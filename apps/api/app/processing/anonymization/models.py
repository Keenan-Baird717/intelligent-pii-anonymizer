from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ValidatedReviewedEntity:
    client_id: str
    entity_type: str
    start: int
    end: int
    text: str
    review_status: str
    anonymization_method: str
    detection_source: str
    confidence: float | None
    manually_added: bool
    checksum_valid: bool | None = None
