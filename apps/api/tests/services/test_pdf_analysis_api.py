"""Phase 5 PDF analyze / review / anonymize API tests."""

from __future__ import annotations

import uuid
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.detected_entity import DetectedEntity
from app.models.generated_artifact import GeneratedArtifact
from app.models.processing_job import ProcessingJob
from app.services.ingestion.storage import resolve_storage_path
from tests.helpers.fictional_files import (
    make_fictional_pdf_bytes,
    make_image_only_pdf,
    make_pdf_with_text,
)

FICTIONAL_EMAIL = "fictional.user@example.com"
FICTIONAL_PHONE = "902-555-0182"


class _CapturingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def _capture(self, event: str, **kwargs: object) -> None:
        self.events.append((event, dict(kwargs)))

    def info(self, event: str, **kwargs: object) -> None:
        self._capture(event, **kwargs)

    def error(self, event: str, **kwargs: object) -> None:
        self._capture(event, **kwargs)

    def warning(self, event: str, **kwargs: object) -> None:
        self._capture(event, **kwargs)

    def debug(self, event: str, **kwargs: object) -> None:
        self._capture(event, **kwargs)


def _upload_pdf(api_client: TestClient, data: bytes, name: str = "memo.pdf") -> str:
    response = api_client.post(
        "/api/v1/documents",
        files={"file": (name, data, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()["job_id"]


def _pdf_plain_text(pdf_bytes: bytes) -> str:
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return "\n".join(
            document.load_page(index).get_text("text") for index in range(document.page_count)
        )
    finally:
        document.close()


def test_analyze_pdf_with_email(api_client: TestClient, db_session: Session) -> None:
    job_id = _upload_pdf(
        api_client,
        make_pdf_with_text(
            [f"Contact Alice Example at {FICTIONAL_EMAIL} for the fictional report summary"]
        ),
    )

    analyze = api_client.post(f"/api/v1/jobs/{job_id}/analyze")
    assert analyze.status_code == 200, analyze.text
    body = analyze.json()
    assert body["status"] == "awaiting_review"
    assert body["detection_count"] >= 1
    assert "storage_key" not in body

    email_entities = [
        entity
        for entity in body["entities"]
        if entity["entity_type"] == "EMAIL_ADDRESS" and entity.get("text") == FICTIONAL_EMAIL
    ]
    assert email_entities
    assert email_entities[0]["page_number"] == 1
    assert email_entities[0]["rectangles"]

    # DetectedEntity must not persist the substring.
    rows = list(db_session.scalars(select(DetectedEntity)).all())
    assert rows
    column_names = {column.name for column in DetectedEntity.__table__.columns}
    assert "text" not in column_names
    assert "original_text" not in column_names
    assert "value" not in column_names


def test_accept_reject_anonymize_download_verifies_output(
    api_client: TestClient,
) -> None:
    job_id = _upload_pdf(
        api_client,
        make_pdf_with_text(
            [
                f"Email {FICTIONAL_EMAIL} phone {FICTIONAL_PHONE} "
                f"and enough filler words for extraction threshold"
            ]
        ),
    )
    analyze = api_client.post(f"/api/v1/jobs/{job_id}/analyze")
    assert analyze.status_code == 200, analyze.text
    entities = analyze.json()["entities"]

    email = next(e for e in entities if e["entity_type"] == "EMAIL_ADDRESS")
    phone = next(e for e in entities if e["entity_type"] == "PHONE_NUMBER")
    assert email["text"] == FICTIONAL_EMAIL
    assert phone["text"] == FICTIONAL_PHONE

    accepted = api_client.patch(
        f"/api/v1/jobs/{job_id}/entities/{email['id']}",
        json={"review_status": "accepted"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["review_status"] == "accepted"

    rejected = api_client.patch(
        f"/api/v1/jobs/{job_id}/entities/{phone['id']}",
        json={"review_status": "rejected"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["review_status"] == "rejected"

    anonymize = api_client.post(
        f"/api/v1/jobs/{job_id}/anonymize",
        json={"default_method": "redaction"},
    )
    assert anonymize.status_code == 200, anonymize.text
    art = anonymize.json()
    assert art["status"] == "completed"
    assert art["redacted_count"] >= 1
    assert art["rejected_count"] >= 1
    artifact_id = art["artifact"]["artifact_id"]

    download = api_client.get(f"/api/v1/jobs/{job_id}/artifacts/{artifact_id}")
    assert download.status_code == 200
    assert "attachment" in download.headers.get("content-disposition", "").lower()
    assert download.headers.get("x-content-type-options") == "nosniff"

    output_text = _pdf_plain_text(download.content)
    assert FICTIONAL_EMAIL not in output_text
    assert FICTIONAL_PHONE in output_text


def test_manual_rectangle_create_and_redact(api_client: TestClient) -> None:
    marker = "MANUALREDACTME"
    job_id = _upload_pdf(
        api_client,
        make_pdf_with_text([f"KeepVisible {marker} and more fictional words here"]),
    )
    analyze = api_client.post(f"/api/v1/jobs/{job_id}/analyze")
    assert analyze.status_code == 200, analyze.text

    # Locate the marker via source file word boxes for a precise manual rectangle.
    source = api_client.get(f"/api/v1/jobs/{job_id}/file")
    assert source.status_code == 200
    document = fitz.open(stream=source.content, filetype="pdf")
    try:
        page = document.load_page(0)
        words = page.get_text("words")
        target = next(word for word in words if word[4] == marker)
        x0, y0, x1, y1 = float(target[0]), float(target[1]), float(target[2]), float(target[3])
    finally:
        document.close()

    created = api_client.post(
        f"/api/v1/jobs/{job_id}/entities",
        json={
            "entity_type": "OTHER",
            "page_number": 1,
            "rectangle": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["manually_added"] is True
    assert created.json()["review_status"] == "manually_added"

    anonymize = api_client.post(
        f"/api/v1/jobs/{job_id}/anonymize",
        json={"default_method": "redaction"},
    )
    assert anonymize.status_code == 200, anonymize.text
    artifact_id = anonymize.json()["artifact"]["artifact_id"]
    download = api_client.get(f"/api/v1/jobs/{job_id}/artifacts/{artifact_id}")
    assert download.status_code == 200
    output_text = _pdf_plain_text(download.content)
    assert marker not in output_text
    assert "KeepVisible" in output_text


def test_artifact_wrong_job_404(api_client: TestClient) -> None:
    job_a = _upload_pdf(
        api_client,
        make_pdf_with_text([f"Email {FICTIONAL_EMAIL} with enough filler content words"]),
        name="a.pdf",
    )
    job_b = _upload_pdf(
        api_client,
        make_fictional_pdf_bytes(text="Second fictional document content"),
        name="b.pdf",
    )

    analyze = api_client.post(f"/api/v1/jobs/{job_a}/analyze")
    assert analyze.status_code == 200
    email = next(
        entity for entity in analyze.json()["entities"] if entity["entity_type"] == "EMAIL_ADDRESS"
    )
    api_client.patch(
        f"/api/v1/jobs/{job_a}/entities/{email['id']}",
        json={"review_status": "accepted"},
    )
    anonymize = api_client.post(
        f"/api/v1/jobs/{job_a}/anonymize",
        json={"default_method": "redaction"},
    )
    assert anonymize.status_code == 200, anonymize.text
    artifact_id = anonymize.json()["artifact"]["artifact_id"]

    wrong = api_client.get(f"/api/v1/jobs/{job_b}/artifacts/{artifact_id}")
    assert wrong.status_code == 404
    assert wrong.json()["error"]["code"] == "ARTIFACT_NOT_FOUND"

    missing = api_client.get(f"/api/v1/jobs/{job_a}/artifacts/{uuid.uuid4()}")
    assert missing.status_code == 404


def test_delete_job_removes_source_and_artifact_files(
    api_client: TestClient,
    db_session: Session,
    temp_upload_dir: Path,
) -> None:
    job_id = _upload_pdf(
        api_client,
        make_pdf_with_text([f"Email {FICTIONAL_EMAIL} with enough filler content words"]),
    )
    analyze = api_client.post(f"/api/v1/jobs/{job_id}/analyze")
    assert analyze.status_code == 200
    email = next(
        entity for entity in analyze.json()["entities"] if entity["entity_type"] == "EMAIL_ADDRESS"
    )
    api_client.patch(
        f"/api/v1/jobs/{job_id}/entities/{email['id']}",
        json={"review_status": "accepted"},
    )
    anonymize = api_client.post(
        f"/api/v1/jobs/{job_id}/anonymize",
        json={"default_method": "redaction"},
    )
    assert anonymize.status_code == 200, anonymize.text

    job = db_session.get(ProcessingJob, uuid.UUID(job_id))
    assert job is not None
    source_key = job.storage_key
    artifact = db_session.scalars(
        select(GeneratedArtifact).where(GeneratedArtifact.processing_job_id == job.id)
    ).one()
    artifact_key = artifact.storage_key
    source_path = resolve_storage_path(source_key, root=temp_upload_dir)
    artifact_path = resolve_storage_path(artifact_key, root=temp_upload_dir)
    assert source_path.exists()
    assert artifact_path.exists()

    deleted = api_client.delete(f"/api/v1/jobs/{job_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert not source_path.exists()
    assert not artifact_path.exists()
    assert api_client.get(f"/api/v1/jobs/{job_id}").status_code == 404


def test_analyze_ocr_required_when_ocr_disabled(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "ocr_enabled", False)
    job_id = _upload_pdf(api_client, make_image_only_pdf(), name="scan.pdf")
    analyze = api_client.post(f"/api/v1/jobs/{job_id}/analyze")
    assert analyze.status_code == 422
    assert analyze.json()["error"]["code"] == "OCR_REQUIRED"


def test_logging_safety_excludes_extracted_email(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    analysis_logger = _CapturingLogger()
    extract_logger = _CapturingLogger()
    detection_logger = _CapturingLogger()
    monkeypatch.setattr("app.services.document_analysis.logger", analysis_logger)
    monkeypatch.setattr("app.processing.pdf.extract.logger", extract_logger)
    monkeypatch.setattr("app.processing.detection.pipeline.logger", detection_logger)

    job_id = _upload_pdf(
        api_client,
        make_pdf_with_text(
            [f"Reach {FICTIONAL_EMAIL} with enough filler content for the threshold"]
        ),
    )
    analyze = api_client.post(f"/api/v1/jobs/{job_id}/analyze")
    assert analyze.status_code == 200, analyze.text

    blob = (
        repr(analysis_logger.events)
        + repr(extract_logger.events)
        + repr(detection_logger.events)
        + capsys.readouterr().out
        + capsys.readouterr().err
    )
    assert FICTIONAL_EMAIL not in blob
    assert "fictional.user" not in blob


def test_manual_entity_delete_only(api_client: TestClient) -> None:
    job_id = _upload_pdf(api_client, make_fictional_pdf_bytes())
    api_client.post(f"/api/v1/jobs/{job_id}/analyze")

    created = api_client.post(
        f"/api/v1/jobs/{job_id}/entities",
        json={
            "entity_type": "OTHER",
            "page_number": 1,
            "rectangle": {"x0": 10, "y0": 10, "x1": 100, "y1": 40},
        },
    )
    assert created.status_code == 201, created.text
    entity_id = created.json()["id"]
    assert created.json()["text"] in ("", None)

    deleted = api_client.delete(f"/api/v1/jobs/{job_id}/entities/{entity_id}")
    assert deleted.status_code == 204
