"""Phase 7 result summary and audit-report generation from safe metadata."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.detected_entity import DetectedEntity, ReviewStatus
from app.models.generated_artifact import GeneratedArtifact
from app.models.processing_job import JobStatus, ProcessingJob
from app.schemas.results import (
    AuditReportAnalysis,
    AuditReportOutput,
    AuditReportPrivacy,
    AuditReportResponse,
    AuditReportReview,
    AuditReportSource,
    JobResultResponse,
    ResultArtifactSummary,
)
from app.services.ingestion.clock import Clock, SystemClock
from app.services.ingestion.upload import get_job

logger = get_logger(__name__)

AUDIT_SCHEMA_VERSION = "1.0"


def _sorted_counts(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter.keys())}


def _load_entities(db: Session, job_id: UUID) -> list[DetectedEntity]:
    return list(
        db.scalars(
            select(DetectedEntity)
            .where(DetectedEntity.processing_job_id == job_id)
            .order_by(DetectedEntity.created_at, DetectedEntity.id)
        ).all()
    )


def _load_latest_artifact(db: Session, job_id: UUID) -> GeneratedArtifact | None:
    return db.scalars(
        select(GeneratedArtifact)
        .where(GeneratedArtifact.processing_job_id == job_id)
        .order_by(GeneratedArtifact.created_at.desc())
        .limit(1)
    ).first()


def _parse_coverage(job: ProcessingJob) -> dict[str, Any] | None:
    if not job.analysis_coverage_json:
        return None
    try:
        data = json.loads(job.analysis_coverage_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    # Return only safe known keys.
    allowed = {
        "total_pages",
        "embedded_text_pages",
        "ocr_pages",
        "failed_pages",
        "fully_analyzed",
        "preprocessing_used",
        "low_confidence_page_count",
        "image_width",
        "image_height",
        "average_ocr_confidence",
        "low_confidence_warning",
    }
    return {key: data[key] for key in sorted(data.keys()) if key in allowed}


def _review_counts(entities: list[DetectedEntity]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for entity in entities:
        counter[entity.review_status.value] += 1
    return _sorted_counts(counter)


def _category_counts(entities: list[DetectedEntity]) -> dict[str, int]:
    counter: Counter[str] = Counter(entity.entity_type for entity in entities)
    return _sorted_counts(counter)


def _method_counts(entities: list[DetectedEntity]) -> dict[str, int]:
    transformable = {
        ReviewStatus.pending,
        ReviewStatus.accepted,
        ReviewStatus.edited,
        ReviewStatus.manually_added,
    }
    counter: Counter[str] = Counter()
    for entity in entities:
        if entity.review_status in transformable:
            counter[entity.anonymization_method.value] += 1
    return _sorted_counts(counter)


def _verification_status(job: ProcessingJob, artifact: GeneratedArtifact | None) -> str | None:
    if job.status is JobStatus.completed and artifact is not None:
        return "passed"
    if job.status is JobStatus.failed and job.safe_error_code in {
        "REDACTION_VERIFICATION_FAILED",
        "OUTPUT_VERIFICATION_FAILED",
    }:
        return "failed"
    if job.status is JobStatus.failed:
        return "failed"
    if artifact is None:
        return None
    return "unknown"


def _safe_warnings(job: ProcessingJob, entities: list[DetectedEntity]) -> list[str]:
    warnings: list[str] = []
    coverage = _parse_coverage(job)
    if coverage:
        if coverage.get("low_confidence_warning") or int(
            coverage.get("low_confidence_page_count") or 0
        ):
            warnings.append("OCR_LOW_CONFIDENCE")
        if coverage.get("fully_analyzed") is False:
            warnings.append("PARTIAL_ANALYSIS")
    if any(getattr(entity, "low_ocr_confidence", False) for entity in entities):
        if "OCR_LOW_CONFIDENCE" not in warnings:
            warnings.append("OCR_LOW_CONFIDENCE")
    if job.safe_error_code:
        warnings.append(job.safe_error_code)
    return warnings


def build_job_result(
    db: Session,
    job_id: UUID,
    *,
    clock: Clock | None = None,
) -> JobResultResponse:
    clock = clock or SystemClock()
    job = get_job(db, job_id, clock=clock)
    entities = _load_entities(db, job_id)
    artifact = _load_latest_artifact(db, job_id)
    coverage = _parse_coverage(job)
    low_confidence_count = sum(
        1 for entity in entities if getattr(entity, "low_ocr_confidence", False)
    )
    if coverage and isinstance(coverage.get("low_confidence_page_count"), int):
        low_confidence_count = max(low_confidence_count, int(coverage["low_confidence_page_count"]))

    ocr_used = False
    if coverage and int(coverage.get("ocr_pages") or 0) > 0:
        ocr_used = True
    if any((getattr(entity, "source_kind", "") == "ocr") for entity in entities):
        ocr_used = True

    output_type = None
    artifact_view = None
    if artifact is not None:
        output_type = artifact.artifact_type.value
        artifact_view = ResultArtifactSummary(
            artifact_id=artifact.id,
            artifact_type=artifact.artifact_type.value,
            byte_size=artifact.byte_size,
            created_at=artifact.created_at,
            expires_at=artifact.expires_at,
        )

    source_type = job.validated_file_type.value
    logger.info(
        "job_result_built",
        job_id=str(job.id),
        status=job.status.value,
        detection_count=len(entities),
        has_artifact=artifact is not None,
    )
    return JobResultResponse(
        job_id=job.id,
        status=job.status.value,
        source_type=source_type,
        output_type=output_type,
        detection_count=len(entities),
        review_status_counts=_review_counts(entities),
        entity_category_counts=_category_counts(entities),
        method_counts=_method_counts(entities),
        analysis_coverage=coverage,
        verification_status=_verification_status(job, artifact),
        warnings=_safe_warnings(job, entities),
        artifact=artifact_view,
        created_at=job.created_at,
        expires_at=job.expires_at,
        low_confidence_count=low_confidence_count,
        ocr_used=ocr_used,
        page_count=job.page_count,
    )


def build_audit_report(
    db: Session,
    job_id: UUID,
    *,
    clock: Clock | None = None,
) -> AuditReportResponse:
    """Build a versioned audit report from safe persisted metadata only.

    Decision: no AuditEvent table. Existing ProcessingJob, DetectedEntity, and
    GeneratedArtifact rows already store the safe counts and coverage needed.
    """
    clock = clock or SystemClock()
    job = get_job(db, job_id, clock=clock)
    entities = _load_entities(db, job_id)
    artifact = _load_latest_artifact(db, job_id)
    coverage = _parse_coverage(job) or {}
    review = _review_counts(entities)

    failed_pages = coverage.get("failed_pages") or []
    failed_count = len(failed_pages) if isinstance(failed_pages, list) else int(failed_pages or 0)

    report = AuditReportResponse(
        schema_version=AUDIT_SCHEMA_VERSION,
        job_id=job.id,
        source=AuditReportSource(
            type=job.validated_file_type.value,
            validated_format=job.validated_mime_type,
            byte_size=job.byte_size,
            page_count=job.page_count,
            image_width=job.image_width,
            image_height=job.image_height,
        ),
        analysis=AuditReportAnalysis(
            status=job.status.value,
            detection_count=len(entities),
            entity_category_counts=_category_counts(entities),
            embedded_text_pages=coverage.get("embedded_text_pages"),
            ocr_pages=coverage.get("ocr_pages"),
            failed_pages=failed_count,
            fully_analyzed=coverage.get("fully_analyzed"),
            low_confidence_count=int(coverage.get("low_confidence_page_count") or 0)
            or sum(1 for entity in entities if getattr(entity, "low_ocr_confidence", False)),
            preprocessing_used=bool(coverage.get("preprocessing_used")),
        ),
        review=AuditReportReview(
            accepted=review.get("accepted", 0),
            rejected=review.get("rejected", 0),
            edited=review.get("edited", 0),
            manually_added=review.get("manually_added", 0),
            pending=review.get("pending", 0),
        ),
        output=AuditReportOutput(
            artifact_type=artifact.artifact_type.value if artifact else None,
            verification_status=_verification_status(job, artifact),
            method_counts=_method_counts(entities),
            byte_size=artifact.byte_size if artifact else None,
        ),
        privacy=AuditReportPrivacy(),
        created_at=job.created_at,
        expires_at=job.expires_at,
        warnings=_safe_warnings(job, entities),
    )
    # Validate round-trip through the schema (extra fields forbidden).
    validated = AuditReportResponse.model_validate(report.model_dump(mode="json"))
    logger.info(
        "audit_report_generated",
        job_id=str(job.id),
        schema_version=AUDIT_SCHEMA_VERSION,
        detection_count=len(entities),
        has_artifact=artifact is not None,
    )
    return validated


def assert_result_payload_is_safe(payload: dict[str, Any]) -> None:
    """Raise if a result/audit payload appears to include sensitive fields."""
    banned = {
        "storage_key",
        "original_filename",
        "filename",
        "path",
        "ocr_text",
        "extracted_text",
        "full_text",
        "pseudonym_mapping",
        "detected_value",
    }

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in banned:
                    raise AppError(
                        code="PRIVACY_VIOLATION",
                        message="Result payload failed privacy validation.",
                        status_code=500,
                    )
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(payload)
