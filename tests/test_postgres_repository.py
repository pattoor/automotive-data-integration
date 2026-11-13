"""Integration tests for PostgreSQL persistence against a real server.

Constraints, foreign keys, and UPSERT conflict resolution only exist inside
PostgreSQL, so these tests are not mocked. They skip unless ``TEST_DATABASE_URL``
or ``DATABASE_URL`` points at a disposable database, and they only touch rows
whose CRM identifiers start with a unique per-test prefix.

Run them with a real server, for example inside Compose:

    docker compose run --rm -e TEST_DATABASE_URL="$DATABASE_URL" pipeline-api \
        pytest tests/test_postgres_repository.py
"""

import os
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import psycopg
import pytest

from automotive_data_integration.pipeline_api.repository import PostgresRepository
from automotive_data_integration.pipeline_api.schemas import Customer, Sale, Vehicle
from automotive_data_integration.pipeline_api.transform import RejectedRecord

DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="set TEST_DATABASE_URL or DATABASE_URL to run PostgreSQL integration tests",
)


def raw_customer(crm_id: str, **overrides: Any) -> Customer:
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
    return Customer.model_validate(record)


def raw_vehicle(crm_id: str, customer_crm_id: str, **overrides: Any) -> Vehicle:
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
    return Vehicle.model_validate(record)


def raw_sale(
    crm_id: str, customer_crm_id: str, vehicle_crm_id: str, **overrides: Any
) -> Sale:
    record = {
        "id": crm_id,
        "customer_id": customer_crm_id,
        "vehicle_id": vehicle_crm_id,
        "sale_date": "2024-02-10",
        "amount_usd": 21500.00,
        "status": "completed",
    }
    record.update(overrides)
    return Sale.model_validate(record)


def fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with psycopg.connect(DATABASE_URL) as connection:
        return connection.execute(sql, params).fetchall()


@dataclass
class RepositoryScope:
    """A unique identifier space plus the cleanup for everything it created."""

    repository: PostgresRepository
    prefix: str
    run_ids: list[int] = field(default_factory=list)

    def crm_id(self, suffix: str) -> str:
        return f"{self.prefix}-{suffix}"

    def create_run(self) -> int:
        run_id = self.repository.create_pipeline_run()
        self.run_ids.append(run_id)
        return run_id

    def cleanup(self) -> None:
        """Delete only this test's rows; never truncate or drop shared tables."""
        pattern = f"{self.prefix}-%"
        with psycopg.connect(DATABASE_URL) as connection:
            if self.run_ids:
                connection.execute(
                    "DELETE FROM rejected_records WHERE run_id = ANY(%s)",
                    (self.run_ids,),
                )
                connection.execute(
                    "DELETE FROM pipeline_runs WHERE id = ANY(%s)", (self.run_ids,)
                )
            connection.execute("DELETE FROM sales WHERE crm_id LIKE %s", (pattern,))
            connection.execute("DELETE FROM vehicles WHERE crm_id LIKE %s", (pattern,))
            connection.execute("DELETE FROM customers WHERE crm_id LIKE %s", (pattern,))


@pytest.fixture()
def database() -> RepositoryScope:
    repository = PostgresRepository(DATABASE_URL)
    repository.initialize_schema()
    scope = RepositoryScope(
        repository=repository, prefix=f"it{uuid.uuid4().hex[:12]}"
    )
    try:
        yield scope
    finally:
        scope.cleanup()


def test_initialize_schema_creates_all_tables_and_is_idempotent(database):
    database.repository.initialize_schema()
    database.repository.initialize_schema()

    rows = fetch_all(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' "
        "AND table_name IN ("
        "'customers', 'vehicles', 'sales', 'pipeline_runs', 'rejected_records'"
        ") ORDER BY table_name"
    )

    assert [row[0] for row in rows] == [
        "customers",
        "pipeline_runs",
        "rejected_records",
        "sales",
        "vehicles",
    ]


def test_upsert_customers_inserts_then_updates_without_extra_rows(database):
    crm_id = database.crm_id("cust-1")

    assert database.repository.upsert_customers([raw_customer(crm_id)]) == 1
    changed = raw_customer(
        crm_id, first_name="Augusta", email="augusta@example.test", city=None
    )
    assert database.repository.upsert_customers([changed]) == 1

    rows = fetch_all(
        "SELECT first_name, email, city FROM customers WHERE crm_id = %s", (crm_id,)
    )
    assert rows == [("Augusta", "augusta@example.test", None)]


def test_upsert_customers_applies_last_value_for_repeated_id_in_one_batch(database):
    crm_id = database.crm_id("cust-2")

    written = database.repository.upsert_customers(
        [raw_customer(crm_id, city="London"), raw_customer(crm_id, city="Paris")]
    )

    assert written == 2
    rows = fetch_all("SELECT city FROM customers WHERE crm_id = %s", (crm_id,))
    assert rows == [("Paris",)]


def test_upsert_vehicles_and_sales_keep_their_foreign_keys(database):
    customer_id = database.crm_id("cust-3")
    vehicle_id = database.crm_id("veh-3")
    sale_id = database.crm_id("sale-3")

    database.repository.upsert_customers([raw_customer(customer_id)])
    assert (
        database.repository.upsert_vehicles(
            [raw_vehicle(vehicle_id, customer_id, vin="SYN00000000000003")]
        )
        == 1
    )
    assert (
        database.repository.upsert_sales(
            [raw_sale(sale_id, customer_id, vehicle_id, amount_usd="18500.55")]
        )
        == 1
    )

    rows = fetch_all(
        "SELECT s.amount_usd, s.status, v.vin, c.email "
        "FROM sales AS s "
        "JOIN vehicles AS v ON v.crm_id = s.vehicle_crm_id "
        "JOIN customers AS c ON c.crm_id = s.customer_crm_id "
        "WHERE s.crm_id = %s",
        (sale_id,),
    )
    assert rows == [
        (
            Decimal("18500.55"),
            "COMPLETED",
            "SYN00000000000003",
            "ada@example.test",
        )
    ]


@pytest.mark.parametrize(
    ("status", "error_message"),
    [
        ("succeeded", None),
        ("failed", "crm-api page 2 returned 502"),
    ],
)
def test_pipeline_run_keeps_counts_and_rejected_raw_payload(
    database, status, error_message
):
    run_id = database.create_run()
    raw_payload = {
        "id": "CUST-9001",
        "email": "not-an-email",
        "tags": ["synthetic", "malformed"],
        "details": {"reason": "demo fixture"},
    }

    written = database.repository.save_rejected_records(
        run_id,
        [
            RejectedRecord(
                entity="customer",
                source_id="CUST-9001",
                raw=raw_payload,
                reason="email: not a valid email address",
            )
        ],
    )
    database.repository.finish_pipeline_run(
        run_id,
        status=status,
        fetched_count=7,
        accepted_count=5,
        rejected_count=1,
        duplicate_count=1,
        error_message=error_message,
    )

    assert written == 1
    run_rows = fetch_all(
        "SELECT status, fetched_count, accepted_count, rejected_count, "
        "duplicate_count, error_message, started_at IS NOT NULL, "
        "finished_at >= started_at "
        "FROM pipeline_runs WHERE id = %s",
        (run_id,),
    )
    assert run_rows == [(status, 7, 5, 1, 1, error_message, True, True)]

    rejected_rows = fetch_all(
        "SELECT entity, source_id, raw_payload, reason "
        "FROM rejected_records WHERE run_id = %s",
        (run_id,),
    )
    assert rejected_rows == [
        (
            "customer",
            "CUST-9001",
            raw_payload,
            "email: not a valid email address",
        )
    ]


def test_finish_pipeline_run_rejects_unknown_run_id(database):
    with pytest.raises(LookupError):
        database.repository.finish_pipeline_run(
            -1,
            status="failed",
            fetched_count=0,
            accepted_count=0,
            rejected_count=0,
            duplicate_count=0,
            error_message="no such run",
        )


def test_upsert_vehicles_surfaces_unknown_customer_foreign_key(database):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        database.repository.upsert_vehicles(
            [raw_vehicle(database.crm_id("veh-orphan"), database.crm_id("cust-missing"))]
        )


def test_upsert_sales_surfaces_unknown_vehicle_foreign_key(database):
    customer_id = database.crm_id("cust-4")
    database.repository.upsert_customers([raw_customer(customer_id)])

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        database.repository.upsert_sales(
            [
                raw_sale(
                    database.crm_id("sale-orphan"),
                    customer_id,
                    database.crm_id("veh-missing"),
                )
            ]
        )
