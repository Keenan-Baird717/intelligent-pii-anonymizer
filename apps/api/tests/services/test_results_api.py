"""Phase 7 result summary and audit-report API tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.results import assert_result_payload_is_safe
from tests.helpers.fictional_files import make_pdf_with_text

FICTIONAL_EMAIL = "fictional.user@example.com"


def _upload_pdf(api_client: TestClient, data: bytes) -> str:
    response = api_client.post(
        "/api/v1/documents",
        files={"file": ("memo.pdf", data, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()["job_id"]


def _complete_pdf_job(api_client: TestClient) -> tuple[str, dict]:
    job_id = _upload_pdf(
        api_client,
        make_pdf_with_text(
            [f"Contact Alice Example at {FICTIONAL_EMAIL} enough filler words CONTROLWORD"]
        ),
    )
    analyze = api_client.post(f"/api/v1/jobs/{job_id}/analyze")
    assert analyze.status_code == 200, analyze.text
    entities = analyze.json()["entities"]
    assert entities
    for entity in entities:
        if entity.get("entity_type") == "EMAIL_ADDRESS":
            api_client.patch(
                f"/api/v1/jobs/{job_id}/entities/{entity['id']}",
                json={"review_status": "accepted"},
            )
        else:
            api_client.patch(
                f"/api/v1/jobs/{job_id}/entities/{entity['id']}",
                json={"review_status": "rejected"},
            )
    anon = api_client.post(f"/api/v1/jobs/{job_id}/anonymize", json={"default_method": "redaction"})
    assert anon.status_code == 200, anon.text
    return job_id, anon.json()


def test_result_summary_safe_fields(api_client: TestClient) -> None:
    job_id, _ = _complete_pdf_job(api_client)
    response = api_client.get(f"/api/v1/jobs/{job_id}/result")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] == job_id
    assert body["status"] == "completed"
    assert body["source_type"] == "pdf"
    assert body["output_type"] == "redacted_pdf"
    assert body["detection_count"] >= 1
    assert body["verification_status"] == "passed"
    assert body["artifact"]["artifact_type"] == "redacted_pdf"
    assert "entity_category_counts" in body
    assert body["entity_category_counts"] == dict(sorted(body["entity_category_counts"].items()))
    assert "method_counts" in body
    assert FICTIONAL_EMAIL not in response.text
    assert "storage_key" not in body
    assert "path" not in body
    assert_result_payload_is_safe(body)


def test_audit_report_download_headers_and_schema(api_client: TestClient) -> None:
    job_id, _ = _complete_pdf_job(api_client)
    response = api_client.get(f"/api/v1/jobs/{job_id}/audit-report")
    assert response.status_code == 200, response.text
    assert response.headers.get("content-type", "").startswith("application/json")
    assert "anonymization-audit-report.json" in response.headers.get("content-disposition", "")
    assert "nosniff" in response.headers.get("x-content-type-options", "").lower()
    assert "no-store" in response.headers.get("cache-control", "")
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["job_id"] == job_id
    assert body["privacy"]["raw_values_included"] is False
    assert body["privacy"]["original_content_included"] is False
    assert body["privacy"]["pseudonym_mapping_included"] is False
    assert body["source"]["type"] == "pdf"
    assert "filename" not in json.dumps(body)
    assert "storage_key" not in json.dumps(body)
    assert FICTIONAL_EMAIL not in response.text
    assert body["analysis"]["entity_category_counts"] == dict(
        sorted(body["analysis"]["entity_category_counts"].items())
    )
    assert_result_payload_is_safe(body)


def test_result_unknown_job(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/jobs/00000000-0000-4000-8000-000000000099/result")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_result_and_audit_unavailable_after_delete(api_client: TestClient) -> None:
    job_id, anon = _complete_pdf_job(api_client)
    artifact_id = anon["artifact"]["artifact_id"]
    deleted = api_client.delete(f"/api/v1/jobs/{job_id}")
    assert deleted.status_code == 200
    assert api_client.get(f"/api/v1/jobs/{job_id}").status_code == 404
    assert api_client.get(f"/api/v1/jobs/{job_id}/result").status_code == 404
    assert api_client.get(f"/api/v1/jobs/{job_id}/audit-report").status_code == 404
    assert api_client.get(f"/api/v1/jobs/{job_id}/artifacts/{artifact_id}").status_code == 404
    # Repeat delete is safe not-found.
    again = api_client.delete(f"/api/v1/jobs/{job_id}")
    assert again.status_code == 404


def test_expired_result_unavailable(api_client: TestClient, db_session: Session) -> None:
    job_id = _upload_pdf(
        api_client,
        make_pdf_with_text([f"Email {FICTIONAL_EMAIL} with enough filler content words"]),
    )
    from uuid import UUID

    from app.models.processing_job import ProcessingJob

    job = db_session.get(ProcessingJob, UUID(job_id))
    assert job is not None
    job.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    result = api_client.get(f"/api/v1/jobs/{job_id}/result")
    assert result.status_code == 410
    assert result.json()["error"]["code"] == "JOB_EXPIRED"
    audit = api_client.get(f"/api/v1/jobs/{job_id}/audit-report")
    assert audit.status_code == 410
    assert audit.json()["error"]["code"] == "JOB_EXPIRED"


def test_artifact_download_cache_headers(api_client: TestClient) -> None:
    job_id, anon = _complete_pdf_job(api_client)
    artifact_id = anon["artifact"]["artifact_id"]
    download = api_client.get(f"/api/v1/jobs/{job_id}/artifacts/{artifact_id}")
    assert download.status_code == 200
    assert "no-store" in download.headers.get("cache-control", "")
    assert "nosniff" in download.headers.get("x-content-type-options", "").lower()
    assert "anonymized-document.pdf" in download.headers.get("content-disposition", "")
