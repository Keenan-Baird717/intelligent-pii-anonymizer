"""Service-level upload ingestion tests with fictional fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO

import pytest
from fastapi import UploadFile
from sqlalchemy import select
from starlette.datastructures import Headers

from app.core.errors import AppError
from app.models.processing_job import ProcessingJob
from app.services.ingestion.clock import FixedClock
from app.services.ingestion.upload import delete_job, get_job, ingest_upload
from tests.helpers.fictional_files import (
    corrupt_pdf_bytes,
    gzip_header_bytes,
    make_fictional_jpeg_bytes,
    make_fictional_pdf_bytes,
    make_fictional_png_bytes,
    make_password_protected_pdf_bytes,
    pe_header_bytes,
    rar_header_bytes,
    seven_z_header_bytes,
    zip_header_bytes,
)


def _upload(filename: str, content_type: str, data: bytes) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=BytesIO(data),
        headers=Headers({"content-type": content_type}),
    )


def test_valid_pdf_png_jpeg_uploads(db_session, temp_upload_dir) -> None:
    clock = FixedClock(datetime(2026, 8, 3, 12, 0, tzinfo=UTC))
    pdf = ingest_upload(
        db_session,
        _upload("fictional-report.pdf", "application/pdf", make_fictional_pdf_bytes()),
        clock=clock,
        root=temp_upload_dir,
    )
    assert pdf.job.validated_file_type.value == "pdf"
    assert pdf.job.page_count == 1
    assert pdf.job.status.value == "pending"
    assert (temp_upload_dir / pdf.job.storage_key).is_file()

    png = ingest_upload(
        db_session,
        _upload("pixel.png", "image/png", make_fictional_png_bytes()),
        clock=clock,
        root=temp_upload_dir,
    )
    assert png.job.image_width == 32
    assert png.job.image_height == 24

    jpg = ingest_upload(
        db_session,
        _upload("shot.jpg", "image/jpeg", make_fictional_jpeg_bytes()),
        clock=clock,
        root=temp_upload_dir,
    )
    assert jpg.job.validated_extension == "jpg"

    jpeg = ingest_upload(
        db_session,
        _upload("shot.jpeg", "image/jpeg", make_fictional_jpeg_bytes()),
        clock=clock,
        root=temp_upload_dir,
    )
    assert jpeg.job.validated_extension == "jpeg"


@pytest.mark.parametrize(
    ("filename", "content_type", "data", "code"),
    [
        ("empty.pdf", "application/pdf", b"", "EMPTY_FILE"),
        ("notes.txt", "text/plain", b"hello", "UNSUPPORTED_FILE_TYPE"),
        ("a.pdf", "image/png", make_fictional_pdf_bytes(), "MIME_TYPE_MISMATCH"),
        ("a.png", "image/png", make_fictional_pdf_bytes(), "FILE_SIGNATURE_MISMATCH"),
        ("a.pdf", "application/pdf", make_fictional_png_bytes(), "FILE_SIGNATURE_MISMATCH"),
        ("virus.pdf", "application/pdf", pe_header_bytes(), "EXECUTABLE_CONTENT_REJECTED"),
        ("pack.pdf", "application/pdf", zip_header_bytes(), "ARCHIVE_CONTENT_REJECTED"),
        ("pack.pdf", "application/pdf", rar_header_bytes(), "ARCHIVE_CONTENT_REJECTED"),
        ("pack.pdf", "application/pdf", seven_z_header_bytes(), "ARCHIVE_CONTENT_REJECTED"),
        ("pack.pdf", "application/pdf", gzip_header_bytes(), "ARCHIVE_CONTENT_REJECTED"),
        ("bad.pdf", "application/pdf", corrupt_pdf_bytes(), "CORRUPT_PDF"),
        (
            "locked.pdf",
            "application/pdf",
            make_password_protected_pdf_bytes(),
            "PASSWORD_PROTECTED_PDF",
        ),
    ],
)
def test_rejection_cases(db_session, temp_upload_dir, filename, content_type, data, code) -> None:
    before = list(temp_upload_dir.iterdir())
    with pytest.raises(AppError) as exc:
        ingest_upload(
            db_session,
            _upload(filename, content_type, data),
            root=temp_upload_dir,
        )
    assert exc.value.code == code
    assert list(db_session.scalars(select(ProcessingJob)).all()) == []
    # No durable files left (quarantine cleaned).
    leftovers = [p for p in temp_upload_dir.iterdir() if p not in before]
    assert leftovers == []


def test_path_traversal_and_pii_filename_still_stores_random_key(
    db_session, temp_upload_dir
) -> None:
    result = ingest_upload(
        db_session,
        _upload(
            r"..\..\CaseyOkafor\secret.pdf",
            "application/pdf",
            make_fictional_pdf_bytes(),
        ),
        root=temp_upload_dir,
    )
    assert "CaseyOkafor" not in result.job.storage_key
    assert ".." not in result.job.storage_key
    assert result.job.storage_key.endswith(".pdf")
    path = temp_upload_dir / result.job.storage_key
    assert path.resolve().is_relative_to(temp_upload_dir.resolve())


def test_double_extension_rejected(db_session, temp_upload_dir) -> None:
    with pytest.raises(AppError) as exc:
        ingest_upload(
            db_session,
            _upload("report.pdf.exe", "application/pdf", make_fictional_pdf_bytes()),
            root=temp_upload_dir,
        )
    assert exc.value.code == "UNSUPPORTED_FILE_TYPE"


def test_oversized_rejected(db_session, temp_upload_dir, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_upload_bytes", 64)
    with pytest.raises(AppError) as exc:
        ingest_upload(
            db_session,
            _upload("big.pdf", "application/pdf", make_fictional_pdf_bytes(pages=3)),
            root=temp_upload_dir,
        )
    assert exc.value.code == "FILE_TOO_LARGE"
    assert list(temp_upload_dir.iterdir()) == []


def test_pdf_page_limit(db_session, temp_upload_dir, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_pdf_pages", 1)
    with pytest.raises(AppError) as exc:
        ingest_upload(
            db_session,
            _upload("many.pdf", "application/pdf", make_fictional_pdf_bytes(pages=2)),
            root=temp_upload_dir,
        )
    assert exc.value.code == "PDF_PAGE_LIMIT_EXCEEDED"


def test_image_pixel_limit(db_session, temp_upload_dir, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_image_pixels", 100)
    with pytest.raises(AppError) as exc:
        ingest_upload(
            db_session,
            _upload("big.png", "image/png", make_fictional_png_bytes(width=50, height=50)),
            root=temp_upload_dir,
        )
    assert exc.value.code == "IMAGE_PIXEL_LIMIT_EXCEEDED"


def test_db_failure_removes_file(db_session, temp_upload_dir, monkeypatch) -> None:
    def boom() -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(db_session, "commit", boom)
    # SQLAlchemyError path — force SQLAlchemyError
    from sqlalchemy.exc import SQLAlchemyError

    def boom_sa() -> None:
        raise SQLAlchemyError("db down")

    monkeypatch.setattr(db_session, "commit", boom_sa)
    with pytest.raises(AppError) as exc:
        ingest_upload(
            db_session,
            _upload("ok.pdf", "application/pdf", make_fictional_pdf_bytes()),
            root=temp_upload_dir,
        )
    assert exc.value.code == "STORAGE_FAILURE"
    assert list(temp_upload_dir.iterdir()) == []


def test_get_delete_job_lifecycle(db_session, temp_upload_dir) -> None:
    clock = FixedClock(datetime(2026, 8, 3, 12, 0, tzinfo=UTC))
    uploaded = ingest_upload(
        db_session,
        _upload("ok.pdf", "application/pdf", make_fictional_pdf_bytes()),
        clock=clock,
        root=temp_upload_dir,
    )
    job = get_job(db_session, uploaded.job.id, clock=clock)
    assert job.id == uploaded.job.id
    storage_key = job.storage_key
    delete_job(db_session, job.id, clock=clock, root=temp_upload_dir)
    assert not (temp_upload_dir / storage_key).exists()
    with pytest.raises(AppError) as exc:
        get_job(db_session, uploaded.job.id, clock=clock)
    assert exc.value.code == "JOB_NOT_FOUND"


def test_expired_job_get(db_session, temp_upload_dir) -> None:
    start = FixedClock(datetime(2026, 8, 3, 12, 0, tzinfo=UTC))
    uploaded = ingest_upload(
        db_session,
        _upload("ok.pdf", "application/pdf", make_fictional_pdf_bytes()),
        clock=start,
        root=temp_upload_dir,
    )
    later = FixedClock(datetime(2026, 8, 3, 14, 0, tzinfo=UTC))
    with pytest.raises(AppError) as exc:
        get_job(db_session, uploaded.job.id, clock=later)
    assert exc.value.code == "JOB_EXPIRED"


def test_no_original_filename_on_model(db_session, temp_upload_dir) -> None:
    uploaded = ingest_upload(
        db_session,
        _upload("CaseyOkafor-fictional.pdf", "application/pdf", make_fictional_pdf_bytes()),
        root=temp_upload_dir,
    )
    columns = set(uploaded.job.__table__.columns.keys())
    assert "original_filename" not in columns
    assert "filename" not in columns
