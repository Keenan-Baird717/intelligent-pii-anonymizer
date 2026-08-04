"""Explicit, deterministic overlap and duplicate resolution."""

from __future__ import annotations

from app.processing.detection.models import CandidateEntity, ResolvedEntity
from app.processing.detection.types import ENTITY_SPECIFICITY, SOURCE_PRIORITY


def resolve_overlaps(candidates: list[CandidateEntity]) -> list[ResolvedEntity]:
    """Resolve exact duplicates and overlapping spans into a deterministic winner set."""
    if not candidates:
        return []

    sorted_candidates = sorted(
        candidates,
        key=lambda c: (c.start, -(c.end - c.start), -_rank_tuple(c)[0]),
    )

    winners: list[CandidateEntity] = []
    for candidate in sorted_candidates:
        conflicting = [w for w in winners if _overlaps(candidate, w)]
        if not conflicting:
            winners.append(candidate)
            continue

        keep_candidate = True
        to_remove: list[CandidateEntity] = []
        for existing in conflicting:
            winner, loser, reason = _choose_winner(candidate, existing)
            if winner is candidate:
                to_remove.append(existing)
                candidate.discarded_by.append(f"{reason}:{existing.recognizer_name}")
            else:
                existing.discarded_by.append(f"{reason}:{candidate.recognizer_name}")
                keep_candidate = False
                break
        for removed in to_remove:
            winners.remove(removed)
        if keep_candidate:
            winners.append(candidate)

    winners.sort(key=lambda c: (c.start, c.end, c.entity_type))
    return [
        ResolvedEntity(
            entity_type=c.entity_type,
            start=c.start,
            end=c.end,
            text=c.text,
            confidence=c.confidence,
            detection_source=c.detection_source,
            recognizer_name=c.recognizer_name,
            checksum_valid=c.checksum_valid,
            normalized_value=c.normalized_value,
            explanation=c.explanation,
            overlap_resolution=(
                "selected"
                if not c.discarded_by
                else f"selected; superseded={','.join(c.discarded_by)}"
            ),
        )
        for c in winners
    ]


def _overlaps(a: CandidateEntity, b: CandidateEntity) -> bool:
    return a.start < b.end and b.start < a.end


def _rank_tuple(candidate: CandidateEntity) -> tuple[int, int, int, float, int, str]:
    specificity = ENTITY_SPECIFICITY.get(candidate.entity_type, 0)
    source = SOURCE_PRIORITY.get(candidate.detection_source, 0)
    checksum_bonus = 0
    if candidate.checksum_valid is True:
        checksum_bonus = 50
    elif candidate.checksum_valid is False:
        checksum_bonus = -20
    manual_bonus = 1000 if candidate.is_manual else 0
    span_length = candidate.end - candidate.start
    return (
        manual_bonus + checksum_bonus + specificity,
        source,
        specificity,
        candidate.confidence,
        span_length,
        candidate.recognizer_name,
    )


def _choose_winner(
    left: CandidateEntity,
    right: CandidateEntity,
) -> tuple[CandidateEntity, CandidateEntity, str]:
    # Exact span + type merge prefers higher-ranked source.
    if (
        left.start == right.start
        and left.end == right.end
        and left.entity_type == right.entity_type
    ):
        if _rank_tuple(left) >= _rank_tuple(right):
            return left, right, "exact_duplicate_merge"
        return right, left, "exact_duplicate_merge"

    left_rank = _rank_tuple(left)
    right_rank = _rank_tuple(right)
    if left_rank > right_rank:
        return left, right, "overlap_priority"
    if right_rank > left_rank:
        return right, left, "overlap_priority"
    # Stable deterministic tie-break: earlier start, then recognizer name.
    if (left.start, left.recognizer_name) <= (right.start, right.recognizer_name):
        return left, right, "deterministic_tiebreak"
    return right, left, "deterministic_tiebreak"
