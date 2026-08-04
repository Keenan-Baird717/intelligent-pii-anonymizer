from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models.generated_artifact import GeneratedArtifact
from app.models.processing_job import ProcessingJob
from app.services.ingestion.clock import Clock, SystemClock
from app.services.ingestion.storage import (
    delete_stored_file,
    ensure_upload_directory,
    is_managed_filename,
    safe_unlink,
)

logger = get_logger(__name__)


def _delete_artifact_files_for_job(
    db: Session,
    job_id: UUID,
    *,
    root: Path | None = None,
) -> None:
    keys = list(
        db.scalars(
            select(GeneratedArtifact.storage_key).where(
                GeneratedArtifact.processing_job_id == job_id
            )
        ).all()
    )
    for key in keys:
        try:
            delete_stored_file(key, root=root)
        except Exception:
            logger.error(
                "cleanup_artifact_file_failure",
                job_id=str(job_id),
                error_code="DELETE_FAILED",
            )


def cleanup_expired_jobs(
    db: Session,
    *,
    clock: Clock | None = None,
    root: Path | None = None,
) -> int:
    clock = clock or SystemClock()
    now = clock.now()
    removed = 0
    jobs = db.scalars(select(ProcessingJob)).all()
    for job in jobs:
        expires_at = job.expires_at
        if expires_at.tzinfo is None:
            from datetime import UTC

            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at > now:
            continue
        try:
            _delete_artifact_files_for_job(db, job.id, root=root)
            try:
                from app.processing.ocr.workfiles import cleanup_job_ocr_work

                cleanup_job_ocr_work(str(job.id), root=None)
            except Exception:
                logger.error(
                    "cleanup_ocr_work_failure",
                    job_id=str(job.id),
                    error_code="DELETE_FAILED",
                )
            try:
                delete_stored_file(job.storage_key, root=root)
            except Exception:
                logger.error(
                    "cleanup_file_failure",
                    job_id=str(job.id),
                    error_code="DELETE_FAILED",
                )
            db.delete(job)
            db.commit()
            removed += 1
        except Exception:
            db.rollback()
            logger.error(
                "cleanup_job_failure",
                job_id=str(job.id),
                error_code="DELETE_FAILED",
            )
    if removed:
        logger.info("cleanup_expired_removed", removed_count=removed)
    return removed


def reconcile_orphaned_files(
    db: Session,
    *,
    root: Path | None = None,
) -> int:
    """Remove randomized files with no matching job or artifact row."""
    base = ensure_upload_directory(root)
    known_keys = set(db.scalars(select(ProcessingJob.storage_key)).all())
    known_keys.update(db.scalars(select(GeneratedArtifact.storage_key)).all())
    removed = 0
    for entry in base.iterdir():
        name = entry.name
        if name.startswith(".quarantine-"):
            # Quarantine leftovers under the controlled root only.
            if entry.is_file() or entry.is_symlink():
                safe_unlink(entry)
                removed += 1
            continue
        if name.startswith("."):
            continue
        if not is_managed_filename(name):
            # Never delete arbitrary files outside the generated-name format.
            continue
        if name not in known_keys and (entry.is_file() or entry.is_symlink()):
            safe_unlink(entry)
            removed += 1
    if removed:
        logger.info("cleanup_orphan_removed", removed_count=removed)
    return removed


def startup_reconciliation(*, clock: Clock | None = None, root: Path | None = None) -> None:
    ensure_upload_directory(root)
    db = SessionLocal()
    try:
        cleanup_expired_jobs(db, clock=clock, root=root)
        reconcile_orphaned_files(db, root=root)
        try:
            from app.processing.ocr.workfiles import reconcile_abandoned_ocr_files

            known = {str(job_id) for job_id in db.scalars(select(ProcessingJob.id)).all()}
            reconcile_abandoned_ocr_files(known_job_ids=known)
        except Exception:
            logger.error("ocr_workfile_reconcile_failure", error_code="TEMPORARY_WORK_FILE_FAILURE")
    finally:
        db.close()


async def cleanup_loop(stop_event: asyncio.Event) -> None:
    interval = settings.upload_cleanup_interval_seconds
    if not settings.upload_cleanup_enabled or interval <= 0:
        await stop_event.wait()
        return
    while not stop_event.is_set():
        try:
            db = SessionLocal()
            try:
                cleanup_expired_jobs(db)
            finally:
                db.close()
        except Exception:
            logger.error("cleanup_loop_failure", error_code="DELETE_FAILED")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            continue
