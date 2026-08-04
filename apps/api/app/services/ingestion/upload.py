from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, timedelta
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.concurrency import job_locks, upload_slot
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.processing_job import JobStatus, ProcessingJob, SourceType, ValidatedFileType
from app.services.ingestion.clock import Clock, SystemClock
from app.services.ingestion.file_types import (
    SIGNATURE_TO_TYPE,
    canonical_extension,
    resolve_client_hints,
)
from app.services.ingestion.image_validation import validate_image
from app.services.ingestion.pdf_validation import validate_pdf
from app.services.ingestion.signatures import EXECUTABLE_OR_ARCHIVE, DetectedKind, detect_signature
from app.services.ingestion.storage import (
    delete_stored_file,
    generate_storage_key,
    promote_quarantine,
    safe_unlink,
    write_stream_to_quarantine,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class UploadResult:
    job: ProcessingJob


def _iter_upload_chunks(upload: UploadFile, chunk_size: int) -> Iterator[bytes]:
    while True:
        chunk = upload.file.read(chunk_size)
        if not chunk:
            break
        yield chunk


def ingest_upload(
    db: Session,
    upload: UploadFile,
    *,
    clock: Clock | None = None,
    root: Path | None = None,
) -> UploadResult:
    with upload_slot():
        return _ingest_upload_inner(db, upload, clock=clock, root=root)


def _ingest_upload_inner(
    db: Session,
    upload: UploadFile,
    *,
    clock: Clock | None = None,
    root: Path | None = None,
) -> UploadResult:
    clock = clock or SystemClock()
    quarantine_path: Path | None = None
    storage_key: str | None = None

    try:
        hints = resolve_client_hints(upload.filename, upload.content_type)
        quarantine_path, byte_size, header = write_stream_to_quarantine(
            _iter_upload_chunks(upload, settings.upload_stream_chunk_bytes),
            max_bytes=settings.max_upload_bytes,
            chunk_size=settings.upload_stream_chunk_bytes,
            root=root,
        )

        signature = detect_signature(header)
        if signature.kind is DetectedKind.empty:
            raise AppError(
                code="EMPTY_FILE", message="The uploaded file is empty.", status_code=400
            )
        if signature.kind in EXECUTABLE_OR_ARCHIVE:
            code = (
                "EXECUTABLE_CONTENT_REJECTED"
                if signature.kind in {DetectedKind.pe, DetectedKind.elf}
                else "ARCHIVE_CONTENT_REJECTED"
            )
            raise AppError(
                code=code,
                message="The uploaded content type is not allowed.",
                status_code=400,
            )
        if signature.kind is DetectedKind.unknown:
            raise AppError(
                code="FILE_SIGNATURE_MISMATCH",
                message="The file signature could not be verified.",
                status_code=400,
            )

        signature_type = SIGNATURE_TO_TYPE.get(signature.kind)
        if signature_type is None or signature_type != hints.file_type:
            raise AppError(
                code="FILE_SIGNATURE_MISMATCH",
                message="The file signature does not match the declared type.",
                status_code=400,
            )

        page_count: int | None = None
        image_width: int | None = None
        image_height: int | None = None

        if hints.file_type is ValidatedFileType.pdf:
            pdf_result = validate_pdf(quarantine_path)
            page_count = pdf_result.page_count
        else:
            image_result = validate_image(quarantine_path, hints.file_type)
            image_width = image_result.width
            image_height = image_result.height

        extension = canonical_extension(hints.file_type, hints.extension)
        storage_key = generate_storage_key(extension)
        promote_quarantine(quarantine_path, storage_key, root=root)
        quarantine_path = None

        now = clock.now()
        job = ProcessingJob(
            source_type=SourceType.document,
            status=JobStatus.pending,
            validated_file_type=hints.file_type,
            validated_extension=extension.lstrip("."),
            validated_mime_type=hints.mime_type,
            byte_size=byte_size,
            page_count=page_count,
            image_width=image_width,
            image_height=image_height,
            storage_key=storage_key,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(minutes=settings.upload_ttl_minutes),
        )
        try:
            db.add(job)
            db.commit()
            db.refresh(job)
        except SQLAlchemyError as exc:
            db.rollback()
            if storage_key:
                delete_stored_file(storage_key, root=root)
            logger.error("job_persist_failure", error_code="STORAGE_FAILURE")
            raise AppError(
                code="STORAGE_FAILURE",
                message="The upload could not be stored.",
                status_code=500,
            ) from exc

        logger.info(
            "document_upload_success",
            job_id=str(job.id),
            validated_file_type=job.validated_file_type.value,
            byte_size=job.byte_size,
            page_count=job.page_count,
            image_width=job.image_width,
            image_height=job.image_height,
            status=job.status.value,
        )
        return UploadResult(job=job)
    except AppError:
        safe_unlink(quarantine_path)
        if storage_key and quarantine_path is None:
            # File may already have been promoted; delete on failure paths that reach here
            # after promotion but before successful commit (handled above). For pre-commit
            # AppErrors after promote, clean up.
            try:
                delete_stored_file(storage_key, root=root)
            except AppError:
                pass
        raise
    except Exception as exc:
        safe_unlink(quarantine_path)
        logger.error("document_upload_unexpected", error_code="STORAGE_FAILURE")
        raise AppError(
            code="STORAGE_FAILURE",
            message="The upload could not be stored.",
            status_code=500,
        ) from exc
    finally:
        try:
            upload.file.close()
        except Exception:
            pass


def get_job(db: Session, job_id: UUID, *, clock: Clock | None = None) -> ProcessingJob:
    clock = clock or SystemClock()
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise AppError(code="JOB_NOT_FOUND", message="Job not found.", status_code=404)
    expires_at = job.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= clock.now():
        raise AppError(code="JOB_EXPIRED", message="This job has expired.", status_code=410)
    return job


def delete_job(
    db: Session, job_id: UUID, *, clock: Clock | None = None, root: Path | None = None
) -> None:
    with job_locks.acquire(str(job_id), "delete"):
        _delete_job_inner(db, job_id, clock=clock, root=root)


def _delete_job_inner(
    db: Session, job_id: UUID, *, clock: Clock | None = None, root: Path | None = None
) -> None:
    clock = clock or SystemClock()
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise AppError(code="JOB_NOT_FOUND", message="Job not found.", status_code=404)
    # Expired jobs are still deletable to allow cleanup; treat missing as not found after delete.
    storage_key = job.storage_key
    from sqlalchemy import select

    from app.models.generated_artifact import GeneratedArtifact

    artifact_keys = list(
        db.scalars(
            select(GeneratedArtifact.storage_key).where(
                GeneratedArtifact.processing_job_id == job.id
            )
        ).all()
    )
    for key in artifact_keys:
        try:
            delete_stored_file(key, root=root)
        except AppError:
            raise
    try:
        from app.processing.ocr.workfiles import cleanup_job_ocr_work

        cleanup_job_ocr_work(str(job.id))
    except Exception:
        logger.error("job_ocr_cleanup_failure", job_id=str(job.id), error_code="DELETE_FAILED")
    try:
        delete_stored_file(storage_key, root=root)
    except AppError:
        raise
    try:
        db.delete(job)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("job_delete_failure", error_code="DELETE_FAILED")
        raise AppError(
            code="DELETE_FAILED",
            message="The job could not be deleted.",
            status_code=500,
        ) from exc
    logger.info(
        "document_delete_success",
        job_id=str(job_id),
        validated_file_type=job.validated_file_type.value,
        byte_size=job.byte_size,
    )
    _ = clock  # reserved for future TTL checks on delete
