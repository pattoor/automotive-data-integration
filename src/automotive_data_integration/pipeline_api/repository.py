"""PostgreSQL persistence for normalized CRM entities, runs, and rejections.

The repository talks to PostgreSQL through ``psycopg`` directly. The SQL schema
lives in ``database/schema.sql`` and is applied idempotently, so the same file
serves a fresh Compose database and an already-initialized one.

Transaction policy: every public method opens one connection, runs one logical
operation, and lets the connection context manager commit or roll back. No
method swallows ``psycopg.IntegrityError`` or connection failures: callers see
foreign-key violations, check violations, and unreachable databases.

Upsert policy: entities have a stable CRM identifier as primary key. Writes use
``INSERT ... ON CONFLICT (crm_id) DO UPDATE`` so a repeated run updates the
existing row (including its ``updated_at``) instead of adding a new one.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Sequence

import psycopg
from psycopg.types.json import Jsonb

from automotive_data_integration.pipeline_api.schemas import Customer, Sale, Vehicle
from automotive_data_integration.pipeline_api.transform import RejectedRecord

logger = logging.getLogger(__name__)

_UPSERT_CUSTOMERS = """
INSERT INTO customers (
    crm_id, first_name, last_name, email, phone, city, created_at
) VALUES (
    %(crm_id)s, %(first_name)s, %(last_name)s, %(email)s, %(phone)s,
    %(city)s, %(created_at)s
)
ON CONFLICT (crm_id) DO UPDATE SET
    first_name = EXCLUDED.first_name,
    last_name = EXCLUDED.last_name,
    email = EXCLUDED.email,
    phone = EXCLUDED.phone,
    city = EXCLUDED.city,
    created_at = EXCLUDED.created_at,
    updated_at = now()
"""

_UPSERT_VEHICLES = """
INSERT INTO vehicles (
    crm_id, customer_crm_id, vin, make, model, year, odometer_km
) VALUES (
    %(crm_id)s, %(customer_crm_id)s, %(vin)s, %(make)s, %(model)s,
    %(year)s, %(odometer_km)s
)
ON CONFLICT (crm_id) DO UPDATE SET
    customer_crm_id = EXCLUDED.customer_crm_id,
    vin = EXCLUDED.vin,
    make = EXCLUDED.make,
    model = EXCLUDED.model,
    year = EXCLUDED.year,
    odometer_km = EXCLUDED.odometer_km,
    updated_at = now()
"""

_UPSERT_SALES = """
INSERT INTO sales (
    crm_id, customer_crm_id, vehicle_crm_id, sale_date, amount_usd, status
) VALUES (
    %(crm_id)s, %(customer_crm_id)s, %(vehicle_crm_id)s, %(sale_date)s,
    %(amount_usd)s, %(status)s
)
ON CONFLICT (crm_id) DO UPDATE SET
    customer_crm_id = EXCLUDED.customer_crm_id,
    vehicle_crm_id = EXCLUDED.vehicle_crm_id,
    sale_date = EXCLUDED.sale_date,
    amount_usd = EXCLUDED.amount_usd,
    status = EXCLUDED.status,
    updated_at = now()
"""

_CREATE_PIPELINE_RUN = """
INSERT INTO pipeline_runs (status) VALUES ('running') RETURNING id
"""

_FINISH_PIPELINE_RUN = """
UPDATE pipeline_runs
SET status = %(status)s,
    finished_at = now(),
    fetched_count = %(fetched_count)s,
    accepted_count = %(accepted_count)s,
    rejected_count = %(rejected_count)s,
    duplicate_count = %(duplicate_count)s,
    error_message = %(error_message)s
WHERE id = %(run_id)s
"""

_INSERT_REJECTED_RECORD = """
INSERT INTO rejected_records (run_id, entity, source_id, raw_payload, reason)
VALUES (%(run_id)s, %(entity)s, %(source_id)s, %(raw_payload)s, %(reason)s)
"""


def schema_path() -> Path:
    """Locate ``database/schema.sql`` in a source checkout or in the image.

    The package is installed into ``site-packages`` inside the container, so the
    search walks up from the package first (source trees) and then falls back to
    the working directory, which is ``/app`` in the image where ``Dockerfile``
    copies ``database/``.
    """
    candidates = [
        *(parent / "database" / "schema.sql" for parent in Path(__file__).parents),
        Path.cwd() / "database" / "schema.sql",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "database/schema.sql was not found; copy it next to the application "
        f"(searched: {', '.join(str(path) for path in candidates)})"
    )


class PostgresRepository:
    """Persistence operations for the pipeline, backed by PostgreSQL."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def initialize_schema(self) -> None:
        """Create every missing table and index; safe to run on every startup.

        The script only uses ``CREATE ... IF NOT EXISTS`` and never alters or
        drops existing objects, so it upgrades nothing it cannot safely add.
        Later schema changes belong in explicit migration files.
        """
        path = schema_path()
        sql = path.read_text(encoding="utf-8")
        with psycopg.connect(self._dsn) as connection:
            connection.execute(sql)
        logger.info("applied database schema from %s", path)

    def upsert_customers(self, customers: Sequence[Customer]) -> int:
        """Insert or update customers by CRM id; returns the rows written."""
        rows = [
            {
                "crm_id": customer.crm_id,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "email": customer.email,
                "phone": customer.phone,
                "city": customer.city,
                "created_at": customer.created_at,
            }
            for customer in customers
        ]
        return self._write_many(_UPSERT_CUSTOMERS, rows)

    def upsert_vehicles(self, vehicles: Sequence[Vehicle]) -> int:
        """Insert or update vehicles by CRM id; returns the rows written.

        A vehicle whose customer is not stored yet raises
        ``psycopg.errors.ForeignKeyViolation``.
        """
        rows = [
            {
                "crm_id": vehicle.crm_id,
                "customer_crm_id": vehicle.customer_crm_id,
                "vin": vehicle.vin,
                "make": vehicle.make,
                "model": vehicle.model,
                "year": vehicle.year,
                "odometer_km": vehicle.odometer_km,
            }
            for vehicle in vehicles
        ]
        return self._write_many(_UPSERT_VEHICLES, rows)

    def upsert_sales(self, sales: Sequence[Sale]) -> int:
        """Insert or update sales by CRM id; returns the rows written.

        A sale whose customer or vehicle is not stored yet raises
        ``psycopg.errors.ForeignKeyViolation``.
        """
        rows = [
            {
                "crm_id": sale.crm_id,
                "customer_crm_id": sale.customer_crm_id,
                "vehicle_crm_id": sale.vehicle_crm_id,
                "sale_date": sale.sale_date,
                "amount_usd": sale.amount_usd,
                "status": sale.status,
            }
            for sale in sales
        ]
        return self._write_many(_UPSERT_SALES, rows)

    def create_pipeline_run(self) -> int:
        """Start a run in ``running`` status and return its identifier."""
        with psycopg.connect(self._dsn) as connection:
            row = connection.execute(_CREATE_PIPELINE_RUN).fetchone()
        if row is None:  # pragma: no cover - INSERT ... RETURNING always returns
            raise RuntimeError("pipeline run insert returned no identifier")
        return int(row[0])

    def finish_pipeline_run(
        self,
        run_id: int,
        *,
        status: str,
        fetched_count: int,
        accepted_count: int,
        rejected_count: int,
        duplicate_count: int,
        error_message: str | None = None,
    ) -> None:
        """Record the final status, counts, and optional error of a run."""
        params = {
            "run_id": run_id,
            "status": status,
            "fetched_count": fetched_count,
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "duplicate_count": duplicate_count,
            "error_message": error_message,
        }
        with psycopg.connect(self._dsn) as connection:
            cursor = connection.execute(_FINISH_PIPELINE_RUN, params)
            if cursor.rowcount != 1:
                raise LookupError(f"pipeline run {run_id} does not exist")

    def save_rejected_records(
        self, run_id: int, rejected: Sequence[RejectedRecord]
    ) -> int:
        """Store quarantined source records with their exact raw payload."""
        rows: list[dict[str, Any]] = [
            {
                "run_id": run_id,
                "entity": record.entity,
                "source_id": record.source_id,
                "raw_payload": Jsonb(record.raw),
                "reason": record.reason,
            }
            for record in rejected
        ]
        return self._write_many(_INSERT_REJECTED_RECORD, rows)

    def _write_many(self, statement: str, rows: Sequence[dict[str, Any]]) -> int:
        if not rows:
            return 0
        with psycopg.connect(self._dsn) as connection:
            with connection.cursor() as cursor:
                cursor.executemany(statement, rows)
                return cursor.rowcount
