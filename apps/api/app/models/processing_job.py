from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JobStatus(str, enum.Enum):
    pending = "pending"
    extracting = "extracting"
    analyzing = "analyzing"
    awaiting_review = "awaiting_review"
    anonymizing = "anonymizing"
    completed = "completed"
    failed = "failed"
    expired = "expired"
    deleted = "deleted"


class SourceType(str, enum.Enum):
    document = "document"


class ValidatedFileType(str, enum.Enum):
    pdf = "pdf"
    png = "png"
    jpeg = "jpeg"


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type", native_enum=False),
        nullable=False,
        default=SourceType.document,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", native_enum=False),
        nullable=False,
        default=JobStatus.pending,
    )
    validated_file_type: Mapped[ValidatedFileType] = mapped_column(
        Enum(ValidatedFileType, name="validated_file_type", native_enum=False),
        nullable=False,
    )
    validated_extension: Mapped[str] = mapped_column(String(16), nullable=False)
    validated_mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    safe_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Phase 6 — safe analysis coverage metadata JSON (no OCR text / paths / values).
    analysis_coverage_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
