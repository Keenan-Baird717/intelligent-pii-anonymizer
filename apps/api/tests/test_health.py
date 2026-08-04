import pytest
from fastapi.testclient import TestClient


def test_health_endpoint_returns_ok_when_database_connected(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert payload["database"] in {"connected", "unavailable"}
    assert payload["version"] == "0.1.0"
    assert "password" not in response.text.lower()
    assert "postgresql" not in response.text.lower()


def test_health_endpoint_includes_request_id_header(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "test-request-123"})
    assert response.headers.get("X-Request-ID") == "test-request-123"


def test_health_endpoint_reports_degraded_when_database_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.api.v1.health.check_database_connection",
        lambda: (False, "fail"),
    )
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["database"] == "unavailable"
