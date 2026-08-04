"""Phase 7 safe result summary and JSON audit-report schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ResultArtifactSummary(BaseModel):
    artifact_id: UUID
    artifact_type: str
    byte_size: int
    created_at: datetime
    expires_at: datetime


class JobResultResponse(BaseModel):
    """Safe job result summary — never includes source content or detected values."""

    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    status: str
    source_type: str
    output_type: str | None = None
    detection_count: int = 0
    review_status_counts: dict[str, int] = Field(default_factory=dict)
    entity_category_counts: dict[str, int] = Field(default_factory=dict)
    method_counts: dict[str, int] = Field(default_factory=dict)
    analysis_coverage: dict[str, Any] | None = None
    verification_status: str | None = None
    warnings: list[str] = Field(default_factory=list)
    artifact: ResultArtifactSummary | None = None
    created_at: datetime
    expires_at: datetime
    low_confidence_count: int = 0
    ocr_used: bool = False
    page_count: int | None = None


class AuditReportSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    validated_format: str | None = None
    byte_size: int
    page_count: int | None = None
    image_width: int | None = None
    image_height: int | None = None


class AuditReportAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    detection_count: int
    entity_category_counts: dict[str, int] = Field(default_factory=dict)
    embedded_text_pages: int | None = None
    ocr_pages: int | None = None
    failed_pages: int = 0
    fully_analyzed: bool | None = None
    low_confidence_count: int = 0
    preprocessing_used: bool = False


class AuditReportReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: int = 0
    rejected: int = 0
    edited: int = 0
    manually_added: int = 0
    pending: int = 0


class AuditReportOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_type: str | None = None
    verification_status: str | None = None
    method_counts: dict[str, int] = Field(default_factory=dict)
    byte_size: int | None = None


class AuditReportPrivacy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_values_included: bool = False
    original_content_included: bool = False
    pseudonym_mapping_included: bool = False


class AuditReportResponse(BaseModel):
    """Versioned safe audit report generated from persisted metadata only."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    job_id: UUID
    source: AuditReportSource
    analysis: AuditReportAnalysis
    review: AuditReportReview
    output: AuditReportOutput
    privacy: AuditReportPrivacy = Field(default_factory=AuditReportPrivacy)
    created_at: datetime
    expires_at: datetime
    warnings: list[str] = Field(default_factory=list)
