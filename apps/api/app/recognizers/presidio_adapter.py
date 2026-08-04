"""Presidio and spaCy integration. NLP resources load once per process."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.core.errors import AppError
from app.core.logging import get_logger
from app.processing.detection.models import CandidateEntity
from app.processing.detection.types import PRESIDIO_TYPE_MAP, DetectionSource, EntityType

logger = get_logger(__name__)


@dataclass(slots=True)
class NlpBundle:
    analyzer: Any
    spacy_available: bool


@lru_cache(maxsize=1)
def get_nlp_bundle() -> NlpBundle:
    """Load Presidio Analyzer and spaCy model once. Fail clearly if model missing."""
    try:
        import spacy
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
    except ImportError as exc:
        raise AppError(
            code="NLP_DEPENDENCY_MISSING",
            message="Required NLP dependencies are not installed.",
            status_code=500,
        ) from exc

    model_name = "en_core_web_sm"
    if not spacy.util.is_package(model_name):
        raise AppError(
            code="SPACY_MODEL_MISSING",
            message=(
                "spaCy model en_core_web_sm is not installed. "
                "Install it during image build or via: python -m spacy download en_core_web_sm"
            ),
            status_code=500,
        )

    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": model_name}],
        }
    )
    nlp_engine = provider.create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    logger.info("nlp_bundle_loaded", model=model_name, engine="presidio_spacy")
    return NlpBundle(analyzer=analyzer, spacy_available=True)


def run_presidio_and_spacy(text: str, language: str = "en") -> list[CandidateEntity]:
    bundle = get_nlp_bundle()
    results = bundle.analyzer.analyze(text=text, language=language)
    candidates: list[CandidateEntity] = []
    for result in results:
        entity_type = PRESIDIO_TYPE_MAP.get(result.entity_type, EntityType.CUSTOM_IDENTIFIER)
        recognizer = getattr(result, "recognition_metadata", {}) or {}
        recognizer_name = str(
            recognizer.get("recognizer_name")
            or getattr(result, "analysis_explanation", None)
            or result.entity_type
        )
        # Presidio's SpacyRecognizer emits PERSON/ORG/LOCATION-like labels via spaCy.
        source = (
            DetectionSource.SPACY
            if "Spacy" in recognizer_name or result.entity_type in {"PERSON", "LOCATION", "ORG"}
            else DetectionSource.PRESIDIO
        )
        # Prefer SPACY source for NER types when score comes from spaCy.
        if result.entity_type in {"PERSON", "LOCATION"} and source != DetectionSource.SPACY:
            # Still mark as presidio when pattern/context recognizers produced them.
            source = DetectionSource.PRESIDIO
        if result.entity_type == "ORG":
            entity_type = EntityType.ORGANIZATION
            source = DetectionSource.SPACY

        snippet = text[result.start : result.end]
        candidates.append(
            CandidateEntity(
                entity_type=entity_type,
                start=result.start,
                end=result.end,
                text=snippet,
                confidence=float(result.score),
                detection_source=source,
                recognizer_name=f"presidio_{result.entity_type.lower()}",
                explanation=f"Detected by Presidio/spaCy as {result.entity_type}",
            )
        )
    return candidates
