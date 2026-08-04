from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.services.ingestion.clock import Clock, SystemClock
from app.services.ingestion.storage import resolve_storage_path
from app.services.ingestion.upload import get_job
from app.services.pdf.analysis import _require_pdf_job


@dataclass(frozen=True)
class SourceFile:
    path: Path
    media_type: str
    filename: str


def get_source_pdf(
    db: Session,
    job_id: UUID,
    *,
    clock: Clock | None = None,
    root: Path | None = None,
) -> SourceFile:
    clock = clock or SystemClock()
    job = get_job(db, job_id, clock=clock)
    _require_pdf_job(job)
    path = resolve_storage_path(job.storage_key, root=root)
    if not path.exists():
        raise AppError(
            code="STORAGE_FAILURE",
            message="The source file is unavailable.",
            status_code=500,
        )
    return SourceFile(
        path=path,
        media_type="application/pdf",
        filename="anonymized-source.pdf",
    )
