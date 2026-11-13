"""ETL orchestration: extract, transform, validate relationships, load, report.

The service composes the CRM client, the pure transforms, and the PostgreSQL
repository. Every run has a persisted row before extraction starts, so a
systemic failure can be finalized as ``failed`` with counts and an error message
instead of leaving a run stuck in ``running``.

Row-level problems (invalid records, unresolvable parent references) are
quarantined and do not fail the run. Only a source or database failure that
prevents the batch from completing marks the run failed.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import NoReturn

import psycopg

from automotive_data_integration.pipeline_api.crm_client import (
    CrmClient,
    CrmClientError,
)
from automotive_data_integration.pipeline_api.repository import PostgresRepository
from automotive_data_integration.pipeline_api.schemas import (
    Customer,
    PipelineRunSummary,
    Sale,
    Vehicle,
)
from automotive_data_integration.pipeline_api.transform import (
    RejectedRecord,
    TransformResult,
    transform_customers,
    transform_sales,
    transform_vehicles,
)

logger = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    """A run could not complete; the message is safe for an HTTP response.

    ``status_code`` separates a source failure (502) from a local database or
    configuration failure (503). ``run_id`` is ``None`` only when the run could
    not be created at all.
    """

    def __init__(
        self, message: str, *, run_id: int | None = None, status_code: int = 503
    ) -> None:
        super().__init__(message)
        self.message = message
        self.run_id = run_id
        self.status_code = status_code


class PipelineService:
    """Run one full ETL execution and return its persisted summary."""

    def __init__(
        self, repository: PostgresRepository, crm_client: CrmClient
    ) -> None:
        self._repository = repository
        self._crm_client = crm_client

    def run(self) -> PipelineRunSummary:
        run_id = self._start_run()

        fetched = 0
        accepted = 0
        rejected: list[RejectedRecord] = []
        duplicate = 0

        try:
            raw_customers = self._crm_client.fetch_customers()
            fetched += len(raw_customers)
            raw_vehicles = self._crm_client.fetch_vehicles()
            fetched += len(raw_vehicles)
            raw_sales = self._crm_client.fetch_sales()
            fetched += len(raw_sales)

            customer_result = transform_customers(raw_customers)
            vehicle_result = transform_vehicles(raw_vehicles)
            sale_result = transform_sales(raw_sales)
            duplicate = (
                customer_result.duplicate_count
                + vehicle_result.duplicate_count
                + sale_result.duplicate_count
            )

            vehicles, sales, relationship_rejects = _resolve_relationships(
                customer_result, vehicle_result, sale_result
            )
            rejected = [
                *customer_result.rejected,
                *vehicle_result.rejected,
                *sale_result.rejected,
                *relationship_rejects,
            ]

            accepted += self._repository.upsert_customers(customer_result.accepted)
            accepted += self._repository.upsert_vehicles(vehicles)
            accepted += self._repository.upsert_sales(sales)
            self._repository.save_rejected_records(run_id, rejected)
            self._repository.finish_pipeline_run(
                run_id,
                status="succeeded",
                fetched_count=fetched,
                accepted_count=accepted,
                rejected_count=len(rejected),
                duplicate_count=duplicate,
            )
        except CrmClientError as error:
            self._fail(
                run_id,
                fetched=fetched,
                accepted=accepted,
                rejected=len(rejected),
                duplicate=duplicate,
                message=f"crm extraction failed: {error}",
                status_code=502,
                cause=error,
            )
        except psycopg.Error as error:
            self._fail(
                run_id,
                fetched=fetched,
                accepted=accepted,
                rejected=len(rejected),
                duplicate=duplicate,
                message=f"database failure: {type(error).__name__}",
                status_code=503,
                cause=error,
            )
        except Exception as error:  # noqa: BLE001 - a run must never stay `running`
            logger.warning(
                "pipeline run %s failed unexpectedly (%s)",
                run_id,
                type(error).__name__,
            )
            self._fail(
                run_id,
                fetched=fetched,
                accepted=accepted,
                rejected=len(rejected),
                duplicate=duplicate,
                message="unexpected pipeline failure",
                status_code=503,
                cause=error,
            )

        return PipelineRunSummary(
            run_id=run_id,
            status="succeeded",
            fetched=fetched,
            accepted=accepted,
            rejected=len(rejected),
            duplicate=duplicate,
        )

    def _start_run(self) -> int:
        try:
            return self._repository.create_pipeline_run()
        except Exception as error:  # noqa: BLE001 - nothing to finalize without a run
            logger.warning(
                "could not create a pipeline run (%s)", type(error).__name__
            )
            raise PipelineError(
                "could not start a pipeline run", status_code=503
            ) from error

    def _fail(
        self,
        run_id: int,
        *,
        fetched: int,
        accepted: int,
        rejected: int,
        duplicate: int,
        message: str,
        status_code: int,
        cause: Exception,
    ) -> NoReturn:
        """Best-effort failure finalization, then one controlled error."""
        try:
            self._repository.finish_pipeline_run(
                run_id,
                status="failed",
                fetched_count=fetched,
                accepted_count=accepted,
                rejected_count=rejected,
                duplicate_count=duplicate,
                error_message=message,
            )
        except Exception as finalize_error:  # noqa: BLE001 - keep the original cause
            logger.warning(
                "pipeline run %s could not be marked failed (%s)",
                run_id,
                type(finalize_error).__name__,
            )
        raise PipelineError(
            message, run_id=run_id, status_code=status_code
        ) from cause


def _resolve_relationships(
    customer_result: TransformResult[Customer],
    vehicle_result: TransformResult[Vehicle],
    sale_result: TransformResult[Sale],
) -> tuple[list[Vehicle], list[Sale], list[RejectedRecord]]:
    """Keep only records whose parents are accepted in this batch.

    Vehicle and sale payloads are index-aligned with their accepted records, so
    a relationship rejection stores the exact source row that caused it.
    """
    accepted_customer_ids = {
        customer.crm_id for customer in customer_result.accepted
    }
    accepted_vehicle_ids: set[str] = set()
    vehicles: list[Vehicle] = []
    rejected: list[RejectedRecord] = []

    for vehicle, raw in zip(
        vehicle_result.accepted, vehicle_result.accepted_raw, strict=True
    ):
        if vehicle.customer_crm_id not in accepted_customer_ids:
            rejected.append(
                RejectedRecord(
                    entity="vehicle",
                    source_id=vehicle.crm_id,
                    raw=deepcopy(raw),
                    reason=(
                        "customer_crm_id: references unknown or rejected "
                        f"customer {vehicle.customer_crm_id}"
                    ),
                )
            )
            continue
        accepted_vehicle_ids.add(vehicle.crm_id)
        vehicles.append(vehicle)

    sales: list[Sale] = []
    for sale, raw in zip(sale_result.accepted, sale_result.accepted_raw, strict=True):
        reasons = []
        if sale.customer_crm_id not in accepted_customer_ids:
            reasons.append(
                "customer_crm_id: references unknown or rejected customer "
                f"{sale.customer_crm_id}"
            )
        if sale.vehicle_crm_id not in accepted_vehicle_ids:
            reasons.append(
                "vehicle_crm_id: references unknown or rejected vehicle "
                f"{sale.vehicle_crm_id}"
            )
        if reasons:
            rejected.append(
                RejectedRecord(
                    entity="sale",
                    source_id=sale.crm_id,
                    raw=deepcopy(raw),
                    reason="; ".join(reasons),
                )
            )
            continue
        sales.append(sale)

    return vehicles, sales, rejected
