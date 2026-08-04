"""API tests for document upload and job lifecycle."""

from __future__ import annotations

import uuid
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.processing_job import ProcessingJob
from tests.helpers.fictional_files import (
    make_fictional_jpeg_bytes,
    make_fictional_pdf_bytes,
    make_fictional_png_bytes,
    pe_header_bytes,
    zip_header_bytes,
)


def test_upload_pdf_png_jpeg_and_get_delete(api_client: TestClient, db_session: Session) -> None:
    pdf_resp = api_client.post(
        "/api/v1/documents",
        files={"file": ("fictional.pdf", make_fictional_pdf_bytes(), "application/pdf")},
    )
    assert pdf_resp.status_code == 201, pdf_resp.text
    body = pdf_resp.json()
    assert body["status"] == "pending"
    assert body["file_type"] == "pdf"
    assert body["page_count"] == 1
    assert "storage_key" not in body
    assert "storage_path" not in body
    assert "/tmp" not in pdf_resp.text
    assert "fictional.pdf" not in pdf_resp.text
    job_id = body["job_id"]

    job = db_session.get(ProcessingJob, UUID(job_id))
    assert job is not None
    assert "original_filename" not in ProcessingJob.__table__.columns.keys()
    assert "fictional.pdf" not in job.storage_key

    png_resp = api_client.post(
        "/api/v1/documents",
        files={"file": ("pixel.png", make_fictional_png_bytes(), "image/png")},
    )
    assert png_resp.status_code == 201
    assert png_resp.json()["image_width"] == 32

    jpg_resp = api_client.post(
        "/api/v1/documents",
        files={"file": ("shot.jpg", make_fictional_jpeg_bytes(), "image/jpeg")},
    )
    assert jpg_resp.status_code == 201
    assert jpg_resp.json()["file_type"] == "jpeg"

    jpeg_resp = api_client.post(
        "/api/v1/documents",
        files={"file": ("shot.jpeg", make_fictional_jpeg_bytes(), "image/jpeg")},
    )
    assert jpeg_resp.status_code == 201
    assert jpeg_resp.json()["file_type"] == "jpeg"

    get_resp = api_client.get(f"/api/v1/jobs/{job_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["job_id"] == job_id
    assert "storage_key" not in get_resp.json()

    delete_resp = api_client.delete(f"/api/v1/jobs/{job_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True

    missing = api_client.get(f"/api/v1/jobs/{job_id}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "JOB_NOT_FOUND"

    delete_again = api_client.delete(f"/api/v1/jobs/{job_id}")
    assert delete_again.status_code == 404


def test_reject_empty_unsupported_and_archives(api_client: TestClient) -> None:
    empty = api_client.post(
        "/api/v1/documents",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "EMPTY_FILE"

    txt = api_client.post(
        "/api/v1/documents",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert txt.status_code == 400
    assert txt.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    pe = api_client.post(
        "/api/v1/documents",
        files={"file": ("fake.pdf", pe_header_bytes(), "application/pdf")},
    )
    assert pe.status_code == 400
    assert pe.json()["error"]["code"] == "EXECUTABLE_CONTENT_REJECTED"
    assert "MZ" not in pe.text

    zipped = api_client.post(
        "/api/v1/documents",
        files={"file": ("archive.pdf", zip_header_bytes(), "application/pdf")},
    )
    assert zipped.status_code == 400
    assert zipped.json()["error"]["code"] == "ARCHIVE_CONTENT_REJECTED"


def test_reject_signature_mismatch_and_traversal_filename(api_client: TestClient) -> None:
    mismatch = api_client.post(
        "/api/v1/documents",
        files={"file": ("fake.png", make_fictional_pdf_bytes(), "image/png")},
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["error"]["code"] == "FILE_SIGNATURE_MISMATCH"

    traversal = api_client.post(
        "/api/v1/documents",
        files={"file": ("../../escape.pdf", make_fictional_pdf_bytes(), "application/pdf")},
    )
    assert traversal.status_code == 201
    assert "storage_key" not in traversal.json()
    assert ".." not in traversal.text


def test_fictional_pii_filename_not_in_response(api_client: TestClient) -> None:
    fictional = "Bob_Jones_DOB_1990-01-01.pdf"
    response = api_client.post(
        "/api/v1/documents",
        files={"file": (fictional, make_fictional_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 201
    assert fictional not in response.text
    assert "Bob_Jones" not in response.text
    assert "storage_key" not in response.json()


def test_unknown_and_malformed_job(api_client: TestClient) -> None:
    unknown = api_client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert unknown.status_code == 404
    malformed = api_client.get("/api/v1/jobs/not-a-uuid")
    assert malformed.status_code == 422

    delete_unknown = api_client.delete(f"/api/v1/jobs/{uuid.uuid4()}")
    assert delete_unknown.status_code == 404
