from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    edited = "edited"
    manually_added = "manually_added"


class AnonymizationMethod(str, enum.Enum):
    redaction = "redaction"
    masking = "masking"
    replacement = "replacement"
    pseudonymization = "pseudonymization"


class DetectedEntity(Base):
    """Persisted detection metadata. Never stores the detected substring/value."""

    __tablename__ = "detected_entities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    processing_job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    detection_source: Mapped[str] = mapped_column(String(64), nullable=False)
    recognizer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    checksum_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    # 1-based page number for display (PDF page 1 is the first page).
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # JSON list of {x0, y0, x1, y1} rectangles in PDF user-space points.
    rectangles_json: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="review_status", native_enum=False),
        nullable=False,
        default=ReviewStatus.pending,
    )
    anonymization_method: Mapped[AnonymizationMethod] = mapped_column(
        Enum(AnonymizationMethod, name="anonymization_method", native_enum=False),
        nullable=False,
        default=AnonymizationMethod.redaction,
    )
    manually_added: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Phase 6 — safe OCR metadata only (never stores OCR text or detected values).
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="embedded_text")
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_ocr_confidence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    preprocessing_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    coordinate_space: Mapped[str] = mapped_column(String(32), nullable=False, default="pdf_points")
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
