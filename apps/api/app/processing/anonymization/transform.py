"""Orchestrate text anonymization. Apply replacements right-to-left."""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.core.logging import get_logger
from app.processing.anonymization.masking import mask_entity
from app.processing.anonymization.models import ValidatedReviewedEntity
from app.processing.anonymization.pseudonymize import PseudonymRegistry
from app.processing.anonymization.redaction import redact_entity
from app.processing.anonymization.replacement import replace_entity
from app.processing.anonymization.review_overlap import select_transformable_entities
from app.processing.anonymization.types import AnonymizationMethod
from app.processing.anonymization.validation import (
    validate_anonymize_request_text,
    validate_reviewed_entities,
)

logger = get_logger(__name__)


@dataclass(slots=True)
class AnonymizeResult:
    anonymized_text: str
    transformed_count: int
    rejected_count: int
    skipped_count: int
    method_counts: dict[str, int]
    warnings: list[str]


def anonymize_text(
    text: str,
    entities: list[dict[str, object]],
    default_method: str,
    request_seed: str = "",
) -> AnonymizeResult:
    started = time.perf_counter()
    validate_anonymize_request_text(text)
    validated = validate_reviewed_entities(text, entities, default_method)
    to_transform, rejected, warnings = select_transformable_entities(validated)

    registry = PseudonymRegistry(seed=request_seed)
    method_counts: dict[str, int] = {}
    # Right-to-left so earlier offsets remain valid.
    ordered = sorted(to_transform, key=lambda e: e.start, reverse=True)
    result = text
    for entity in ordered:
        replacement = _apply_method(entity, registry)
        result = result[: entity.start] + replacement + result[entity.end :]
        method_counts[entity.anonymization_method] = (
            method_counts.get(entity.anonymization_method, 0) + 1
        )

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "text_anonymization_completed",
        text_length=len(text),
        reviewed_entity_count=len(validated),
        accepted_count=len(to_transform),
        rejected_count=len(rejected),
        manual_entity_count=sum(1 for e in validated if e.manually_added),
        method_counts=method_counts,
        duration_ms=duration_ms,
        status="success",
    )

    return AnonymizeResult(
        anonymized_text=result,
        transformed_count=len(to_transform),
        rejected_count=len(rejected),
        skipped_count=len(validated) - len(to_transform) - len(rejected),
        method_counts=method_counts,
        warnings=warnings,
    )


def _apply_method(entity: ValidatedReviewedEntity, registry: PseudonymRegistry) -> str:
    method = entity.anonymization_method
    if method == AnonymizationMethod.REPLACEMENT:
        return replace_entity(entity.entity_type)
    if method == AnonymizationMethod.REDACTION:
        return redact_entity(entity.text)
    if method == AnonymizationMethod.MASKING:
        return mask_entity(entity.entity_type, entity.text)
    if method == AnonymizationMethod.PSEUDONYMIZE:
        return registry.pseudonymize(entity.entity_type, entity.text)
    return replace_entity(entity.entity_type)
