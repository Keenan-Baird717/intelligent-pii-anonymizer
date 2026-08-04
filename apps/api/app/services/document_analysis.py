"""Phase 6 document analysis — PDF (embedded + OCR) and PNG/JPEG OCR."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.concurrency import document_job_slot, job_locks, ocr_slot
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.detected_entity import AnonymizationMethod, DetectedEntity, ReviewStatus
from app.models.processing_job import JobStatus, ProcessingJob, ValidatedFileType
from app.processing.detection.pipeline import analyze_text
from app.processing.image import analyze_image_file, map_image_entity_rects
from app.processing.ocr.adapter import ensure_tesseract_available, get_default_ocr_engine
from app.processing.ocr.confidence import combine_confidence
from app.processing.ocr.index import build_ocr_text_index, map_ocr_offsets
from app.processing.ocr.preprocess import run_ocr_with_optional_preprocess
from app.processing.ocr.workfiles import cleanup_job_ocr_work, safe_unlink_ocr
from app.processing.pdf.classify import is_scanned_like
from app.processing.pdf.constants import PAGE_SEPARATOR
from app.processing.pdf.coordinates import map_entity
from app.processing.pdf.extract import extract_document
from app.processing.pdf.render import render_pdf_page
from app.processing.pdf.types import (
    BBox,
    ExtractedDocument,
    ExtractedPage,
    PositionedSpan,
)
from app.services.ingestion.clock import Clock, SystemClock
from app.services.ingestion.storage import resolve_storage_path
from app.services.ingestion.upload import get_job
from app.services.pdf.rectangles import rectangles_to_json

logger = get_logger(__name__)


@dataclass(frozen=True)
class EntityView:
    id: UUID
    entity_type: str
    start: int
    end: int
    text: str
    confidence: float | None
    detection_source: str
    recognizer_name: str
    checksum_valid: bool | None
    page_number: int
    rectangles: list[dict[str, float]]
    review_status: str
    anonymization_method: str
    manually_added: bool
    edited: bool
    source_kind: str = "embedded_text"
    ocr_confidence: float | None = None
    low_ocr_confidence: bool = False
    preprocessing_used: bool = False
    coordinate_space: str = "pdf_points"


@dataclass(frozen=True)
class AnalysisCoverage:
    total_pages: int = 0
    embedded_text_pages: int = 0
    ocr_pages: int = 0
    failed_pages: list[int] = field(default_factory=list)
    fully_analyzed: bool = True
    preprocessing_used: bool = False
    low_confidence_page_count: int = 0
    image_width: int | None = None
    image_height: int | None = None
    average_ocr_confidence: float | None = None
    low_confidence_warning: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "total_pages": self.total_pages,
            "embedded_text_pages": self.embedded_text_pages,
            "ocr_pages": self.ocr_pages,
            "failed_pages": list(self.failed_pages),
            "fully_analyzed": self.fully_analyzed,
            "preprocessing_used": self.preprocessing_used,
            "low_confidence_page_count": self.low_confidence_page_count,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "average_ocr_confidence": self.average_ocr_confidence,
            "low_confidence_warning": self.low_confidence_warning,
        }


@dataclass(frozen=True)
class AnalyzeDocumentResult:
    job_id: UUID
    status: str
    detection_count: int
    entities: list[EntityView]
    warnings: list[str]
    pages_needing_ocr: list[int]
    pages_with_text: list[int]
    page_count: int
    coverage: AnalysisCoverage


AnalyzePdfResult = AnalyzeDocumentResult


def _entity_text(full_text: str, start: int, end: int, *, manually_added: bool) -> str:
    if manually_added or start < 0 or end < 0 or end < start or end > len(full_text):
        return ""
    return full_text[start:end]


def entity_to_view(entity: DetectedEntity, full_text: str) -> EntityView:
    try:
        rects = json.loads(entity.rectangles_json)
    except json.JSONDecodeError:
        rects = []
    return EntityView(
        id=entity.id,
        entity_type=entity.entity_type,
        start=entity.start_offset,
        end=entity.end_offset,
        text=_entity_text(
            full_text,
            entity.start_offset,
            entity.end_offset,
            manually_added=entity.manually_added,
        ),
        confidence=entity.confidence,
        detection_source=entity.detection_source,
        recognizer_name=entity.recognizer_name,
        checksum_valid=entity.checksum_valid,
        page_number=entity.page_number,
        rectangles=rects if isinstance(rects, list) else [],
        review_status=entity.review_status.value,
        anonymization_method=entity.anonymization_method.value,
        manually_added=entity.manually_added,
        edited=entity.edited,
        source_kind=getattr(entity, "source_kind", None) or "embedded_text",
        ocr_confidence=getattr(entity, "ocr_confidence", None),
        low_ocr_confidence=bool(getattr(entity, "low_ocr_confidence", False)),
        preprocessing_used=bool(getattr(entity, "preprocessing_used", False)),
        coordinate_space=getattr(entity, "coordinate_space", None) or "pdf_points",
    )


def load_job_entities(db: Session, job_id: UUID) -> list[DetectedEntity]:
    return list(
        db.scalars(
            select(DetectedEntity)
            .where(DetectedEntity.processing_job_id == job_id)
            .order_by(DetectedEntity.created_at, DetectedEntity.id)
        ).all()
    )


def _require_pdf_job(job: ProcessingJob) -> None:
    if job.validated_file_type is not ValidatedFileType.pdf:
        raise AppError(
            code="UNSUPPORTED_FILE_TYPE",
            message="PDF analysis is only available for PDF jobs.",
            status_code=400,
        )


def _load_extracted(job: ProcessingJob, *, root: Path | None = None) -> ExtractedDocument:
    path = resolve_storage_path(job.storage_key, root=root)
    if not path.exists():
        raise AppError(
            code="STORAGE_FAILURE", message="The source file is unavailable.", status_code=500
        )
    return extract_document(path, raise_on_scanned=False)


def _require_ocr_ready() -> None:
    if not settings.ocr_enabled:
        raise AppError(
            code="OCR_DISABLED",
            message="OCR is disabled in this configuration.",
            status_code=503,
        )
    ensure_tesseract_available()


def analyze_document_job(
    db: Session,
    job_id: UUID,
    *,
    language: str = "en",
    clock: Clock | None = None,
    root: Path | None = None,
) -> AnalyzeDocumentResult:
    with job_locks.acquire(str(job_id), "analyze"):
        with document_job_slot():
            return _analyze_document_job_inner(
                db, job_id, language=language, clock=clock, root=root
            )


def _analyze_document_job_inner(
    db: Session,
    job_id: UUID,
    *,
    language: str = "en",
    clock: Clock | None = None,
    root: Path | None = None,
) -> AnalyzeDocumentResult:
    clock = clock or SystemClock()
    job = get_job(db, job_id, clock=clock)
    if job.validated_file_type is ValidatedFileType.pdf:
        return _analyze_pdf(db, job, language=language, root=root)
    if job.validated_file_type in {ValidatedFileType.png, ValidatedFileType.jpeg}:
        with ocr_slot():
            return _analyze_image(db, job, language=language, root=root)
    raise AppError(
        code="UNSUPPORTED_FILE_TYPE",
        message="Document analysis is not available for this file type.",
        status_code=400,
    )


def analyze_pdf_job(
    db: Session,
    job_id: UUID,
    *,
    language: str = "en",
    clock: Clock | None = None,
    root: Path | None = None,
) -> AnalyzeDocumentResult:
    return analyze_document_job(db, job_id, language=language, clock=clock, root=root)


def _persist_entities_from_document(
    db: Session,
    job: ProcessingJob,
    document: ExtractedDocument,
    *,
    language: str,
    page_source: dict[int, str],
    preprocessing_used: bool,
) -> list[EntityView]:
    resolved = (
        analyze_text(document.full_text, language=language) if document.full_text.strip() else []
    )
    db.execute(delete(DetectedEntity).where(DetectedEntity.processing_job_id == job.id))
    views: list[EntityView] = []
    for item in resolved:
        mapping = map_entity(document, item.start, item.end)
        source_kind = page_source.get(mapping.page_number, "embedded_text")
        ocr_conf = None
        low_ocr = False
        if source_kind == "ocr":
            ocr_conf = item.confidence
            low_ocr = (item.confidence or 1.0) < (settings.ocr_low_confidence_threshold / 100.0)
        combined = combine_confidence(
            detection_confidence=item.confidence,
            ocr_confidence=ocr_conf,
            checksum_valid=item.checksum_valid,
            low_ocr_confidence=low_ocr,
        )
        entity = DetectedEntity(
            processing_job_id=job.id,
            entity_type=item.entity_type,
            confidence=item.confidence,
            detection_source=("ocr" if source_kind == "ocr" else item.detection_source),
            recognizer_name=item.recognizer_name,
            checksum_valid=item.checksum_valid,
            start_offset=item.start,
            end_offset=item.end,
            page_number=mapping.page_number,
            rectangles_json=rectangles_to_json(mapping.rectangles),
            review_status=ReviewStatus.pending,
            anonymization_method=AnonymizationMethod.redaction,
            manually_added=False,
            edited=False,
            source_kind=source_kind,
            ocr_confidence=combined.ocr_confidence if source_kind == "ocr" else None,
            low_ocr_confidence=combined.low_ocr_confidence if source_kind == "ocr" else False,
            preprocessing_used=preprocessing_used if source_kind == "ocr" else False,
            coordinate_space="pdf_points",
        )
        db.add(entity)
        db.flush()
        views.append(entity_to_view(entity, document.full_text))
    return views


def _ocr_page_to_extracted(
    path: Path,
    page: ExtractedPage,
    *,
    job_id: str,
    root: Path | None,
) -> tuple[str, list[PositionedSpan], bool, float]:
    rendered = render_pdf_page(path, page.page_number, job_id=job_id, root=root)
    try:
        pass_result = run_ocr_with_optional_preprocess(
            rendered.image_path,
            engine=get_default_ocr_engine(),
            job_id=job_id,
            root=root,
        )
        index = build_ocr_text_index(
            pass_result.result,
            page_number=page.page_number,
            render_transform=rendered.transform,
            rotation=rendered.transform.rotation,
        )
        avg = sum(w.confidence for w in pass_result.result.words) / max(
            len(pass_result.result.words), 1
        )
        # Spans use local offsets; caller shifts to global.
        spans: list[PositionedSpan] = []
        for word in index.words:
            if word.pdf_bbox is None:
                continue
            x0, y0, x1, y1 = word.pdf_bbox
            spans.append(
                PositionedSpan(
                    page_number=page.page_number,
                    start=word.start,
                    end=word.end,
                    text_length=word.end - word.start,
                    bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1).clip(page.width, page.height),
                    block_no=word.block_no,
                    line_no=word.line_no,
                )
            )
        return index.full_text, spans, pass_result.preprocessing_used, avg
    finally:
        safe_unlink_ocr(rendered.image_path, root=root)


def _analyze_pdf(
    db: Session,
    job: ProcessingJob,
    *,
    language: str,
    root: Path | None,
) -> AnalyzeDocumentResult:
    job.status = JobStatus.extracting
    job.safe_error_code = None
    db.commit()

    path = resolve_storage_path(job.storage_key, root=root)
    if not path.exists():
        job.status = JobStatus.failed
        job.safe_error_code = "STORAGE_FAILURE"
        db.commit()
        raise AppError(
            code="STORAGE_FAILURE", message="The source file is unavailable.", status_code=500
        )

    try:
        extracted = extract_document(path, raise_on_scanned=False)
    except AppError as exc:
        job.status = JobStatus.failed
        job.safe_error_code = exc.code
        db.commit()
        raise

    ocr_page_numbers = list(extracted.pages_needing_ocr)
    fully_scanned = is_scanned_like(extracted, min_chars=settings.min_pdf_text_chars)
    if fully_scanned:
        ocr_page_numbers = [p.page_number for p in extracted.pages]

    if ocr_page_numbers:
        try:
            _require_ocr_ready()
        except AppError as exc:
            if fully_scanned or not extracted.pages_with_text:
                job.status = JobStatus.failed
                job.safe_error_code = (
                    "OCR_REQUIRED"
                    if exc.code in {"OCR_DISABLED", "OCR_ENGINE_UNAVAILABLE"}
                    else exc.code
                )
                db.commit()
                raise AppError(
                    code="OCR_REQUIRED"
                    if exc.code in {"OCR_DISABLED", "OCR_ENGINE_UNAVAILABLE"}
                    else exc.code,
                    message="This PDF requires OCR, which is unavailable.",
                    status_code=422,
                ) from exc
            ocr_page_numbers = []

    if len(ocr_page_numbers) > settings.effective_ocr_max_pages:
        job.status = JobStatus.failed
        job.safe_error_code = "OCR_PAGE_LIMIT_EXCEEDED"
        db.commit()
        raise AppError(
            code="OCR_PAGE_LIMIT_EXCEEDED",
            message="This document exceeds the OCR page limit for synchronous processing.",
            status_code=413,
        )

    job.status = JobStatus.analyzing
    db.commit()

    warnings: list[str] = []
    failed_pages: list[int] = []
    preprocessing_used = False
    low_conf_pages = 0
    page_source: dict[int, str] = {}

    try:
        if not ocr_page_numbers:
            # Pure embedded-text Phase 5 path.
            page_source = {p.page_number: "embedded_text" for p in extracted.pages if p.has_text}
            views = _persist_entities_from_document(
                db,
                job,
                extracted,
                language=language,
                page_source=page_source,
                preprocessing_used=False,
            )
            if extracted.is_partial_text:
                warnings.append("PARTIAL_TEXT_EXTRACTION")
            coverage = AnalysisCoverage(
                total_pages=len(extracted.pages),
                embedded_text_pages=len(extracted.pages_with_text),
                ocr_pages=0,
                failed_pages=[],
                fully_analyzed=not extracted.is_partial_text,
                preprocessing_used=False,
            )
            job.status = JobStatus.awaiting_review
            job.analysis_coverage_json = json.dumps(coverage.to_dict(), separators=(",", ":"))
            db.commit()
            return AnalyzeDocumentResult(
                job_id=job.id,
                status=job.status.value,
                detection_count=len(views),
                entities=views,
                warnings=warnings,
                pages_needing_ocr=list(extracted.pages_needing_ocr),
                pages_with_text=list(extracted.pages_with_text),
                page_count=len(extracted.pages),
                coverage=coverage,
            )

        # Mixed / scanned: rebuild document page-by-page.
        page_texts: list[str] = []
        all_spans: list[PositionedSpan] = []
        global_offset = 0
        rebuilt_pages: list[ExtractedPage] = []

        for page in extracted.pages:
            if page.page_number in ocr_page_numbers:
                page_source[page.page_number] = "ocr"
                try:
                    text, local_spans, used_prep, avg = _ocr_page_to_extracted(
                        path, page, job_id=str(job.id), root=root
                    )
                    if used_prep:
                        preprocessing_used = True
                    if avg < settings.ocr_low_confidence_threshold:
                        low_conf_pages += 1
                    spans = [
                        PositionedSpan(
                            page_number=s.page_number,
                            start=global_offset + s.start,
                            end=global_offset + s.end,
                            text_length=s.text_length,
                            bbox=s.bbox,
                            block_no=s.block_no,
                            line_no=s.line_no,
                        )
                        for s in local_spans
                    ]
                except AppError:
                    failed_pages.append(page.page_number)
                    text, spans = "", []
            else:
                page_source[page.page_number] = "embedded_text"
                text = page.text
                spans = [
                    PositionedSpan(
                        page_number=s.page_number,
                        start=global_offset
                        + (s.start - _page_global_start(extracted, page.page_number)),
                        end=global_offset
                        + (s.end - _page_global_start(extracted, page.page_number)),
                        text_length=s.text_length,
                        bbox=s.bbox,
                        block_no=s.block_no,
                        line_no=s.line_no,
                    )
                    for s in page.spans
                ]

            rebuilt_pages.append(
                ExtractedPage(
                    page_number=page.page_number,
                    width=page.width,
                    height=page.height,
                    text=text,
                    spans=spans,
                    has_text=bool(text.strip()),
                    has_images=page.has_images,
                )
            )
            all_spans.extend(spans)
            page_texts.append(text)
            global_offset += len(text)
            if page.page_number != extracted.pages[-1].page_number:
                global_offset += len(PAGE_SEPARATOR)

        combined = ExtractedDocument(
            pages=rebuilt_pages,
            full_text=PAGE_SEPARATOR.join(page_texts),
            page_separator=PAGE_SEPARATOR,
            pages_with_text=[
                p.page_number
                for p in rebuilt_pages
                if p.has_text and page_source.get(p.page_number) == "embedded_text"
            ],
            pages_needing_ocr=[p for p, kind in page_source.items() if kind == "ocr"],
        )
        # Attach all spans onto pages (already done).
        views = _persist_entities_from_document(
            db,
            job,
            combined,
            language=language,
            page_source=page_source,
            preprocessing_used=preprocessing_used,
        )
        if failed_pages:
            warnings.append("PARTIAL_ANALYSIS")
        coverage = AnalysisCoverage(
            total_pages=len(extracted.pages),
            embedded_text_pages=len([p for p, k in page_source.items() if k == "embedded_text"]),
            ocr_pages=len([p for p, k in page_source.items() if k == "ocr"]),
            failed_pages=failed_pages,
            fully_analyzed=len(failed_pages) == 0,
            preprocessing_used=preprocessing_used,
            low_confidence_page_count=low_conf_pages,
        )
        job.status = JobStatus.awaiting_review
        job.analysis_coverage_json = json.dumps(coverage.to_dict(), separators=(",", ":"))
        db.commit()
        logger.info(
            "document_analysis_completed",
            job_id=str(job.id),
            detection_count=len(views),
            ocr_pages=coverage.ocr_pages,
            embedded_text_pages=coverage.embedded_text_pages,
            failed_page_count=len(failed_pages),
            fully_analyzed=coverage.fully_analyzed,
            status=job.status.value,
        )
        return AnalyzeDocumentResult(
            job_id=job.id,
            status=job.status.value,
            detection_count=len(views),
            entities=views,
            warnings=warnings,
            pages_needing_ocr=list(combined.pages_needing_ocr),
            pages_with_text=list(combined.pages_with_text),
            page_count=len(extracted.pages),
            coverage=coverage,
        )
    except AppError as exc:
        db.rollback()
        failed_job = db.get(ProcessingJob, job.id)
        if failed_job is not None:
            failed_job.status = JobStatus.failed
            failed_job.safe_error_code = exc.code
            db.commit()
        raise
    except Exception as exc:
        db.rollback()
        failed_job = db.get(ProcessingJob, job.id)
        if failed_job is not None:
            failed_job.status = JobStatus.failed
            failed_job.safe_error_code = "DOCUMENT_ANALYSIS_FAILED"
            db.commit()
        logger.error(
            "document_analysis_failure", job_id=str(job.id), error_code="DOCUMENT_ANALYSIS_FAILED"
        )
        raise AppError(
            code="DOCUMENT_ANALYSIS_FAILED",
            message="Document analysis failed.",
            status_code=500,
        ) from exc
    finally:
        cleanup_job_ocr_work(str(job.id), root=root)


def _page_global_start(extracted: ExtractedDocument, page_number: int) -> int:
    offset = 0
    for page in extracted.pages:
        if page.page_number == page_number:
            return offset
        offset += len(page.text) + len(PAGE_SEPARATOR)
    return 0


def _analyze_image(
    db: Session,
    job: ProcessingJob,
    *,
    language: str,
    root: Path | None,
) -> AnalyzeDocumentResult:
    job.status = JobStatus.analyzing
    job.safe_error_code = None
    db.commit()
    path = resolve_storage_path(job.storage_key, root=root)
    if not path.exists():
        job.status = JobStatus.failed
        job.safe_error_code = "STORAGE_FAILURE"
        db.commit()
        raise AppError(
            code="STORAGE_FAILURE", message="The source file is unavailable.", status_code=500
        )

    try:
        _require_ocr_ready()
        index, transform, preprocessing_used, avg_conf = analyze_image_file(
            path, job_id=str(job.id), root=root
        )
        resolved = analyze_text(index.full_text, language=language)
        db.execute(delete(DetectedEntity).where(DetectedEntity.processing_job_id == job.id))
        views: list[EntityView] = []
        for item in resolved:
            mapping = map_ocr_offsets(index, item.start, item.end)
            rects = map_image_entity_rects(index, item.start, item.end, transform)
            combined = combine_confidence(
                detection_confidence=item.confidence,
                ocr_confidence=mapping.ocr_confidence,
                checksum_valid=item.checksum_valid,
                low_ocr_confidence=mapping.low_ocr_confidence,
            )
            entity = DetectedEntity(
                processing_job_id=job.id,
                entity_type=item.entity_type,
                confidence=item.confidence,
                detection_source="ocr",
                recognizer_name=item.recognizer_name,
                checksum_valid=item.checksum_valid,
                start_offset=item.start,
                end_offset=item.end,
                page_number=1,
                rectangles_json=json.dumps(rects, separators=(",", ":")),
                review_status=ReviewStatus.pending,
                anonymization_method=AnonymizationMethod.redaction,
                manually_added=False,
                edited=False,
                source_kind="ocr",
                ocr_confidence=combined.ocr_confidence,
                low_ocr_confidence=combined.low_ocr_confidence,
                preprocessing_used=preprocessing_used,
                coordinate_space="image_pixels",
            )
            db.add(entity)
            db.flush()
            views.append(entity_to_view(entity, index.full_text))

        low_warn = avg_conf < (settings.ocr_low_confidence_threshold / 100.0)
        coverage = AnalysisCoverage(
            total_pages=1,
            embedded_text_pages=0,
            ocr_pages=1,
            failed_pages=[],
            fully_analyzed=True,
            preprocessing_used=preprocessing_used,
            low_confidence_page_count=1 if low_warn else 0,
            image_width=transform.original_width,
            image_height=transform.original_height,
            average_ocr_confidence=avg_conf,
            low_confidence_warning=low_warn,
        )
        warnings = ["OCR_LOW_CONFIDENCE"] if low_warn else []
        job.status = JobStatus.awaiting_review
        job.analysis_coverage_json = json.dumps(coverage.to_dict(), separators=(",", ":"))
        db.commit()
        return AnalyzeDocumentResult(
            job_id=job.id,
            status=job.status.value,
            detection_count=len(views),
            entities=views,
            warnings=warnings,
            pages_needing_ocr=[1],
            pages_with_text=[],
            page_count=1,
            coverage=coverage,
        )
    except AppError as exc:
        db.rollback()
        failed_job = db.get(ProcessingJob, job.id)
        if failed_job is not None:
            failed_job.status = JobStatus.failed
            failed_job.safe_error_code = exc.code
            db.commit()
        raise
    except Exception as exc:
        db.rollback()
        failed_job = db.get(ProcessingJob, job.id)
        if failed_job is not None:
            failed_job.status = JobStatus.failed
            failed_job.safe_error_code = "IMAGE_ANALYSIS_FAILED"
            db.commit()
        raise AppError(
            code="IMAGE_ANALYSIS_FAILED",
            message="Image analysis failed.",
            status_code=500,
        ) from exc
    finally:
        cleanup_job_ocr_work(str(job.id), root=root)
