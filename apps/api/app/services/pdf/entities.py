from __future__ import annotations

from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.detected_entity import AnonymizationMethod, DetectedEntity, ReviewStatus
from app.models.processing_job import JobStatus
from app.processing.pdf.types import MappedRectangle
from app.services.ingestion.clock import Clock, SystemClock
from app.services.ingestion.upload import get_job
from app.services.pdf.analysis import (
    EntityView,
    _load_extracted,
    entity_to_view,
    load_job_entities,
)
from app.services.pdf.rectangles import rectangles_to_json, validate_rectangle_dict


def list_entities(
    db: Session,
    job_id: UUID,
    *,
    clock: Clock | None = None,
    root: Path | None = None,
) -> list[EntityView]:
    clock = clock or SystemClock()
    job = get_job(db, job_id, clock=clock)
    full_text = ""
    if job.validated_file_type.value == "pdf":
        try:
            extracted = _load_extracted(job, root=root)
            full_text = extracted.full_text
        except AppError:
            full_text = ""
    return [entity_to_view(entity, full_text) for entity in load_job_entities(db, job_id)]


def patch_entity(
    db: Session,
    job_id: UUID,
    entity_id: UUID,
    *,
    review_status: str | None = None,
    entity_type: str | None = None,
    anonymization_method: str | None = None,
    rectangles: list[dict[str, float]] | None = None,
    page_number: int | None = None,
    clock: Clock | None = None,
    root: Path | None = None,
) -> EntityView:
    clock = clock or SystemClock()
    job = get_job(db, job_id, clock=clock)
    entity = db.get(DetectedEntity, entity_id)
    if entity is None or entity.processing_job_id != job.id:
        raise AppError(code="ENTITY_NOT_FOUND", message="Entity not found.", status_code=404)

    if review_status is not None:
        try:
            entity.review_status = ReviewStatus(review_status)
        except ValueError as exc:
            raise AppError(
                code="INVALID_REVIEW_STATUS",
                message="Invalid review status.",
                status_code=400,
            ) from exc
    if entity_type is not None:
        cleaned = entity_type.strip()
        if not cleaned:
            raise AppError(
                code="UNSUPPORTED_ENTITY_TYPE",
                message="Unsupported entity type.",
                status_code=400,
            )
        entity.entity_type = cleaned
        entity.edited = True
        if entity.review_status not in {ReviewStatus.manually_added, ReviewStatus.rejected}:
            entity.review_status = ReviewStatus.edited
    if anonymization_method is not None:
        if anonymization_method != AnonymizationMethod.redaction.value:
            raise AppError(
                code="UNSUPPORTED_ANONYMIZATION_METHOD",
                message="PDF anonymization supports redaction only.",
                status_code=400,
            )
        entity.anonymization_method = AnonymizationMethod.redaction
    if page_number is not None:
        if page_number < 1 or (job.page_count and page_number > job.page_count):
            raise AppError(
                code="INVALID_MANUAL_REDACTION",
                message="Page number is invalid.",
                status_code=400,
            )
        entity.page_number = page_number
    if rectangles is not None:
        boxes = [validate_rectangle_dict(item) for item in rectangles]
        mapped = [MappedRectangle(page_number=entity.page_number, bbox=box) for box in boxes]
        entity.rectangles_json = rectangles_to_json(mapped)
        entity.edited = True

    db.commit()
    db.refresh(entity)
    full_text = ""
    if job.validated_file_type.value == "pdf":
        try:
            extracted = _load_extracted(job, root=root)
            full_text = extracted.full_text
        except AppError:
            full_text = ""
    return entity_to_view(entity, full_text)


def create_manual_entity(
    db: Session,
    job_id: UUID,
    *,
    page_number: int,
    rectangle: dict[str, float],
    entity_type: str = "OTHER",
    clock: Clock | None = None,
    root: Path | None = None,
) -> EntityView:
    clock = clock or SystemClock()
    job = get_job(db, job_id, clock=clock)
    is_pdf = job.validated_file_type.value == "pdf"
    is_image = job.validated_file_type.value in {"png", "jpeg"}
    if not is_pdf and not is_image:
        raise AppError(
            code="UNSUPPORTED_FILE_TYPE",
            message="Manual redaction is not available for this file type.",
            status_code=400,
        )
    from sqlalchemy import func, select

    from app.core.config import settings
    from app.models.detected_entity import DetectedEntity

    manual_count = db.scalar(
        select(func.count())
        .select_from(DetectedEntity)
        .where(
            DetectedEntity.processing_job_id == job_id,
            DetectedEntity.manually_added.is_(True),
        )
    )
    if (manual_count or 0) >= settings.max_manual_rectangles:
        raise AppError(
            code="TOO_MANY_MANUAL_RECTANGLES",
            message="Too many manual redaction regions for this job.",
            status_code=400,
        )
    if is_pdf:
        if page_number < 1 or (job.page_count and page_number > job.page_count):
            raise AppError(
                code="INVALID_MANUAL_REDACTION",
                message="Page number is invalid.",
                status_code=400,
            )
    elif page_number != 1:
        raise AppError(
            code="INVALID_MANUAL_REDACTION",
            message="Page number is invalid.",
            status_code=400,
        )
    bbox = validate_rectangle_dict(rectangle)
    full_text = ""
    if is_pdf:
        try:
            extracted = _load_extracted(job, root=root)
            page = next((p for p in extracted.pages if p.page_number == page_number), None)
            if page is not None:
                bbox = bbox.clip(page.width, page.height)
            full_text = extracted.full_text
        except AppError:
            full_text = ""
    else:
        width = float(job.image_width or 0)
        height = float(job.image_height or 0)
        if width > 0 and height > 0:
            bbox = bbox.clip(width, height)

    if bbox.x1 <= bbox.x0 or bbox.y1 <= bbox.y0:
        raise AppError(
            code="INVALID_MANUAL_REDACTION",
            message="Rectangle coordinates are invalid.",
            status_code=400,
        )

    entity = DetectedEntity(
        processing_job_id=job.id,
        entity_type=(entity_type or "OTHER").strip() or "OTHER",
        confidence=None,
        detection_source="manual",
        recognizer_name="manual_rectangle",
        checksum_valid=None,
        start_offset=-1,
        end_offset=-1,
        page_number=page_number,
        rectangles_json=rectangles_to_json([MappedRectangle(page_number=page_number, bbox=bbox)]),
        review_status=ReviewStatus.manually_added,
        anonymization_method=AnonymizationMethod.redaction,
        manually_added=True,
        edited=False,
        source_kind="manual",
        ocr_confidence=None,
        low_ocr_confidence=False,
        preprocessing_used=False,
        coordinate_space="pdf_points" if is_pdf else "image_pixels",
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    if job.status == JobStatus.pending:
        job.status = JobStatus.awaiting_review
        db.commit()
    return entity_to_view(entity, full_text)


def delete_entity(
    db: Session,
    job_id: UUID,
    entity_id: UUID,
    *,
    clock: Clock | None = None,
) -> None:
    clock = clock or SystemClock()
    job = get_job(db, job_id, clock=clock)
    entity = db.get(DetectedEntity, entity_id)
    if entity is None or entity.processing_job_id != job.id:
        raise AppError(code="ENTITY_NOT_FOUND", message="Entity not found.", status_code=404)
    if not entity.manually_added:
        raise AppError(
            code="INVALID_MANUAL_REDACTION",
            message="Only manually added regions can be deleted.",
            status_code=400,
        )
    db.delete(entity)
    db.commit()
