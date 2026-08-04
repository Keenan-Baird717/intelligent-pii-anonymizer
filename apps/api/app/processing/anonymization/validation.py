"""Validate client-submitted reviewed entities. Never trust client text substrings."""

from __future__ import annotations

from app.core.config import settings
from app.core.errors import AppError
from app.processing.anonymization.models import ValidatedReviewedEntity
from app.processing.anonymization.types import (
    SUPPORTED_ENTITY_TYPES,
    SUPPORTED_METHODS,
    SUPPORTED_REVIEW_STATUSES,
    ReviewStatus,
)


def validate_anonymize_request_text(text: str) -> None:
    if text.strip() == "":
        raise AppError(
            code="EMPTY_TEXT", message="Provide non-empty text to anonymize.", status_code=400
        )
    if len(text) > settings.max_text_length:
        raise AppError(
            code="TEXT_TOO_LONG",
            message=f"Text exceeds the maximum length of {settings.max_text_length} characters.",
            status_code=400,
        )


def validate_reviewed_entities(
    text: str,
    entities: list[dict[str, object]],
    default_method: str,
) -> list[ValidatedReviewedEntity]:
    if default_method not in SUPPORTED_METHODS:
        raise AppError(
            code="UNSUPPORTED_ANONYMIZATION_METHOD",
            message=f"Unsupported anonymization method: {default_method}.",
            status_code=400,
        )

    validated: list[ValidatedReviewedEntity] = []
    for index, raw in enumerate(entities):
        validated.append(_validate_one(text, raw, default_method, index))
    return validated


def _validate_one(
    text: str,
    raw: dict[str, object],
    default_method: str,
    index: int,
) -> ValidatedReviewedEntity:
    try:
        start = int(str(raw["start"]))
        end = int(str(raw["end"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError(
            code="INVALID_ENTITY_SPAN",
            message=f"Entity at index {index} has an invalid start or end offset.",
            status_code=400,
        ) from exc

    if start < 0:
        raise AppError(
            code="INVALID_ENTITY_SPAN",
            message=f"Entity at index {index} has a negative start offset.",
            status_code=400,
        )
    if end <= start:
        raise AppError(
            code="INVALID_ENTITY_SPAN",
            message=f"Entity at index {index} must have end greater than start.",
            status_code=400,
        )
    if end > len(text):
        raise AppError(
            code="INVALID_ENTITY_SPAN",
            message=f"Entity at index {index} end offset exceeds text length.",
            status_code=400,
        )

    entity_type = str(raw.get("entity_type", ""))
    if entity_type not in SUPPORTED_ENTITY_TYPES:
        raise AppError(
            code="UNSUPPORTED_ENTITY_TYPE",
            message=f"Unsupported entity type for entity at index {index}.",
            status_code=400,
        )

    review_status = str(raw.get("review_status", ReviewStatus.PENDING))
    if review_status not in SUPPORTED_REVIEW_STATUSES:
        raise AppError(
            code="INVALID_REVIEW_STATUS",
            message=f"Unsupported review status for entity at index {index}.",
            status_code=400,
        )

    method = str(raw.get("anonymization_method") or default_method)
    if method not in SUPPORTED_METHODS:
        raise AppError(
            code="UNSUPPORTED_ANONYMIZATION_METHOD",
            message=f"Unsupported anonymization method for entity at index {index}.",
            status_code=400,
        )

    manually_added = (
        bool(raw.get("manually_added", False)) or review_status == ReviewStatus.MANUALLY_ADDED
    )
    detection_source = str(
        raw.get("detection_source") or ("manual" if manually_added else "unknown")
    )

    confidence_raw = raw.get("confidence")
    confidence: float | None
    if confidence_raw is None or manually_added or review_status == ReviewStatus.EDITED:
        confidence = (
            None
            if manually_added
            or review_status
            in {
                ReviewStatus.MANUALLY_ADDED,
                ReviewStatus.EDITED,
            }
            else _optional_float(confidence_raw)
        )
    else:
        confidence = _optional_float(confidence_raw)

    client_id = str(raw.get("client_id") or f"entity-{index}")
    # Always derive substring from validated spans — never trust client-supplied text.
    derived = text[start:end]

    checksum_valid = raw.get("checksum_valid")
    checksum: bool | None
    if checksum_valid is None:
        checksum = None
    else:
        checksum = bool(checksum_valid)

    return ValidatedReviewedEntity(
        client_id=client_id,
        entity_type=entity_type,
        start=start,
        end=end,
        text=derived,
        review_status=review_status,
        anonymization_method=method,
        detection_source=detection_source,
        confidence=confidence,
        manually_added=manually_added,
        checksum_valid=checksum,
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
