from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.generated_artifact import GeneratedArtifact
from app.services.ingestion.clock import Clock, SystemClock
from app.services.ingestion.storage import resolve_storage_path
from app.services.ingestion.upload import get_job


@dataclass(frozen=True)
class ArtifactFile:
    artifact_id: UUID
    path: Path
    media_type: str
    filename: str
    byte_size: int
    artifact_type: str
    created_at: datetime
    expires_at: datetime


def get_artifact_file(
    db: Session,
    job_id: UUID,
    artifact_id: UUID,
    *,
    clock: Clock | None = None,
    root: Path | None = None,
) -> ArtifactFile:
    clock = clock or SystemClock()
    job = get_job(db, job_id, clock=clock)
    artifact = db.get(GeneratedArtifact, artifact_id)
    if artifact is None or artifact.processing_job_id != job.id:
        raise AppError(
            code="ARTIFACT_NOT_FOUND",
            message="Artifact not found.",
            status_code=404,
        )
    path = resolve_storage_path(artifact.storage_key, root=root)
    if not path.exists():
        raise AppError(
            code="STORAGE_FAILURE",
            message="The artifact file is unavailable.",
            status_code=500,
        )
    return ArtifactFile(
        artifact_id=artifact.id,
        path=path,
        media_type=artifact.validated_mime_type,
        filename="anonymized-document.pdf",
        byte_size=artifact.byte_size,
        artifact_type=artifact.artifact_type.value,
        created_at=artifact.created_at,
        expires_at=artifact.expires_at,
    )
