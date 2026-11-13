"""End-to-end pipeline runs against a real CRM service and PostgreSQL.

Gated on ``DATABASE_URL`` (or ``TEST_DATABASE_URL``) and ``CRM_BASE_URL`` so a
laptop without the Compose stack reports a clear skip instead of a failure.

The fixture entities remain in the database on purpose: they are the portfolio
dataset. Only the pipeline runs created here (and their cascading rejected
records) are removed afterwards. No table is truncated or dropped.
"""

import os
from copy import deepcopy
from typing import Any

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from automotive_data_integration.pipeline_api.main import app

DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
CRM_BASE_URL = os.environ.get("CRM_BASE_URL")

pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and CRM_BASE_URL),
    reason="set DATABASE_URL (or TEST_DATABASE_URL) and CRM_BASE_URL for the end-to-end pipeline test",
)

CUSTOMER_IDS = [f"CUST-{number:04d}" for number in range(1, 6)]
VEHICLE_IDS = [f"VEH-{number:04d}" for number in range(1, 6)]
SALE_IDS = [f"SALE-{number:04d}" for number in range(1, 6)]

EXPECTED_COUNTS = {
    "fetched": 17,
    "accepted": 15,
    "rejected": 1,
    "duplicate": 1,
}


def fetch_bad_customer() -> dict[str, Any]:
    """Read CUST-9001 straight from the CRM service, independent of the client."""
    url = f"{CRM_BASE_URL.rstrip('/')}/customers"
    response = httpx.get(url, params={"page": 1, "page_size": 100}, timeout=10)
    response.raise_for_status()
    return deepcopy(
        next(item for item in response.json()["items"] if item["id"] == "CUST-9001")
    )


def entity_stats() -> dict[str, dict[str, int]]:
    """Fixture row counts plus total/distinct identifiers for every entity table."""
    stats: dict[str, dict[str, int]] = {}
    with psycopg.connect(DATABASE_URL) as connection:
        for table, ids in (
            ("customers", CUSTOMER_IDS),
            ("vehicles", VEHICLE_IDS),
            ("sales", SALE_IDS),
        ):
            fixture_rows = connection.execute(
                f"SELECT count(*) FROM {table} WHERE crm_id = ANY(%s)",
                (ids,),
            ).fetchone()[0]
            total_rows, distinct_ids = connection.execute(
                f"SELECT count(*), count(DISTINCT crm_id) FROM {table}"
            ).fetchone()
            stats[table] = {
                "fixture_rows": fixture_rows,
                "total_rows": total_rows,
                "distinct_ids": distinct_ids,
            }
    return stats


def stored_run(run_id: int) -> tuple[Any, ...]:
    with psycopg.connect(DATABASE_URL) as connection:
        return connection.execute(
            "SELECT status, fetched_count, accepted_count, rejected_count, "
            "duplicate_count FROM pipeline_runs WHERE id = %s",
            (run_id,),
        ).fetchone()


def stored_rejections(run_id: int) -> list[tuple[Any, ...]]:
    with psycopg.connect(DATABASE_URL) as connection:
        return connection.execute(
            "SELECT source_id, raw_payload, reason FROM rejected_records "
            "WHERE run_id = %s",
            (run_id,),
        ).fetchall()


def assert_summary(summary: dict[str, Any]) -> None:
    assert isinstance(summary["run_id"], int)
    assert summary["status"] == "succeeded"
    assert {
        key: summary[key] for key in ("fetched", "accepted", "rejected", "duplicate")
    } == EXPECTED_COUNTS


def test_two_runs_are_idempotent_and_quarantine_the_malformed_customer():
    expected_bad_customer = fetch_bad_customer()
    run_ids: list[int] = []
    try:
        with TestClient(app) as client:
            first = client.post("/pipeline/runs")
            assert first.status_code == 200
            first_summary = first.json()
            assert_summary(first_summary)
            run_ids.append(first_summary["run_id"])
            stats_after_first = entity_stats()

            second = client.post("/pipeline/runs")
            assert second.status_code == 200
            second_summary = second.json()
            assert_summary(second_summary)
            run_ids.append(second_summary["run_id"])
            stats_after_second = entity_stats()

        assert stats_after_second == stats_after_first
        for table in ("customers", "vehicles", "sales"):
            assert stats_after_second[table]["fixture_rows"] == 5
            assert (
                stats_after_second[table]["distinct_ids"]
                == stats_after_second[table]["total_rows"]
            )

        for run_id in run_ids:
            assert stored_run(run_id) == ("succeeded", 17, 15, 1, 1)

        rejections = stored_rejections(run_ids[-1])
        assert len(rejections) == 1
        source_id, raw_payload, reason = rejections[0]
        assert source_id == "CUST-9001"
        assert raw_payload == expected_bad_customer
        assert "email" in reason
    finally:
        # Remove only this test's run history; rejected records cascade with it.
        # Fixture entities stay as the intentional portfolio dataset.
        if run_ids:
            with psycopg.connect(DATABASE_URL) as connection:
                connection.execute(
                    "DELETE FROM pipeline_runs WHERE id = ANY(%s)", (run_ids,)
                )
