"""Review and anonymization enums."""

from enum import StrEnum

from app.processing.detection.types import EntityType


class ReviewStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EDITED = "edited"
    MANUALLY_ADDED = "manually_added"


class AnonymizationMethod(StrEnum):
    REPLACEMENT = "replacement"
    REDACTION = "redaction"
    MASKING = "masking"
    PSEUDONYMIZE = "pseudonymize"


SUPPORTED_ENTITY_TYPES: frozenset[str] = frozenset(e.value for e in EntityType)
SUPPORTED_REVIEW_STATUSES: frozenset[str] = frozenset(s.value for s in ReviewStatus)
SUPPORTED_METHODS: frozenset[str] = frozenset(m.value for m in AnonymizationMethod)

# Statuses that cause transformation when default "accept pending" is enabled.
TRANSFORMABLE_STATUSES: frozenset[str] = frozenset(
    {
        ReviewStatus.PENDING,
        ReviewStatus.ACCEPTED,
        ReviewStatus.EDITED,
        ReviewStatus.MANUALLY_ADDED,
    }
)
