from fastapi.testclient import TestClient

from automotive_data_integration.pipeline_api.main import app

client = TestClient(app)


def test_pipeline_health_reports_ok_for_the_pipeline_service():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "pipeline-api"}
