"""Service layer for text anonymization."""

from __future__ import annotations

import uuid

from app.processing.anonymization.transform import anonymize_text
from app.schemas.anonymize import AnonymizeTextRequest, AnonymizeTextResponse


def anonymize_pasted_text(request: AnonymizeTextRequest) -> AnonymizeTextResponse:
    payload = [entity.model_dump(mode="json") for entity in request.entities]
    result = anonymize_text(
        text=request.text,
        entities=payload,
        default_method=request.default_method.value,
        request_seed=str(uuid.uuid4()),
    )
    return AnonymizeTextResponse(
        anonymized_text=result.anonymized_text,
        transformed_count=result.transformed_count,
        rejected_count=result.rejected_count,
        skipped_count=result.skipped_count,
        method_counts=result.method_counts,
        warnings=result.warnings,
    )
