from fastapi.testclient import TestClient

from automotive_data_integration.crm_api.main import app

client = TestClient(app)


def test_crm_health_reports_ok_for_the_crm_service():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "crm-api"}
