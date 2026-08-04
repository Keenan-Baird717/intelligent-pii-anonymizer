"""Resolve overlaps among reviewed entities after human review."""

from __future__ import annotations

from app.core.errors import AppError
from app.processing.anonymization.models import ValidatedReviewedEntity
from app.processing.anonymization.types import TRANSFORMABLE_STATUSES, ReviewStatus
from app.processing.detection.types import ENTITY_SPECIFICITY, SOURCE_PRIORITY


def select_transformable_entities(
    entities: list[ValidatedReviewedEntity],
) -> tuple[list[ValidatedReviewedEntity], list[ValidatedReviewedEntity], list[str]]:
    """Return (to_transform, skipped_rejected, warnings)."""
    rejected = [e for e in entities if e.review_status == ReviewStatus.REJECTED]
    candidates = [e for e in entities if e.review_status in TRANSFORMABLE_STATUSES]
    resolved, warnings = resolve_reviewed_overlaps(candidates)
    return resolved, rejected, warnings


def resolve_reviewed_overlaps(
    candidates: list[ValidatedReviewedEntity],
) -> tuple[list[ValidatedReviewedEntity], list[str]]:
    if not candidates:
        return [], []

    warnings: list[str] = []
    sorted_candidates = sorted(candidates, key=lambda e: (e.start, -(e.end - e.start)))
    winners: list[ValidatedReviewedEntity] = []

    for candidate in sorted_candidates:
        conflicting = [w for w in winners if _overlaps(candidate, w)]
        if not conflicting:
            winners.append(candidate)
            continue

        keep = True
        to_remove: list[ValidatedReviewedEntity] = []
        for existing in conflicting:
            if _both_manual_conflict(candidate, existing):
                raise AppError(
                    code="CONFLICTING_MANUAL_ENTITIES",
                    message=(
                        "Two manually added or edited entities overlap. "
                        "Resolve the conflict in the review UI before anonymizing."
                    ),
                    status_code=400,
                )
            winner, loser = _choose_winner(candidate, existing)
            if winner is candidate:
                to_remove.append(existing)
                warnings.append(
                    f"Dropped overlapping entity {loser.client_id} in favor of {winner.client_id}."
                )
            else:
                keep = False
                warnings.append(
                    "Dropped overlapping entity "
                    f"{candidate.client_id} in favor of {existing.client_id}."
                )
                break
        for removed in to_remove:
            winners.remove(removed)
        if keep:
            winners.append(candidate)

    winners.sort(key=lambda e: (e.start, e.end))
    return winners, warnings


def _overlaps(a: ValidatedReviewedEntity, b: ValidatedReviewedEntity) -> bool:
    return a.start < b.end and b.start < a.end


def _both_manual_conflict(a: ValidatedReviewedEntity, b: ValidatedReviewedEntity) -> bool:
    return (
        _is_user_priority(a)
        and _is_user_priority(b)
        and not (a.start == b.start and a.end == b.end and a.entity_type == b.entity_type)
    )


def _is_user_priority(entity: ValidatedReviewedEntity) -> bool:
    return entity.manually_added or entity.review_status in {
        ReviewStatus.MANUALLY_ADDED,
        ReviewStatus.EDITED,
    }


def _rank(entity: ValidatedReviewedEntity) -> tuple[int, int, int, int, int, float, int, str]:
    manual = (
        1000 if entity.manually_added or entity.review_status == ReviewStatus.MANUALLY_ADDED else 0
    )
    edited = 800 if entity.review_status == ReviewStatus.EDITED else 0
    checksum = 50 if entity.checksum_valid is True else 0
    specificity = ENTITY_SPECIFICITY.get(entity.entity_type, 0)
    source = SOURCE_PRIORITY.get(entity.detection_source, 0)
    confidence = entity.confidence if entity.confidence is not None else 0.0
    span = entity.end - entity.start
    return (manual, edited, checksum, specificity, source, confidence, span, entity.client_id)


def _choose_winner(
    left: ValidatedReviewedEntity,
    right: ValidatedReviewedEntity,
) -> tuple[ValidatedReviewedEntity, ValidatedReviewedEntity]:
    if (
        left.start == right.start
        and left.end == right.end
        and left.entity_type == right.entity_type
    ):
        return (left, right) if _rank(left) >= _rank(right) else (right, left)
    return (left, right) if _rank(left) >= _rank(right) else (right, left)
