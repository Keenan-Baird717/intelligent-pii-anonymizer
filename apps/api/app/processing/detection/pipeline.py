"""Hybrid PII detection pipeline for pasted text."""

from __future__ import annotations

import time

from app.core.logging import get_logger
from app.processing.detection.models import CandidateEntity, ResolvedEntity
from app.processing.detection.normalize import normalize_candidates
from app.processing.detection.overlap import resolve_overlaps
from app.recognizers.presidio_adapter import run_presidio_and_spacy
from app.recognizers.regex_recognizers import run_regex_recognizers

logger = get_logger(__name__)


def analyze_text(
    text: str,
    language: str = "en",
    *,
    extra_candidates: list[CandidateEntity] | None = None,
) -> list[ResolvedEntity]:
    """Run the Phase 2 detection pipeline and return resolved entities.

    Never logs the submitted text or detected values.
    """
    started = time.perf_counter()
    candidates = run_regex_recognizers(text)
    nlp_candidates = run_presidio_and_spacy(text, language=language)
    candidates.extend(nlp_candidates)
    if extra_candidates:
        candidates.extend(extra_candidates)
    normalized = normalize_candidates(candidates)
    resolved = resolve_overlaps(normalized)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)

    category_counts: dict[str, int] = {}
    for entity in resolved:
        category_counts[entity.entity_type] = category_counts.get(entity.entity_type, 0) + 1

    logger.info(
        "text_analysis_completed",
        text_length=len(text),
        detection_count=len(resolved),
        category_counts=category_counts,
        duration_ms=duration_ms,
        language=language,
        status="success",
    )
    return resolved
