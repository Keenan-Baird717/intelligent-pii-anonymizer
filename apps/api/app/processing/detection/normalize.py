"""Normalize entity types and attach confidence scores."""

from __future__ import annotations

from app.processing.detection.confidence import normalize_confidence
from app.processing.detection.models import CandidateEntity
from app.processing.detection.types import PRESIDIO_TYPE_MAP, EntityType


def normalize_entity_type(entity_type: str) -> str:
    mapped = PRESIDIO_TYPE_MAP.get(entity_type, entity_type)
    try:
        return EntityType(mapped)
    except ValueError:
        return EntityType.CUSTOM_IDENTIFIER


def normalize_candidates(candidates: list[CandidateEntity]) -> list[CandidateEntity]:
    for candidate in candidates:
        candidate.entity_type = normalize_entity_type(candidate.entity_type)
        candidate.confidence = normalize_confidence(candidate)
    return candidates
