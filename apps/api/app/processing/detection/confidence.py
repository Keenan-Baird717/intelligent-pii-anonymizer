"""Confidence normalization into a consistent 0.0–1.0 range.

Documented mapping (not production-grade accuracy claims):
- checksum-valid structured IDs: 0.95–0.99
- regex with structural validation: 0.85–0.92
- regex-only moderate patterns: 0.55–0.75
- Presidio scores: clamped/scaled into 0.4–0.95
- spaCy NER: clamped into 0.4–0.9
- checksum-invalid structured candidates: 0.15–0.35 (kept for explainability)
"""

from __future__ import annotations

from app.processing.detection.models import CandidateEntity
from app.processing.detection.types import DetectionSource, EntityType


def normalize_confidence(candidate: CandidateEntity) -> float:
    score = candidate.confidence

    if candidate.checksum_valid is True and candidate.entity_type in {
        EntityType.CREDIT_CARD,
        EntityType.CANADIAN_SIN,
    }:
        score = max(score, 0.95)
        candidate.detection_source = DetectionSource.REGEX_CHECKSUM
    elif candidate.checksum_valid is False and candidate.entity_type in {
        EntityType.CREDIT_CARD,
        EntityType.CANADIAN_SIN,
    }:
        score = min(score, 0.35)

    if candidate.detection_source == DetectionSource.PRESIDIO:
        score = _clamp(score, 0.4, 0.95)
    elif candidate.detection_source == DetectionSource.SPACY:
        score = _clamp(score, 0.4, 0.9)
    elif candidate.detection_source == DetectionSource.REGEX:
        if candidate.entity_type in {
            EntityType.EMAIL_ADDRESS,
            EntityType.CANADIAN_POSTAL_CODE,
            EntityType.IP_ADDRESS,
            EntityType.URL,
        }:
            score = max(score, 0.85)
        elif candidate.entity_type in {EntityType.STREET_ADDRESS, EntityType.DATE_OF_BIRTH}:
            score = _clamp(score, 0.55, 0.75)

    return round(_clamp(score, 0.0, 1.0), 4)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
