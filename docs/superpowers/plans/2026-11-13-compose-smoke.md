# Compose End-to-End Smoke Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Each task ends with a runnable verification gate.

**Goal:** Add a repeatable smoke test that calls the running `pipeline-api` over the Compose network twice and proves the real CRM→ETL→PostgreSQL path remains idempotent.

**Architecture:** Add one pytest integration test that runs inside the already-running `pipeline-api` container. It posts to `http://pipeline-api:8000/pipeline/runs`, checks the returned summaries and PostgreSQL state, and removes only the run rows created by this test. The existing entity fixtures remain in the database.

**Tech Stack:** Python 3.13 in the Compose image, pytest, httpx, psycopg 3, PostgreSQL 16, Docker Compose v2.

## Global Constraints

- Use synthetic CRM data only; do not add real CRM integrations, external services, or credentials.
- Keep ETL and persistence logic in `pipeline-api`; the smoke test exercises it through HTTP.
- Run G7 application/tests only through Docker Compose; do not install host packages or use `sudo` on G7.
- Keep PostgreSQL and n8n data in the existing project-relative bind mounts; never use named persistent volumes or global Docker prunes.
- Delete only `pipeline_runs` rows created by the test; rejected rows must cascade, and entity fixtures must remain.
- Leave the n8n workflow unpublished and inactive.

---

## File Map

- Create `tests/test_compose_smoke.py` — actual HTTP and PostgreSQL smoke coverage for the running Compose services.
- Modify `docs/ROADMAP.md` only after the smoke test passes locally and on the intended Compose runtime — record the exact verification command and result.

### Task 1: Add the live Compose smoke test

**Files:**
- Create: `tests/test_compose_smoke.py`

**Interfaces:**
- Consumes: the running `pipeline-api` service at `http://pipeline-api:8000`, its Compose-provided `DATABASE_URL`, and PostgreSQL tables from `database/schema.sql`.
- Produces: `test_two_live_http_runs_are_idempotent_and_quarantine_the_bad_customer`, runnable with `docker compose exec -T pipeline-api pytest tests/test_compose_smoke.py`.

- [x] **Step 1: Add the test module**

```python
"""Smoke-test the running Compose services through the real HTTP boundary."""

from __future__ import annotations

import os

import httpx
import psycopg
import pytest

DATABASE_URL = os.environ.get("DATABASE_URL")
COMPOSE_SMOKE_TEST = os.environ.get("COMPOSE_SMOKE_TEST") == "1"
PIPELINE_URL = "http://pipeline-api:8000"
EXPECTED_COUNTS = {"fetched": 17, "accepted": 15, "rejected": 1, "duplicate": 1}


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
        200,
        json={"run_id": 42, "status": "succeeded", **EXPECTED_COUNTS},
    )

    summary = assert_successful_response(response, run_ids)

    assert summary["run_id"] == 42
    assert run_ids == [42]


def entity_counts() -> dict[str, tuple[int, int]]:
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
                "SELECT source_id, reason FROM rejected_records "
                "WHERE run_id = %s",
                (run_ids[-1],),
            ).fetchall()
        assert len(rejected) == 1
        assert rejected[0][0] == "CUST-9001"
        assert "email" in rejected[0][1]
    finally:
        if run_ids:
            with psycopg.connect(DATABASE_URL) as connection:
                connection.execute(
                    "DELETE FROM pipeline_runs WHERE id = ANY(%s)", (run_ids,)
                )


def remember_run_id(response: httpx.Response, run_ids: list[int]) -> dict[str, object]:
    """Track a persisted run ID before later response assertions can fail."""
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
    """Track a response's run ID exactly once before checking its outcome."""
    summary = remember_run_id(response, run_ids)
    assert response.status_code == 200, response.text
    assert summary["status"] == "succeeded"
    assert {key: summary[key] for key in EXPECTED_COUNTS} == EXPECTED_COUNTS
    return summary
```

- [x] **Step 2: Prepare only the project-local n8n state directory when needed**

On a fresh Linux checkout, create `n8n/data` as the project user before starting Compose. On G7, verify the existing directory is still owned by UID/GID 1000; do not use `sudo` or change PostgreSQL permissions.

- [x] **Step 3: Verify the focused test against Compose**

Run from the repository root after the stack is available:

```bash
docker compose up -d --build --wait --wait-timeout 300
docker compose exec -T -e COMPOSE_SMOKE_TEST=1 pipeline-api pytest tests/test_compose_smoke.py
```

Expected: three tests pass (two helper unit tests plus the live HTTP integration test), both real HTTP responses contain `17/15/1/1`, entity counts are unchanged, and only the two test-created run rows are deleted in `finally`.

- [x] **Step 4: Verify local test discovery remains safe without Compose**

Run: `.venv/Scripts/python.exe -m pytest tests/test_compose_smoke.py -rs`

Expected: both helper unit tests pass and the live smoke test skips with the stated reason unless both `DATABASE_URL` and `COMPOSE_SMOKE_TEST=1` are present; it must not attempt network access or mutate a local database when the marker is absent.

- [x] **Step 5: Run the complete in-container suite**

Run: `docker compose exec -T pipeline-api pytest`

Expected: unit, PostgreSQL, and TestClient end-to-end tests pass; the live Compose smoke test skips because its explicit marker is absent. The n8n export contract test may also skip because `n8n/` is excluded from the API build context.

Then run the explicitly marked live test:

```bash
docker compose exec -T -e COMPOSE_SMOKE_TEST=1 pipeline-api pytest tests/test_compose_smoke.py
```

Expected: one live test passes, its two run IDs are distinct, and the test removes only its created run rows.

- [x] **Step 6: Record evidence after the test passes**

Update the Stage 6 entry in `docs/ROADMAP.md` with the exact focused and full in-container results. Do not change the n8n inactive state or clean up portfolio entity fixtures.

- [x] **Step 7: Commit the smoke-test work unit**

Run `git add tests/test_compose_smoke.py docs/ROADMAP.md && git commit -m "test: add live Compose smoke coverage"` after the verification results are recorded.

## Completion Gate

- `tests/test_compose_smoke.py` passes against the actual running Compose service, not only FastAPI `TestClient`.
- Both runs are `succeeded` with fetched/accepted/rejected/duplicate `17/15/1/1`.
- Entity table counts and distinct CRM-ID counts are unchanged after the two runs.
- Cleanup deletes only the test's run IDs; rejected rows cascade and fixture entities remain.
- Pause for the learner checkpoint after this component before starting the CI plan.
