"""Service layer for text analysis."""

from __future__ import annotations

from app.core.concurrency import regex_test_slot
from app.core.config import settings
from app.core.errors import AppError
from app.core.regex_safety import find_matches, validate_custom_recognizers
from app.processing.detection.models import CandidateEntity
from app.processing.detection.pipeline import analyze_text
from app.schemas.analyze import AnalyzeTextRequest, AnalyzeTextResponse, DetectedEntityResponse


def analyze_pasted_text(request: AnalyzeTextRequest) -> AnalyzeTextResponse:
    text = request.text
    if text.strip() == "":
        raise AppError(
            code="EMPTY_TEXT",
            message="Provide non-empty text to analyze.",
            status_code=400,
        )
    if len(text) > settings.max_text_length:
        raise AppError(
            code="TEXT_TOO_LONG",
            message=f"Text exceeds the maximum length of {settings.max_text_length} characters.",
            status_code=400,
        )

    custom_candidates: list[CandidateEntity] = []
    if request.custom_recognizers:
        with regex_test_slot():
            specs = validate_custom_recognizers(
                [item.model_dump() for item in request.custom_recognizers]
            )
            for spec in specs:
                for match in find_matches(spec, text):
                    custom_candidates.append(
                        CandidateEntity(
                            entity_type=spec.entity_type,
                            start=match.start,
                            end=match.end,
                            text=match.text,
                            confidence=0.85,
                            detection_source="custom",
                            recognizer_name=f"custom_{spec.name}",
                            explanation="Matched custom recognizer pattern",
                        )
                    )

    resolved = analyze_text(
        text,
        language=request.language,
        extra_candidates=custom_candidates or None,
    )
    if len(resolved) > settings.max_entities_per_job:
        raise AppError(
            code="TOO_MANY_ENTITIES",
            message="Too many entities were detected for a single request.",
            status_code=400,
        )

    entities = [
        DetectedEntityResponse(
            entity_type=entity.entity_type,
            start=entity.start,
            end=entity.end,
            text=entity.text,
            confidence=entity.confidence,
            detection_source=entity.detection_source,
            recognizer_name=entity.recognizer_name,
            checksum_valid=entity.checksum_valid,
            normalized_value=entity.normalized_value,
            explanation=entity.explanation,
            overlap_resolution=entity.overlap_resolution,
        )
        for entity in resolved
    ]
    return AnalyzeTextResponse(
        text=text,
        language=request.language,
        detection_count=len(entities),
        entities=entities,
    )
