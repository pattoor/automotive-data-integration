"""Smoke-test the running Compose services through the real HTTP boundary.

This module posts to the live ``pipeline-api`` service over the Compose network
instead of using FastAPI's ``TestClient``, then inspects PostgreSQL directly.

The live test is gated on both ``COMPOSE_SMOKE_TEST=1`` (an explicit opt-in the
caller passes with ``docker compose exec -e``) and ``DATABASE_URL`` (supplied by
the Compose service). Both are checked inside the test so the offline helper
tests in this module still run on a laptop. The fixture entities remain in the
database on purpose; only the pipeline runs created here (and their cascading
rejected records) are removed afterwards.
"""

from __future__ import annotations

import os

import httpx
import psycopg
import pytest

DATABASE_URL = os.environ.get("DATABASE_URL")
COMPOSE_SMOKE_TEST = os.environ.get("COMPOSE_SMOKE_TEST") == "1"
PIPELINE_URL = "http://pipeline-api:8000"
EXPECTED_COUNTS = {"fetched": 17, "accepted": 15, "rejected": 1, "duplicate": 1}


def remember_run_id(response: httpx.Response, run_ids: list[int]) -> dict[str, object]:
    """Track a persisted run ID before later response assertions can fail.

    ``pipeline-api`` reports failed runs as JSON carrying the ``run_id``, so the
    identifier is recorded first and ``finally`` can still delete that row when
    a request answers 502/503. Malformed or non-object bodies are ignored, and a
    boolean is rejected because it is an ``int`` subclass, not a real run ID.
    """
    try:
        payload = response.json()
    except ValueError:
        return {}
    if not isinstance(payload, dict):
        return {}
    run_id = payload.get("run_id")
    if isinstance(run_id, int) and not isinstance(run_id, bool):
        run_ids.append(run_id)
    return payload


def assert_successful_response(
    response: httpx.Response, run_ids: list[int]
) -> dict[str, object]:
    """Validate one completed run and track its ID exactly once.

    The identifier is recorded through :func:`remember_run_id` here and nowhere
    else, so a caller cannot append the same run twice. The summary assertions
    run after the ID is known, which keeps ``finally`` cleanup complete even when
    the pipeline answers with an unexpected body.
    """
    summary = remember_run_id(response, run_ids)
    assert response.status_code == 200, response.text
    assert summary["status"] == "succeeded"
    assert {key: summary[key] for key in EXPECTED_COUNTS} == EXPECTED_COUNTS
    return summary


def test_error_response_run_id_is_tracked_before_assertions() -> None:
    run_ids: list[int] = []
    response = httpx.Response(
        502,
        json={"run_id": 42, "status": "failed", "message": "CRM unavailable"},
    )

    payload = remember_run_id(response, run_ids)

    assert payload["status"] == "failed"
    assert run_ids == [42]


def test_successful_response_is_tracked_exactly_once() -> None:
    run_ids: list[int] = []
    response = httpx.Response(
        200, json={"run_id": 7, **EXPECTED_COUNTS, "status": "succeeded"}
    )

    summary = assert_successful_response(response, run_ids)

    assert summary["status"] == "succeeded"
    assert summary["run_id"] == 7
    assert run_ids == [7]


def entity_counts() -> dict[str, tuple[int, int]]:
    """Total and distinct-CRM-ID row counts for every entity table."""
    counts: dict[str, tuple[int, int]] = {}
    with psycopg.connect(DATABASE_URL) as connection:
        for table in ("customers", "vehicles", "sales"):
            total, distinct = connection.execute(
                f"SELECT count(*), count(DISTINCT crm_id) FROM {table}"
            ).fetchone()
            counts[table] = (total, distinct)
    return counts


@pytest.mark.skipif(
    not (DATABASE_URL and COMPOSE_SMOKE_TEST),
    reason="set COMPOSE_SMOKE_TEST=1 inside Compose to exercise the live pipeline service",
)
def test_two_live_http_runs_are_idempotent_and_quarantine_the_bad_customer() -> None:
    before = entity_counts()
    run_ids: list[int] = []

    try:
        for _ in range(2):
            response = httpx.post(f"{PIPELINE_URL}/pipeline/runs", timeout=120)
            assert_successful_response(response, run_ids)

        assert len(run_ids) == 2
        assert len(set(run_ids)) == 2

        after = entity_counts()
        assert after == before
        assert all(total == distinct for total, distinct in after.values())

        with psycopg.connect(DATABASE_URL) as connection:
            for run_id in run_ids:
                assert connection.execute(
                    "SELECT status, fetched_count, accepted_count, rejected_count, "
                    "duplicate_count FROM pipeline_runs WHERE id = %s",
                    (run_id,),
                ).fetchone() == ("succeeded", 17, 15, 1, 1)

            rejected = connection.execute(
                "SELECT source_id, reason FROM rejected_records WHERE run_id = %s",
                (run_ids[-1],),
            ).fetchall()
        assert len(rejected) == 1
        assert rejected[0][0] == "CUST-9001"
        assert "email" in rejected[0][1]
    finally:
        # Remove only this test's run history; rejected records cascade with it.
        # Fixture entities stay as the intentional portfolio dataset.
        if run_ids:
            with psycopg.connect(DATABASE_URL) as connection:
                connection.execute(
                    "DELETE FROM pipeline_runs WHERE id = ANY(%s)", (run_ids,)
                )
