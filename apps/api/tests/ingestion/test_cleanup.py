"""Cleanup and reconciliation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from app.models.processing_job import ProcessingJob
from app.services.ingestion.cleanup import cleanup_expired_jobs, reconcile_orphaned_files
from app.services.ingestion.clock import FixedClock
from app.services.ingestion.upload import ingest_upload
from tests.helpers.fictional_files import make_fictional_pdf_bytes


def _upload(name: str, data: bytes) -> UploadFile:
    return UploadFile(
        filename=name,
        file=BytesIO(data),
        headers=Headers({"content-type": "application/pdf"}),
    )


def test_cleanup_expired_removes_file_and_row(db_session: Session, temp_upload_dir: Path) -> None:
    start = FixedClock(datetime(2026, 8, 3, 12, 0, tzinfo=UTC))
    uploaded = ingest_upload(
        db_session,
        _upload("ok.pdf", make_fictional_pdf_bytes()),
        clock=start,
        root=temp_upload_dir,
    )
    key = uploaded.job.storage_key
    assert (temp_upload_dir / key).exists()

    later = FixedClock(datetime(2026, 8, 3, 14, 0, tzinfo=UTC))
    removed = cleanup_expired_jobs(db_session, clock=later, root=temp_upload_dir)
    assert removed == 1
    assert not (temp_upload_dir / key).exists()
    assert db_session.get(ProcessingJob, uploaded.job.id) is None


def test_reconcile_orphans_and_quarantine(db_session: Session, temp_upload_dir: Path) -> None:
    orphan = temp_upload_dir / ("a" * 32 + ".pdf")
    orphan.write_bytes(b"%PDF-1.4 fictional orphan")
    quarantine = temp_upload_dir / ".quarantine-deadbeef"
    quarantine.write_bytes(b"partial")
    keep = temp_upload_dir / "not-our-pattern.txt"
    keep.write_bytes(b"keep")

    removed = reconcile_orphaned_files(db_session, root=temp_upload_dir)
    assert removed >= 2
    assert not orphan.exists()
    assert not quarantine.exists()
    assert keep.exists()


def test_reconcile_path_containment(db_session: Session, temp_upload_dir: Path) -> None:
    sibling = temp_upload_dir.parent / "outside-uploads"
    sibling.mkdir(exist_ok=True)
    marker = sibling / ("b" * 32 + ".pdf")
    marker.write_bytes(b"must-remain")
    removed = reconcile_orphaned_files(db_session, root=temp_upload_dir)
    assert removed == 0
    assert marker.exists()


def test_cleanup_missing_file_still_removes_row(db_session: Session, temp_upload_dir: Path) -> None:
    start = FixedClock(datetime(2026, 8, 3, 12, 0, tzinfo=UTC))
    uploaded = ingest_upload(
        db_session,
        _upload("ok.pdf", make_fictional_pdf_bytes()),
        clock=start,
        root=temp_upload_dir,
    )
    (temp_upload_dir / uploaded.job.storage_key).unlink()
    later = FixedClock(start.now() + timedelta(hours=2))
    removed = cleanup_expired_jobs(db_session, clock=later, root=temp_upload_dir)
    assert removed == 1
    assert db_session.get(ProcessingJob, uploaded.job.id) is None
