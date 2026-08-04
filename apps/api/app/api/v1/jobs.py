import json
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.generated_artifact import ArtifactType
from app.models.processing_job import ValidatedFileType
from app.schemas.documents import DeleteJobResponse, JobMetadataResponse
from app.schemas.pdf_review import (
    AnalysisCoverageResponse,
    AnalyzeDocumentResponse,
    AnonymizeDocumentRequest,
    AnonymizeDocumentResponse,
    ArtifactMetadataResponse,
    DocumentEntityResponse,
    EntityListResponse,
    ManualEntityRequest,
    PatchEntityRequest,
    PdfRectSchema,
)
from app.schemas.results import JobResultResponse
from app.services.document_analysis import AnalyzeDocumentResult, EntityView, analyze_document_job
from app.services.ingestion.storage import resolve_storage_path
from app.services.ingestion.upload import delete_job, get_job
from app.services.pdf.entities import (
    create_manual_entity,
    delete_entity,
    list_entities,
    patch_entity,
)
from app.services.pdf.redaction import anonymize_pdf_job, get_artifact

router = APIRouter()

_WARNING_MESSAGES = {
    "PARTIAL_TEXT_EXTRACTION": (
        "Some pages lack extractable text. OCR was not applied to those pages."
    ),
    "PARTIAL_ANALYSIS": ("Some pages could not be analyzed. The document was not fully analyzed."),
    "OCR_LOW_CONFIDENCE": (
        "OCR confidence is low for this image. Review detections carefully; "
        "automated detection may miss sensitive information."
    ),
}


def _job_response(job) -> JobMetadataResponse:  # type: ignore[no-untyped-def]
    return JobMetadataResponse(
        job_id=job.id,
        status=job.status.value,
        file_type=job.validated_file_type.value,
        byte_size=job.byte_size,
        page_count=job.page_count,
        image_width=job.image_width,
        image_height=job.image_height,
        created_at=job.created_at,
        expires_at=job.expires_at,
        error_code=job.safe_error_code,
    )


def _entity_response(view: EntityView) -> DocumentEntityResponse:
    return DocumentEntityResponse(
        id=view.id,
        entity_type=view.entity_type,
        confidence=view.confidence,
        detection_source=view.detection_source,
        recognizer_name=view.recognizer_name,
        checksum_valid=view.checksum_valid,
        start=view.start,
        end=view.end,
        text=view.text or None,
        page_number=view.page_number,
        rectangles=[PdfRectSchema(**rect) for rect in view.rectangles],
        review_status=view.review_status,
        anonymization_method=view.anonymization_method,
        manually_added=view.manually_added,
        edited=view.edited,
        source_kind=view.source_kind,
        ocr_confidence=view.ocr_confidence,
        low_ocr_confidence=view.low_ocr_confidence,
        preprocessing_used=view.preprocessing_used,
        coordinate_space=view.coordinate_space,
    )


def _analyze_response(result: AnalyzeDocumentResult, page_count: int) -> AnalyzeDocumentResponse:
    warning_code = result.warnings[0] if result.warnings else None
    warning_message = _WARNING_MESSAGES.get(warning_code) if warning_code else None
    coverage = AnalysisCoverageResponse(
        total_pages=result.coverage.total_pages,
        embedded_text_pages=result.coverage.embedded_text_pages,
        ocr_pages=result.coverage.ocr_pages,
        failed_pages=list(result.coverage.failed_pages),
        fully_analyzed=result.coverage.fully_analyzed,
        preprocessing_used=result.coverage.preprocessing_used,
        low_confidence_page_count=result.coverage.low_confidence_page_count,
        image_width=result.coverage.image_width,
        image_height=result.coverage.image_height,
        average_ocr_confidence=result.coverage.average_ocr_confidence,
        low_confidence_warning=result.coverage.low_confidence_warning,
    )
    return AnalyzeDocumentResponse(
        job_id=result.job_id,
        status=result.status,
        page_count=result.page_count or page_count,
        pages_with_text=len(result.pages_with_text),
        pages_needing_ocr=result.pages_needing_ocr,
        detection_count=result.detection_count,
        warning_code=warning_code,
        warning_message=warning_message,
        entities=[_entity_response(entity) for entity in result.entities],
        coverage=coverage,
    )


@router.get("/jobs/{job_id}", response_model=JobMetadataResponse)
def read_job(job_id: UUID, db: Session = Depends(get_db)) -> JobMetadataResponse:
    job = get_job(db, job_id)
    return _job_response(job)


@router.delete("/jobs/{job_id}", response_model=DeleteJobResponse)
def remove_job(job_id: UUID, db: Session = Depends(get_db)) -> DeleteJobResponse:
    delete_job(db, job_id)
    return DeleteJobResponse(job_id=job_id, deleted=True)


@router.post("/jobs/{job_id}/analyze", response_model=AnalyzeDocumentResponse)
def analyze_job(job_id: UUID, db: Session = Depends(get_db)) -> AnalyzeDocumentResponse:
    job = get_job(db, job_id)
    result = analyze_document_job(db, job_id)
    return _analyze_response(result, page_count=job.page_count or 0)


@router.get("/jobs/{job_id}/entities", response_model=EntityListResponse)
def read_entities(job_id: UUID, db: Session = Depends(get_db)) -> EntityListResponse:
    views = list_entities(db, job_id)
    return EntityListResponse(entities=[_entity_response(view) for view in views])


@router.patch("/jobs/{job_id}/entities/{entity_id}", response_model=DocumentEntityResponse)
def update_entity(
    job_id: UUID,
    entity_id: UUID,
    body: PatchEntityRequest,
    db: Session = Depends(get_db),
) -> DocumentEntityResponse:
    view = patch_entity(
        db,
        job_id,
        entity_id,
        review_status=body.review_status,
        entity_type=body.entity_type,
        anonymization_method=body.anonymization_method,
        rectangles=[rect.model_dump() for rect in body.rectangles] if body.rectangles else None,
        page_number=body.page_number,
    )
    return _entity_response(view)


@router.post("/jobs/{job_id}/entities", response_model=DocumentEntityResponse, status_code=201)
def add_manual_entity(
    job_id: UUID,
    body: ManualEntityRequest,
    db: Session = Depends(get_db),
) -> DocumentEntityResponse:
    view = create_manual_entity(
        db,
        job_id,
        page_number=body.page_number,
        rectangle=body.rectangle.model_dump(),
        entity_type=body.entity_type,
    )
    return _entity_response(view)


@router.delete("/jobs/{job_id}/entities/{entity_id}", status_code=204)
def remove_entity(job_id: UUID, entity_id: UUID, db: Session = Depends(get_db)) -> None:
    delete_entity(db, job_id, entity_id)


@router.post("/jobs/{job_id}/anonymize", response_model=AnonymizeDocumentResponse)
def anonymize_job(
    job_id: UUID,
    body: AnonymizeDocumentRequest,
    db: Session = Depends(get_db),
) -> AnonymizeDocumentResponse:
    job = get_job(db, job_id)
    if job.validated_file_type is ValidatedFileType.pdf:
        result = anonymize_pdf_job(db, job_id, default_method=body.default_method)
    else:
        from app.services.image_redaction import anonymize_image_job

        result = anonymize_image_job(db, job_id, default_method=body.default_method)
    return AnonymizeDocumentResponse(
        job_id=result.job_id,
        status=result.status,
        artifact=ArtifactMetadataResponse(
            artifact_id=result.artifact.artifact_id,
            job_id=result.artifact.job_id,
            artifact_type=result.artifact.artifact_type,
            byte_size=result.artifact.byte_size,
            created_at=result.artifact.created_at,  # type: ignore[arg-type]
            expires_at=result.artifact.expires_at,  # type: ignore[arg-type]
        ),
        redacted_count=result.redacted_count,
        rejected_count=result.rejected_count,
        warnings=result.warnings,
    )


@router.get("/jobs/{job_id}/file")
def download_source_file(job_id: UUID, db: Session = Depends(get_db)) -> FileResponse:
    job = get_job(db, job_id)
    path = resolve_storage_path(job.storage_key)
    if not path.exists():
        from app.core.errors import AppError

        raise AppError(code="JOB_NOT_FOUND", message="Job not found.", status_code=404)
    media = job.validated_mime_type or "application/octet-stream"
    if job.validated_file_type is ValidatedFileType.pdf:
        filename = "anonymized-source.pdf"
    elif job.validated_file_type is ValidatedFileType.png:
        filename = "anonymized-source.png"
    else:
        filename = "anonymized-source.jpg"
    return FileResponse(
        path=path,
        media_type=media,
        filename=filename,
        content_disposition_type="inline",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store, private",
        },
    )


@router.get("/jobs/{job_id}/artifacts/{artifact_id}")
def download_artifact(
    job_id: UUID,
    artifact_id: UUID,
    db: Session = Depends(get_db),
) -> FileResponse:
    artifact = get_artifact(db, job_id, artifact_id)
    path = resolve_storage_path(artifact.storage_key)
    if not path.exists():
        from app.core.errors import AppError

        raise AppError(code="ARTIFACT_NOT_FOUND", message="Artifact not found.", status_code=404)
    if artifact.artifact_type is ArtifactType.redacted_png:
        filename = "anonymized-image.png"
    elif artifact.artifact_type is ArtifactType.redacted_jpeg:
        filename = "anonymized-image.jpg"
    else:
        filename = "anonymized-document.pdf"
    return FileResponse(
        path=path,
        media_type=artifact.validated_mime_type,
        filename=filename,
        content_disposition_type="attachment",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store, private",
        },
    )


@router.get("/jobs/{job_id}/result", response_model=JobResultResponse)
def read_job_result(job_id: UUID, db: Session = Depends(get_db)) -> JobResultResponse:
    from app.services.results import assert_result_payload_is_safe, build_job_result

    result = build_job_result(db, job_id)
    assert_result_payload_is_safe(result.model_dump(mode="json"))
    return result


@router.get("/jobs/{job_id}/audit-report")
def download_audit_report(job_id: UUID, db: Session = Depends(get_db)) -> Response:
    from app.services.results import assert_result_payload_is_safe, build_audit_report

    report = build_audit_report(db, job_id)
    payload = report.model_dump(mode="json")
    assert_result_payload_is_safe(payload)
    body = json.dumps(payload, indent=2, sort_keys=True)
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="anonymization-audit-report.json"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store, private",
        },
    )
