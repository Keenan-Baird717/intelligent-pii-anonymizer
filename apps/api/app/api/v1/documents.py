from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.schemas.documents import JobMetadataResponse
from app.services.ingestion.upload import ingest_upload

router = APIRouter()


def _to_response(job) -> JobMetadataResponse:  # type: ignore[no-untyped-def]
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


@router.post("/documents", response_model=JobMetadataResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JobMetadataResponse:
    if file is None:
        raise AppError(code="EMPTY_FILE", message="The uploaded file is empty.", status_code=400)
    result = ingest_upload(db, file)
    return _to_response(result.job)
