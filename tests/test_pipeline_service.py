"""Orchestration tests for the pipeline service.

Only the two external boundaries are replaced: the CRM client (HTTP) and the
repository (PostgreSQL). Transforms, relationship validation, counting, and
failure finalization run for real, so these tests describe pipeline behavior
rather than fake behavior.
"""

from copy import deepcopy
from typing import Any

import psycopg
import pytest

from automotive_data_integration.pipeline_api.crm_client import CrmClientError
from automotive_data_integration.pipeline_api.service import (
    PipelineError,
    PipelineService,
)


def customer(crm_id: str, **overrides: Any) -> dict[str, Any]:
    record = {
        "id": crm_id,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.test",
        "phone": "+1-555-0101",
        "city": "London",
        "created_at": "2024-01-05T09:00:00Z",
    }
    record.update(overrides)
    return record


def vehicle(crm_id: str, customer_crm_id: str, **overrides: Any) -> dict[str, Any]:
    record = {
        "id": crm_id,
        "customer_id": customer_crm_id,
        "vin": "SYN00000000000001",
        "make": "Ficta",
        "model": "Vela",
        "year": 2021,
        "odometer_km": 41250,
    }
    record.update(overrides)
    return record


def sale(
    crm_id: str, customer_crm_id: str, vehicle_crm_id: str, **overrides: Any
) -> dict[str, Any]:
    record = {
        "id": crm_id,
        "customer_id": customer_crm_id,
        "vehicle_id": vehicle_crm_id,
        "sale_date": "2024-02-10",
        "amount_usd": 21500.00,
        "status": "completed",
    }
    record.update(overrides)
    return record


class FakeCrmClient:
    """A stand-in for the HTTP client; returns whole collections, already paged."""

    def __init__(
        self,
        *,
        customers: list[dict[str, Any]],
        vehicles: list[dict[str, Any]],
        sales: list[dict[str, Any]],
        fail_on: str | None = None,
    ) -> None:
        self.customers = customers
        self.vehicles = vehicles
        self.sales = sales
        self.fail_on = fail_on

    def _collection(self, name: str, records: list[dict[str, Any]]):
        if self.fail_on == name:
            raise CrmClientError(f"crm-api request for /{name} failed with HTTP 502")
        return records

    def fetch_customers(self):
        return self._collection("customers", self.customers)

    def fetch_vehicles(self):
        return self._collection("vehicles", self.vehicles)

    def fetch_sales(self):
        return self._collection("sales", self.sales)


class FakeRepository:
    """Records writes in order and can fail one boundary like PostgreSQL would."""

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.calls: list[tuple[str, Any]] = []
        self.finishes: list[dict[str, Any]] = []
        self.upserted: dict[str, list[Any]] = {}
        self.rejected: list[Any] = []

    def create_pipeline_run(self) -> int:
        self.calls.append(("create_pipeline_run", None))
        return 42

    def _upsert(self, name: str, records):
        if self.fail_on == name:
            raise psycopg.OperationalError("connection to server was lost")
        self.calls.append((name, [record.crm_id for record in records]))
        self.upserted[name] = list(records)
        return len(records)

    def upsert_customers(self, customers):
        return self._upsert("upsert_customers", customers)

    def upsert_vehicles(self, vehicles):
        return self._upsert("upsert_vehicles", vehicles)

    def upsert_sales(self, sales):
        return self._upsert("upsert_sales", sales)

    def save_rejected_records(self, run_id, rejected):
        self.calls.append(
            (
                "save_rejected_records",
                [(record.entity, record.source_id) for record in rejected],
            )
        )
        self.rejected.extend(rejected)
        return len(rejected)

    def finish_pipeline_run(self, run_id, **counts):
        self.finishes.append({"run_id": run_id, **counts})


def raw_fixture_collections():
    """Source rows deliberately including a duplicate and broken references."""
    customers = [
        customer("CUST-1", city="London"),
        customer("CUST-1", city="Paris"),
        customer("CUST-9001", email="not-an-email", created_at="2024-13-45T99:99:99Z"),
    ]
    vehicles = [
        vehicle("VEH-1", "CUST-1"),
        vehicle("VEH-2", "CUST-9001", vin="SYN00000000000002"),
    ]
    sales = [
        sale("SALE-1", "CUST-1", "VEH-1"),
        sale("SALE-2", "CUST-9001", "VEH-404"),
    ]
    return customers, vehicles, sales


def build_service(customers, vehicles, sales, *, repository=None, crm=None):
    repository = repository or FakeRepository()
    crm = crm or FakeCrmClient(customers=customers, vehicles=vehicles, sales=sales)
    return PipelineService(repository=repository, crm_client=crm), repository


def test_run_counts_accepted_rejected_duplicate_and_persists_in_parent_order():
    customers, vehicles, sales = raw_fixture_collections()
    service, repository = build_service(customers, vehicles, sales)

    summary = service.run()

    assert summary.run_id == 42
    assert summary.status == "succeeded"
    assert summary.fetched == 7
    assert summary.accepted == 3
    assert summary.rejected == 3
    assert summary.duplicate == 1
    assert repository.calls == [
        ("create_pipeline_run", None),
        ("upsert_customers", ["CUST-1"]),
        ("upsert_vehicles", ["VEH-1"]),
        ("upsert_sales", ["SALE-1"]),
        (
            "save_rejected_records",
            [("customer", "CUST-9001"), ("vehicle", "VEH-2"), ("sale", "SALE-2")],
        ),
    ]
    assert repository.finishes == [
        {
            "run_id": 42,
            "status": "succeeded",
            "fetched_count": 7,
            "accepted_count": 3,
            "rejected_count": 3,
            "duplicate_count": 1,
        }
    ]


def test_first_valid_duplicate_wins_before_persistence():
    customers = [customer("CUST-1", city="London"), customer("CUST-1", city="Paris")]
    service, repository = build_service(customers, [], [])

    service.run()

    stored = repository.upserted["upsert_customers"]
    assert [(record.crm_id, record.city) for record in stored] == [
        ("CUST-1", "London")
    ]


def test_rejected_relationship_rows_keep_their_exact_raw_payload():
    customers, vehicles, sales = raw_fixture_collections()
    expected = deepcopy([customers[2], vehicles[1], sales[1]])
    service, repository = build_service(customers, vehicles, sales)

    service.run()

    customers[2]["email"] = "changed@example.test"
    vehicles[1]["nested"] = {"changed": True}
    sales[1]["amount_usd"] = 1.0

    assert [rejected.entity for rejected in repository.rejected] == [
        "customer",
        "vehicle",
        "sale",
    ]
    assert [rejected.raw for rejected in repository.rejected] == expected


def test_vehicle_relationship_rejection_blocks_sales_that_need_that_vehicle():
    customers = [customer("CUST-1")]
    vehicles = [vehicle("VEH-2", "CUST-9001")]
    sales = [sale("SALE-3", "CUST-1", "VEH-2")]
    service, repository = build_service(customers, vehicles, sales)

    summary = service.run()

    assert summary.accepted == 1
    assert summary.rejected == 2
    assert repository.calls == [
        ("create_pipeline_run", None),
        ("upsert_customers", ["CUST-1"]),
        ("upsert_vehicles", []),
        ("upsert_sales", []),
        (
            "save_rejected_records",
            [("vehicle", "VEH-2"), ("sale", "SALE-3")],
        ),
    ]


def test_crm_failure_marks_the_run_failed_and_raises_a_controlled_error():
    customers, vehicles, sales = raw_fixture_collections()
    repository = FakeRepository()
    crm = FakeCrmClient(
        customers=customers, vehicles=vehicles, sales=sales, fail_on="sales"
    )
    service, repository = build_service(
        customers, vehicles, sales, repository=repository, crm=crm
    )

    with pytest.raises(PipelineError) as raised:
        service.run()

    assert raised.value.run_id == 42
    assert raised.value.status_code == 502
    assert "crm-api" in raised.value.message
    assert repository.finishes == [
        {
            "run_id": 42,
            "status": "failed",
            "fetched_count": 5,
            "accepted_count": 0,
            "rejected_count": 0,
            "duplicate_count": 0,
            "error_message": raised.value.message,
        }
    ]
    assert [call[0] for call in repository.calls] == ["create_pipeline_run"]


def test_database_failure_marks_the_run_failed_with_rows_written_so_far():
    customers, vehicles, sales = raw_fixture_collections()
    repository = FakeRepository(fail_on="upsert_vehicles")
    service, repository = build_service(
        customers, vehicles, sales, repository=repository
    )

    with pytest.raises(PipelineError) as raised:
        service.run()

    assert raised.value.run_id == 42
    assert raised.value.status_code == 503
    assert "database failure" in raised.value.message
    assert "connection to server was lost" not in raised.value.message
    assert repository.finishes == [
        {
            "run_id": 42,
            "status": "failed",
            "fetched_count": 7,
            "accepted_count": 1,
            "rejected_count": 3,
            "duplicate_count": 1,
            "error_message": raised.value.message,
        }
    ]
