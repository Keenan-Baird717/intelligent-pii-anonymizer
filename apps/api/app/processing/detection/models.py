from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CandidateEntity:
    entity_type: str
    start: int
    end: int
    text: str
    confidence: float
    detection_source: str
    recognizer_name: str
    checksum_valid: bool | None = None
    normalized_value: str | None = None
    explanation: str = ""
    is_manual: bool = False
    discarded_by: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResolvedEntity:
    entity_type: str
    start: int
    end: int
    text: str
    confidence: float
    detection_source: str
    recognizer_name: str
    checksum_valid: bool | None
    normalized_value: str | None
    explanation: str
    overlap_resolution: str
