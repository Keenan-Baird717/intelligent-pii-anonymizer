"""API tests for POST /api/v1/analyze/text."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.recognizers.checksums import make_valid_sin


def test_empty_and_whitespace_rejected(client: TestClient) -> None:
    assert client.post("/api/v1/analyze/text", json={"text": ""}).status_code == 400
    assert client.post("/api/v1/analyze/text", json={"text": "   \n"}).status_code == 400
    payload = client.post("/api/v1/analyze/text", json={"text": ""}).json()
    assert payload["error"]["code"] == "EMPTY_TEXT"
    assert "request_id" in payload["error"]


def test_text_length_limit(client: TestClient) -> None:
    long_text = "a" * (settings.max_text_length + 1)
    response = client.post("/api/v1/analyze/text", json={"text": long_text})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TEXT_TOO_LONG"


def test_analyze_text_workflow(client: TestClient) -> None:
    sin = make_valid_sin("94645428")
    text = (
        f"Fictional User at fictional.user@example.com, phone 902-555-0182, "
        f"postal B3H 1Y2, card 4111-1111-1111-1111, SIN {sin}, "
        f"site https://example.com, ip 203.0.113.10."
    )
    response = client.post(
        "/api/v1/analyze/text",
        json={"text": text, "language": "en"},
        headers={"X-Request-ID": "analyze-test-1"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "analyze-test-1"
    body = response.json()
    assert body["text"] == text
    assert body["detection_count"] >= 5
    types = {e["entity_type"] for e in body["entities"]}
    assert "EMAIL_ADDRESS" in types
    assert "PHONE_NUMBER" in types
    assert "CANADIAN_POSTAL_CODE" in types
    assert "CREDIT_CARD" in types
    assert "CANADIAN_SIN" in types
    # Sorted by start
    starts = [e["start"] for e in body["entities"]]
    assert starts == sorted(starts)
    for entity in body["entities"]:
        assert text[entity["start"] : entity["end"]] == entity["text"]
        assert 0.0 <= entity["confidence"] <= 1.0
        assert "detection_source" in entity
        assert "recognizer_name" in entity


def test_no_pii_empty_result(client: TestClient) -> None:
    response = client.post(
        "/api/v1/analyze/text",
        json={"text": "The weather is pleasant today."},
    )
    assert response.status_code == 200
    assert response.json()["detection_count"] == 0


def test_safe_logging_excludes_text_and_values(
    client: TestClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_email = "secret.fictional@example.com"
    response = client.post(
        "/api/v1/analyze/text",
        json={"text": f"Email {secret_email}"},
    )
    assert response.status_code == 200
    captured = capsys.readouterr().out + capsys.readouterr().err
    assert secret_email not in captured
    assert "Email secret" not in captured


def test_error_response_does_not_echo_text(client: TestClient) -> None:
    long_text = "SENSITIVE_FICTIONAL_VALUE_" + ("x" * (settings.max_text_length))
    response = client.post("/api/v1/analyze/text", json={"text": long_text})
    assert response.status_code == 400
    assert "SENSITIVE_FICTIONAL_VALUE_" not in response.text
