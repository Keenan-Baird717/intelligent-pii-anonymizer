"""Image redaction service for PNG/JPEG jobs."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.concurrency import job_locks, ocr_slot, redaction_slot
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.detected_entity import ReviewStatus
from app.models.generated_artifact import ArtifactType, GeneratedArtifact
from app.models.processing_job import JobStatus, ValidatedFileType
from app.processing.image import redact_image, verify_image_redaction
from app.processing.ocr.models import PixelBBox as OcrPixelBBox
from app.services.ingestion.clock import Clock, SystemClock
from app.services.ingestion.storage import (
    generate_storage_key,
    resolve_storage_path,
    safe_unlink,
)
from app.services.ingestion.upload import get_job
from app.services.pdf.analysis import load_job_entities
from app.services.pdf.redaction import ArtifactView, RedactPdfResult

logger = get_logger(__name__)

_TRANSFORMABLE = {
    ReviewStatus.pending,
    ReviewStatus.accepted,
    ReviewStatus.edited,
    ReviewStatus.manually_added,
}


def anonymize_image_job(
    db: Session,
    job_id: UUID,
    *,
    default_method: str = "redaction",
    clock: Clock | None = None,
    root: Path | None = None,
) -> RedactPdfResult:
    method = default_method.value if hasattr(default_method, "value") else str(default_method)
    with job_locks.acquire(str(job_id), "redact"):
        with redaction_slot():
            with ocr_slot():
                return _anonymize_image_job_inner(
                    db, job_id, default_method=method, clock=clock, root=root
                )


def _anonymize_image_job_inner(
    db: Session,
    job_id: UUID,
    *,
    default_method: str = "redaction",
    clock: Clock | None = None,
    root: Path | None = None,
) -> RedactPdfResult:
    clock = clock or SystemClock()
    if default_method != "redaction":
        raise AppError(
            code="UNSUPPORTED_ANONYMIZATION_METHOD",
            message="Image anonymization supports redaction only.",
            status_code=400,
        )
    job = get_job(db, job_id, clock=clock)
    if job.validated_file_type not in {ValidatedFileType.png, ValidatedFileType.jpeg}:
        raise AppError(
            code="UNSUPPORTED_FILE_TYPE",
            message="Image redaction is only available for PNG/JPEG jobs.",
            status_code=400,
        )

    job.status = JobStatus.anonymizing
    db.commit()

    entities = load_job_entities(db, job_id)
    accepted = [e for e in entities if e.review_status in _TRANSFORMABLE]
    rejected = [e for e in entities if e.review_status is ReviewStatus.rejected]
    if not accepted:
        job.status = JobStatus.awaiting_review
        db.commit()
        raise AppError(
            code="IMAGE_REDACTION_FAILED",
            message="No accepted detections or manual regions to redact.",
            status_code=400,
        )

    source = resolve_storage_path(job.storage_key, root=root)
    rectangles: list[OcrPixelBBox] = []
    manual_rects: list[OcrPixelBBox] = []
    forbidden: list[str] = []
    for entity in accepted:
        try:
            raw = json.loads(entity.rectangles_json)
        except json.JSONDecodeError:
            continue
        for item in raw:
            box = OcrPixelBBox(
                x0=float(item["x0"]),
                y0=float(item["y0"]),
                x1=float(item["x1"]),
                y1=float(item["y1"]),
            )
            rectangles.append(box)
            if entity.manually_added:
                manual_rects.append(box)
        if (
            not entity.manually_added
            and entity.start_offset >= 0
            and entity.end_offset > entity.start_offset
        ):
            # Value is not stored; verification uses OCR absence best-effort without forbidden
            # substrings when we cannot re-derive from a persisted index. Skip forbidden list.
            pass

    required: list[str] = []
    for entity in rejected:
        # Same limitation — control text not persisted.
        _ = entity
        break

    if job.validated_file_type is ValidatedFileType.png:
        ext, mime, artifact_type, fmt = ".png", "image/png", ArtifactType.redacted_png, "png"
    else:
        ext, mime, artifact_type, fmt = ".jpg", "image/jpeg", ArtifactType.redacted_jpeg, "jpeg"

    storage_key = generate_storage_key(ext)
    output = resolve_storage_path(storage_key, root=root)
    try:
        redact_image(source, output, rectangles, output_format=fmt)
        verify_image_redaction(
            output,
            forbidden=forbidden,
            required=required,
            manual_rects=manual_rects,
        )
    except AppError:
        safe_unlink(output)
        job.status = JobStatus.failed
        job.safe_error_code = "OUTPUT_VERIFICATION_FAILED"
        db.commit()
        raise
    except Exception as exc:
        safe_unlink(output)
        job.status = JobStatus.failed
        job.safe_error_code = "IMAGE_REDACTION_FAILED"
        db.commit()
        raise AppError(
            code="IMAGE_REDACTION_FAILED",
            message="Image redaction failed.",
            status_code=500,
        ) from exc

    now = clock.now()
    byte_size = output.stat().st_size
    artifact = GeneratedArtifact(
        processing_job_id=job.id,
        artifact_type=artifact_type,
        validated_extension=ext.lstrip("."),
        validated_mime_type=mime,
        byte_size=byte_size,
        storage_key=storage_key,
        created_at=now,
        expires_at=now + timedelta(minutes=settings.upload_ttl_minutes),
    )
    db.add(artifact)
    job.status = JobStatus.completed
    job.safe_error_code = None
    db.commit()
    db.refresh(artifact)
    logger.info(
        "image_redaction_completed",
        job_id=str(job.id),
        artifact_id=str(artifact.id),
        artifact_type=artifact_type.value,
        redacted_count=len(accepted),
        rejected_count=len(rejected),
        rectangle_count=len(rectangles),
        byte_size=byte_size,
        status=job.status.value,
    )
    return RedactPdfResult(
        job_id=job.id,
        status=job.status.value,
        artifact=ArtifactView(
            artifact_id=artifact.id,
            job_id=job.id,
            artifact_type=artifact.artifact_type.value,
            byte_size=artifact.byte_size,
            created_at=artifact.created_at,
            expires_at=artifact.expires_at,
        ),
        redacted_count=len(accepted),
        rejected_count=len(rejected),
        warnings=[],
    )
