from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings
from app.schemas.common import FiniteFloat


class CustomRecognizerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=64)
    pattern: str = Field(..., min_length=1, max_length=2000)
    entity_type: str = Field(default="CUSTOM", min_length=1, max_length=64)
    flags: list[str] = Field(default_factory=list, max_length=4)


class AnalyzeTextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=0, max_length=200_000)
    language: str = Field(default="en", min_length=2, max_length=16)
    custom_recognizers: list[CustomRecognizerRequest] = Field(default_factory=list, max_length=50)

    @field_validator("custom_recognizers")
    @classmethod
    def validate_recognizer_count(
        cls, value: list[CustomRecognizerRequest]
    ) -> list[CustomRecognizerRequest]:
        if len(value) > settings.max_custom_recognizers:
            raise ValueError("Too many custom recognizers.")
        for item in value:
            if len(item.pattern) > settings.max_regex_pattern_length:
                raise ValueError("Custom recognizer pattern is too long.")
        return value


class DetectedEntityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str
    start: int
    end: int
    text: str
    confidence: FiniteFloat
    detection_source: str
    recognizer_name: str
    checksum_valid: bool | None = None
    normalized_value: str | None = None
    explanation: str = ""
    overlap_resolution: str = "selected"


class AnalyzeTextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    language: str
    detection_count: int
    entities: list[DetectedEntityResponse]
