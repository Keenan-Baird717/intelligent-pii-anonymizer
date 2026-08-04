from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import settings
from app.schemas.common import FiniteFloat, FiniteRectMixin


class ReviewStatusValue(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    edited = "edited"
    manually_added = "manually_added"


class AnonymizationMethodValue(str, Enum):
    replacement = "replacement"
    redaction = "redaction"
    masking = "masking"
    pseudonymize = "pseudonymize"


class PdfRectSchema(FiniteRectMixin, BaseModel):
    model_config = ConfigDict(extra="forbid")

    x0: FiniteFloat
    y0: FiniteFloat
    x1: FiniteFloat
    y1: FiniteFloat

    @model_validator(mode="after")
    def validate_geometry(self) -> "PdfRectSchema":
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("Rectangle coordinates must form a non-inverted box.")
        width = self.x1 - self.x0
        height = self.y1 - self.y0
        if width < 0 or height < 0:
            raise ValueError("Rectangle size must be non-negative.")
        return self


class DocumentEntityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    entity_type: str
    confidence: FiniteFloat | None = None
    detection_source: str
    recognizer_name: str
    checksum_valid: bool | None = None
    start: int
    end: int
    text: str | None = None
    page_number: int
    rectangles: list[PdfRectSchema]
    review_status: str
    anonymization_method: str
    manually_added: bool
    edited: bool
    source_kind: str = "embedded_text"
    ocr_confidence: FiniteFloat | None = None
    low_ocr_confidence: bool = False
    preprocessing_used: bool = False
    coordinate_space: str = "pdf_points"


class AnalysisCoverageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_pages: int = Field(default=0, ge=0)
    embedded_text_pages: int = Field(default=0, ge=0)
    ocr_pages: int = Field(default=0, ge=0)
    failed_pages: list[int] = Field(default_factory=list, max_length=500)
    fully_analyzed: bool = True
    preprocessing_used: bool = False
    low_confidence_page_count: int = Field(default=0, ge=0)
    image_width: int | None = Field(default=None, ge=0)
    image_height: int | None = Field(default=None, ge=0)
    average_ocr_confidence: FiniteFloat | None = None
    low_confidence_warning: bool = False


class AnalyzeDocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    status: str
    page_count: int = Field(ge=0)
    pages_with_text: int = Field(ge=0)
    pages_needing_ocr: list[int] = Field(default_factory=list, max_length=500)
    detection_count: int = Field(ge=0)
    warning_code: str | None = None
    warning_message: str | None = None
    entities: list[DocumentEntityResponse]
    coverage: AnalysisCoverageResponse | None = None


class EntityListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: list[DocumentEntityResponse]


class PatchEntityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: ReviewStatusValue | None = None
    entity_type: str | None = Field(default=None, min_length=1, max_length=64)
    anonymization_method: AnonymizationMethodValue | None = None
    rectangles: list[PdfRectSchema] | None = None
    page_number: int | None = Field(default=None, ge=1)

    @field_validator("rectangles")
    @classmethod
    def validate_rect_count(cls, value: list[PdfRectSchema] | None) -> list[PdfRectSchema] | None:
        if value is not None and len(value) > settings.max_rectangles_per_entity:
            raise ValueError("Too many rectangles for one entity.")
        return value


class ManualEntityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    rectangle: PdfRectSchema
    entity_type: str = Field(default="OTHER", min_length=1, max_length=64)


class AnonymizeDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_method: AnonymizationMethodValue = AnonymizationMethodValue.redaction


class ArtifactMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: UUID
    job_id: UUID
    artifact_type: str
    byte_size: int = Field(ge=0)
    created_at: datetime
    expires_at: datetime


class AnonymizeDocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    status: str
    artifact: ArtifactMetadataResponse
    redacted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list, max_length=50)
