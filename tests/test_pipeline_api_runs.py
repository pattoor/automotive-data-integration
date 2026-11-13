"""HTTP contract of ``POST /pipeline/runs``.

The service dependency is replaced so these tests describe the route's own
behavior: the response body, status codes, and how a failed run is reported.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from automotive_data_integration.pipeline_api.dependencies import get_pipeline_service
from automotive_data_integration.pipeline_api.main import app
from automotive_data_integration.pipeline_api.schemas import PipelineRunSummary
from automotive_data_integration.pipeline_api.service import PipelineError


class StubService:
    def __init__(self, *, summary=None, error=None) -> None:
        self.summary = summary
        self.error = error

    def run(self) -> PipelineRunSummary:
        if self.error is not None:
            raise self.error
        return self.summary


def post_run(service: Any) -> Any:
    app.dependency_overrides[get_pipeline_service] = lambda: service
    try:
        with TestClient(app) as client:
            return client.post("/pipeline/runs")
    finally:
        app.dependency_overrides.pop(get_pipeline_service, None)


def test_create_run_returns_the_run_summary():
    summary = PipelineRunSummary(
        run_id=7, status="succeeded", fetched=17, accepted=15, rejected=1, duplicate=1
    )

    response = post_run(StubService(summary=summary))

    assert response.status_code == 200
    assert response.json() == {
        "run_id": 7,
        "status": "succeeded",
        "fetched": 17,
        "accepted": 15,
        "rejected": 1,
        "duplicate": 1,
    }


def test_create_run_reports_a_failed_run_as_a_controlled_error():
    error = PipelineError(
        "crm extraction failed: crm-api request for /sales failed with HTTP 502",
        run_id=7,
        status_code=502,
    )

    response = post_run(StubService(error=error))

    assert response.status_code == 502
    assert response.json() == {
        "run_id": 7,
        "status": "failed",
        "message": "crm extraction failed: crm-api request for /sales failed with HTTP 502",
    }


def test_create_run_without_pipeline_configuration_returns_503(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CRM_BASE_URL", raising=False)
    monkeypatch.delenv("CRM_PAGE_SIZE", raising=False)

    with TestClient(app) as client:
        response = client.post("/pipeline/runs")

    assert response.status_code == 503
    message = response.json()["message"]
    assert "DATABASE_URL" in message
    assert "CRM_BASE_URL" in message
