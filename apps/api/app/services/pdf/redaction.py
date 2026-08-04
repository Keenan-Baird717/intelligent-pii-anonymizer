from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.concurrency import job_locks, redaction_slot
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.detected_entity import ReviewStatus
from app.models.generated_artifact import ArtifactType, GeneratedArtifact
from app.models.processing_job import JobStatus
from app.processing.pdf.classify import normalize_whitespace
from app.processing.pdf.redact import apply_redactions
from app.processing.pdf.types import BBox
from app.processing.pdf.verify import verify_redaction, verify_scanned_page_redaction
from app.services.ingestion.clock import Clock, SystemClock
from app.services.ingestion.storage import (
    delete_stored_file,
    generate_storage_key,
    resolve_storage_path,
    safe_unlink,
)
from app.services.ingestion.upload import get_job
from app.services.pdf.analysis import _load_extracted, _require_pdf_job, load_job_entities
from app.services.pdf.rectangles import rectangles_from_json

logger = get_logger(__name__)

_TRANSFORMABLE = {
    ReviewStatus.pending,
    ReviewStatus.accepted,
    ReviewStatus.edited,
    ReviewStatus.manually_added,
}


@dataclass(frozen=True)
class ArtifactView:
    artifact_id: UUID
    job_id: UUID
    artifact_type: str
    byte_size: int
    created_at: object
    expires_at: object


@dataclass(frozen=True)
class RedactPdfResult:
    job_id: UUID
    status: str
    artifact: ArtifactView
    redacted_count: int
    rejected_count: int
    warnings: list[str]


def anonymize_pdf_job(
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
            return _anonymize_pdf_job_inner(
                db, job_id, default_method=method, clock=clock, root=root
            )


def _anonymize_pdf_job_inner(
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
            message="PDF anonymization supports redaction only.",
            status_code=400,
        )

    job = get_job(db, job_id, clock=clock)
    _require_pdf_job(job)
    job.status = JobStatus.anonymizing
    db.commit()

    entities = load_job_entities(db, job_id)
    accepted = [entity for entity in entities if entity.review_status in _TRANSFORMABLE]
    rejected = [entity for entity in entities if entity.review_status is ReviewStatus.rejected]

    if not accepted:
        job.status = JobStatus.awaiting_review
        db.commit()
        raise AppError(
            code="REDACTION_FAILED",
            message="No accepted detections or manual regions to redact.",
            status_code=400,
        )

    source_path = resolve_storage_path(job.storage_key, root=root)
    extracted = _load_extracted(job, root=root)

    rectangles: list[tuple[int, BBox]] = []
    page_rects: dict[int, list[BBox]] = defaultdict(list)
    for entity in accepted:
        boxes = rectangles_from_json(entity.rectangles_json)
        for box in boxes:
            rectangles.append((entity.page_number, box))
            page_rects[entity.page_number].append(box)

    pixel_pages = _resolve_pixel_redact_pages(job, accepted, extracted)
    text_forbidden = _embedded_forbidden_values(accepted, extracted)
    text_required = _embedded_required_values(rejected, extracted, text_forbidden)

    # Ephemeral OCR tokens for scanned-page verification (never persisted).
    scanned_forbidden: dict[int, list[str]] = {}
    scanned_required: dict[int, list[str]] = {}
    for page_number in sorted(pixel_pages):
        if page_number not in page_rects:
            continue
        scanned_forbidden[page_number] = _ocr_tokens_in_rectangles(
            source_path,
            page_number,
            page_rects[page_number],
            root=root,
            job_id=str(job.id),
        )
        # Prefer rejected OCR/manual neighboring tokens when available.
        scanned_required[page_number] = _ocr_control_tokens(
            source_path,
            page_number,
            page_rects[page_number],
            root=root,
            job_id=str(job.id),
        )

    storage_key = generate_storage_key(".pdf")
    output_path = resolve_storage_path(storage_key, root=root)
    try:
        apply_redactions(
            source_path,
            output_path,
            rectangles,
            pixel_redact_pages=pixel_pages,
        )
        # Text-layer verification for embedded-text content.
        if text_forbidden or text_required:
            verify_redaction(output_path, text_forbidden, text_required)
        # Pixel permanence + OCR verification for scanned / mixed pages.
        for page_number in sorted(pixel_pages):
            if page_number not in page_rects:
                continue
            verify_scanned_page_redaction(
                output_path,
                page_number=page_number,
                rectangles=page_rects[page_number],
                forbidden_substrings=scanned_forbidden.get(page_number, []),
                required_substrings=scanned_required.get(page_number, []),
                source_path=source_path,
            )
    except AppError as exc:
        safe_unlink(output_path)
        job.status = JobStatus.failed
        job.safe_error_code = (
            "REDACTION_VERIFICATION_FAILED"
            if exc.code == "REDACTION_VERIFICATION_FAILED"
            else "REDACTION_FAILED"
        )
        db.commit()
        raise
    except Exception as exc:
        safe_unlink(output_path)
        job.status = JobStatus.failed
        job.safe_error_code = "REDACTION_FAILED"
        db.commit()
        logger.error("pdf_redaction_unexpected", job_id=str(job_id), error_code="REDACTION_FAILED")
        raise AppError(
            code="REDACTION_FAILED",
            message="Redaction could not be applied.",
            status_code=500,
        ) from exc

    now = clock.now()
    byte_size = output_path.stat().st_size
    artifact = GeneratedArtifact(
        processing_job_id=job.id,
        artifact_type=ArtifactType.redacted_pdf,
        validated_extension="pdf",
        validated_mime_type="application/pdf",
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
        "pdf_redaction_completed",
        job_id=str(job.id),
        artifact_id=str(artifact.id),
        redacted_count=len(accepted),
        rejected_count=len(rejected),
        rectangle_count=len(rectangles),
        pixel_page_count=len(pixel_pages),
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


def _resolve_pixel_redact_pages(job, accepted, extracted) -> set[int]:  # type: ignore[no-untyped-def]
    """Pages that must be rasterized and rebuilt for irreversible pixel redaction."""
    pages: set[int] = set()
    ocr_pages_from_coverage: set[int] = set()
    if job.analysis_coverage_json:
        try:
            coverage = json.loads(job.analysis_coverage_json)
            # coverage stores counts, not page lists — fall back to entity source_kind
            # and extracted.pages_needing_ocr / has_images.
            _ = coverage
        except json.JSONDecodeError:
            pass

    for page in extracted.pages:
        if page.page_number in extracted.pages_needing_ocr or (
            page.has_images and not page.has_text
        ):
            ocr_pages_from_coverage.add(page.page_number)

    for entity in accepted:
        kind = getattr(entity, "source_kind", None) or "embedded_text"
        if kind == "ocr":
            pages.add(entity.page_number)
        elif kind == "manual":
            # Manual regions on image/OCR pages need pixel permanence.
            page = next((p for p in extracted.pages if p.page_number == entity.page_number), None)
            if page is not None and (
                page.has_images or page.page_number in ocr_pages_from_coverage
            ):
                pages.add(entity.page_number)
        elif kind == "embedded_text":
            page = next((p for p in extracted.pages if p.page_number == entity.page_number), None)
            # Mixed page: embedded text + imagery — rebuild so image pixels cannot survive.
            if page is not None and page.has_images and page.has_text:
                pages.add(entity.page_number)

    # Any accepted rectangle on a known OCR/scanned page.
    for page_number in ocr_pages_from_coverage:
        if any(entity.page_number == page_number for entity in accepted):
            pages.add(page_number)

    return pages


def _embedded_forbidden_values(accepted, extracted) -> list[str]:  # type: ignore[no-untyped-def]
    forbidden: list[str] = []
    for entity in accepted:
        kind = getattr(entity, "source_kind", None) or "embedded_text"
        if kind != "embedded_text":
            continue
        if (
            not entity.manually_added
            and entity.start_offset >= 0
            and entity.end_offset > entity.start_offset
            and entity.end_offset <= len(extracted.full_text)
        ):
            value = extracted.full_text[entity.start_offset : entity.end_offset]
            if value.strip():
                forbidden.append(value)
    return forbidden


def _embedded_required_values(rejected, extracted, forbidden: list[str]) -> list[str]:  # type: ignore[no-untyped-def]
    required: list[str] = []
    for entity in rejected:
        if entity.start_offset >= 0 and entity.end_offset > entity.start_offset:
            if entity.end_offset > len(extracted.full_text):
                continue
            value = extracted.full_text[entity.start_offset : entity.end_offset]
            if value.strip() and value not in forbidden:
                required.append(value)
                break
    if not required:
        for token in extracted.full_text.split():
            if len(token) >= 4 and token not in forbidden:
                required.append(token)
                break
    return required


def _ocr_tokens_in_rectangles(
    source_path: Path,
    page_number: int,
    rectangles: list[BBox],
    *,
    root: Path | None,
    job_id: str,
) -> list[str]:
    """Ephemeral OCR of source page words intersecting redaction rectangles."""
    from app.processing.ocr.adapter import get_default_ocr_engine
    from app.processing.ocr.index import build_ocr_text_index
    from app.processing.ocr.preprocess import run_ocr_with_optional_preprocess
    from app.processing.ocr.workfiles import safe_unlink_ocr
    from app.processing.pdf.render import render_pdf_page

    tokens: list[str] = []
    try:
        rendered = render_pdf_page(source_path, page_number, job_id=job_id, root=root)
    except AppError:
        return tokens
    try:
        try:
            pass_result = run_ocr_with_optional_preprocess(
                rendered.image_path,
                engine=get_default_ocr_engine(),
                job_id=job_id,
                root=root,
            )
        except AppError:
            return tokens
        index = build_ocr_text_index(
            pass_result.result,
            page_number=page_number,
            render_transform=rendered.transform,
            rotation=rendered.transform.rotation,
        )
        for word in index.words:
            if word.pdf_bbox is None:
                continue
            wx0, wy0, wx1, wy1 = word.pdf_bbox
            if any(_rects_intersect(wx0, wy0, wx1, wy1, box) for box in rectangles):
                cleaned = normalize_whitespace(word.text)
                if len(cleaned) >= 3:
                    tokens.append(cleaned)
    finally:
        safe_unlink_ocr(rendered.image_path, root=root)
    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for token in tokens:
        key = token.lower()
        if key not in seen:
            seen.add(key)
            unique.append(token)
    return unique


def _ocr_control_tokens(
    source_path: Path,
    page_number: int,
    redacted: list[BBox],
    *,
    root: Path | None,
    job_id: str,
) -> list[str]:
    """Pick a control OCR token outside redaction rectangles when practical."""
    from app.processing.ocr.adapter import get_default_ocr_engine
    from app.processing.ocr.index import build_ocr_text_index
    from app.processing.ocr.preprocess import run_ocr_with_optional_preprocess
    from app.processing.ocr.workfiles import safe_unlink_ocr
    from app.processing.pdf.render import render_pdf_page

    try:
        rendered = render_pdf_page(source_path, page_number, job_id=job_id, root=root)
    except AppError:
        return []
    try:
        try:
            pass_result = run_ocr_with_optional_preprocess(
                rendered.image_path,
                engine=get_default_ocr_engine(),
                job_id=job_id,
                root=root,
            )
        except AppError:
            return []
        index = build_ocr_text_index(
            pass_result.result,
            page_number=page_number,
            render_transform=rendered.transform,
            rotation=rendered.transform.rotation,
        )
        for word in index.words:
            if word.pdf_bbox is None:
                continue
            cleaned = normalize_whitespace(word.text)
            if len(cleaned) < 4:
                continue
            wx0, wy0, wx1, wy1 = word.pdf_bbox
            if any(_rects_intersect(wx0, wy0, wx1, wy1, box) for box in redacted):
                continue
            return [cleaned]
    finally:
        safe_unlink_ocr(rendered.image_path, root=root)
    return []


def _rects_intersect(ax0: float, ay0: float, ax1: float, ay1: float, box: BBox) -> bool:
    return not (ax1 <= box.x0 or box.x1 <= ax0 or ay1 <= box.y0 or box.y1 <= ay0)


def get_artifact(
    db: Session,
    job_id: UUID,
    artifact_id: UUID,
    *,
    clock: Clock | None = None,
) -> GeneratedArtifact:
    clock = clock or SystemClock()
    job = get_job(db, job_id, clock=clock)
    artifact = db.get(GeneratedArtifact, artifact_id)
    if artifact is None or artifact.processing_job_id != job.id:
        raise AppError(code="ARTIFACT_NOT_FOUND", message="Artifact not found.", status_code=404)
    expires = artifact.expires_at
    if expires.tzinfo is None:
        from datetime import UTC

        expires = expires.replace(tzinfo=UTC)
    if expires <= clock.now():
        raise AppError(
            code="ARTIFACT_EXPIRED", message="This artifact has expired.", status_code=410
        )
    return artifact


def delete_job_artifacts(db: Session, job_id: UUID, *, root: Path | None = None) -> None:
    artifacts = db.scalars(
        select(GeneratedArtifact).where(GeneratedArtifact.processing_job_id == job_id)
    ).all()
    for artifact in artifacts:
        try:
            delete_stored_file(artifact.storage_key, root=root)
        except AppError:
            pass
        db.delete(artifact)
    db.commit()
