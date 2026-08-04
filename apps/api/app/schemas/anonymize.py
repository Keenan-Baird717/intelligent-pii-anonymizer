from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings
from app.schemas.common import FiniteFloat


class ReviewStatusLiteral(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    edited = "edited"
    manually_added = "manually_added"


class AnonymizationMethodLiteral(str, Enum):
    replacement = "replacement"
    redaction = "redaction"
    masking = "masking"
    pseudonymize = "pseudonymize"


class ReviewedEntityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str | None = Field(default=None, max_length=128)
    entity_type: str = Field(..., min_length=1, max_length=64)
    start: int = Field(..., ge=0)
    end: int = Field(..., ge=0)
    review_status: ReviewStatusLiteral
    anonymization_method: AnonymizationMethodLiteral | None = None
    detection_source: str | None = Field(default=None, max_length=64)
    confidence: FiniteFloat | None = Field(default=None, ge=0.0, le=1.0)
    manually_added: bool = False
    checksum_valid: bool | None = None
    # Client-supplied text is ignored; server derives from spans.

    @field_validator("end")
    @classmethod
    def end_after_start(cls, value: int, info: object) -> int:
        data = getattr(info, "data", {}) or {}
        start = data.get("start")
        if isinstance(start, int) and value < start:
            raise ValueError("end must be >= start")
        return value


class AnonymizeTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=0, max_length=200_000)
    entities: list[ReviewedEntityInput] = Field(default_factory=list)
    default_method: AnonymizationMethodLiteral = AnonymizationMethodLiteral.replacement
    language: str = Field(default="en", min_length=2, max_length=16)

    @field_validator("entities")
    @classmethod
    def validate_entity_count(cls, value: list[ReviewedEntityInput]) -> list[ReviewedEntityInput]:
        if len(value) > settings.max_entities_per_job:
            raise ValueError("Too many entities in the request.")
        return value


class AnonymizeTextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anonymized_text: str
    transformed_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    method_counts: dict[str, int]
    warnings: list[str] = Field(default_factory=list, max_length=50)
