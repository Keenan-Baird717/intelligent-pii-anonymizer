"""Overlap resolution unit tests."""

from app.processing.detection.models import CandidateEntity
from app.processing.detection.overlap import resolve_overlaps
from app.processing.detection.types import DetectionSource, EntityType


def _cand(
    entity_type: str,
    start: int,
    end: int,
    confidence: float,
    source: str,
    name: str,
    checksum_valid: bool | None = None,
    is_manual: bool = False,
) -> CandidateEntity:
    return CandidateEntity(
        entity_type=entity_type,
        start=start,
        end=end,
        text="x" * (end - start),
        confidence=confidence,
        detection_source=source,
        recognizer_name=name,
        checksum_valid=checksum_valid,
        is_manual=is_manual,
    )


def test_exact_duplicate_merge() -> None:
    a = _cand(EntityType.EMAIL_ADDRESS, 0, 10, 0.9, DetectionSource.REGEX, "regex")
    b = _cand(EntityType.EMAIL_ADDRESS, 0, 10, 0.8, DetectionSource.PRESIDIO, "presidio")
    resolved = resolve_overlaps([a, b])
    assert len(resolved) == 1
    assert resolved[0].detection_source == DetectionSource.REGEX


def test_checksum_credit_card_outranks_generic_number_span() -> None:
    card = _cand(
        EntityType.CREDIT_CARD,
        0,
        16,
        0.97,
        DetectionSource.REGEX_CHECKSUM,
        "luhn",
        checksum_valid=True,
    )
    location = _cand(EntityType.LOCATION, 0, 16, 0.9, DetectionSource.SPACY, "spacy")
    resolved = resolve_overlaps([location, card])
    assert len(resolved) == 1
    assert resolved[0].entity_type == EntityType.CREDIT_CARD


def test_postal_code_outranks_location() -> None:
    postal = _cand(
        EntityType.CANADIAN_POSTAL_CODE,
        5,
        12,
        0.93,
        DetectionSource.REGEX,
        "postal",
    )
    location = _cand(EntityType.LOCATION, 5, 12, 0.95, DetectionSource.SPACY, "spacy")
    resolved = resolve_overlaps([location, postal])
    assert resolved[0].entity_type == EntityType.CANADIAN_POSTAL_CODE


def test_partial_overlap_deterministic() -> None:
    left = _cand(EntityType.PERSON, 0, 10, 0.7, DetectionSource.SPACY, "a")
    right = _cand(EntityType.ORGANIZATION, 5, 15, 0.7, DetectionSource.SPACY, "b")
    resolved = resolve_overlaps([left, right])
    assert len(resolved) == 1


def test_manual_detection_highest_priority() -> None:
    auto = _cand(EntityType.PERSON, 0, 5, 0.99, DetectionSource.REGEX_CHECKSUM, "auto")
    manual = _cand(
        EntityType.CUSTOM_IDENTIFIER,
        0,
        5,
        0.5,
        DetectionSource.MANUAL,
        "manual",
        is_manual=True,
    )
    resolved = resolve_overlaps([auto, manual])
    assert resolved[0].entity_type == EntityType.CUSTOM_IDENTIFIER


def test_stable_ordering_by_start() -> None:
    a = _cand(EntityType.EMAIL_ADDRESS, 20, 30, 0.9, DetectionSource.REGEX, "e")
    b = _cand(EntityType.PHONE_NUMBER, 0, 12, 0.9, DetectionSource.REGEX, "p")
    resolved = resolve_overlaps([a, b])
    assert [r.start for r in resolved] == [0, 20]
