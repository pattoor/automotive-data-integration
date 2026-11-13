"""Startup behaviour of pipeline-api around the optional database.

Both cases run without a database: one proves the service still starts when
persistence is not configured, the other proves an unreachable database fails
the start instead of being ignored.
"""

import psycopg
import pytest
from fastapi.testclient import TestClient

from automotive_data_integration.pipeline_api.main import app


def test_pipeline_api_starts_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "pipeline-api"}


def test_pipeline_api_startup_fails_when_database_is_unreachable(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://nobody:nobody@127.0.0.1:1/unreachable?connect_timeout=2",
    )

    with pytest.raises(psycopg.OperationalError):
        with TestClient(app):
            pass
