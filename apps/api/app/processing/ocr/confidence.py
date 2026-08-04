"""OCR vs detection confidence combination — keep scores separate."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True, slots=True)
class CombinedConfidence:
    detection_confidence: float | None
    ocr_confidence: float | None  # 0-1
    final_confidence: float | None
    low_ocr_confidence: bool
    review_priority: float


def combine_confidence(
    *,
    detection_confidence: float | None,
    ocr_confidence: float | None,
    checksum_valid: bool | None = None,
    manually_added: bool = False,
    low_ocr_confidence: bool = False,
) -> CombinedConfidence:
    """
    Conservative combination rule:

    - Never replace detection_confidence with OCR confidence.
    - Aggregate OCR confidence is supplied already averaged across covered words.
    - Checksum-invalid entities are not promoted by high OCR confidence.
    - Manual rectangles receive the highest review priority.
    - Low OCR confidence is surfaced for careful human review.
    """
    if manually_added:
        return CombinedConfidence(
            detection_confidence=detection_confidence,
            ocr_confidence=ocr_confidence,
            final_confidence=1.0,
            low_ocr_confidence=False,
            review_priority=1.0,
        )

    det = detection_confidence
    ocr = ocr_confidence
    threshold = settings.ocr_low_confidence_threshold / 100.0
    low = low_ocr_confidence or (ocr is not None and ocr < threshold)

    if checksum_valid is False:
        # Do not promote invalid checksums.
        final = min(det, 0.4) if det is not None else 0.2
        if ocr is not None:
            final = min(final, ocr)
        return CombinedConfidence(
            detection_confidence=det,
            ocr_confidence=ocr,
            final_confidence=final,
            low_ocr_confidence=low,
            review_priority=final,
        )

    if checksum_valid is True and det is not None:
        final = max(det, 0.85)
        priority = final
        if low:
            priority = min(priority, 0.75)
        return CombinedConfidence(
            detection_confidence=det,
            ocr_confidence=ocr,
            final_confidence=final,
            low_ocr_confidence=low,
            review_priority=priority,
        )

    if det is None and ocr is None:
        return CombinedConfidence(None, None, None, low, 0.5 if not low else 0.35)

    if det is None:
        final = (ocr or 0.0) * 0.85
        return CombinedConfidence(det, ocr, final, low, final)

    if ocr is None:
        return CombinedConfidence(det, ocr, det, low, det if not low else det * 0.9)

    # Geometric-ish conservative blend weighted toward detector.
    final = (det * 0.7) + (ocr * 0.3)
    if low:
        final *= 0.9
    return CombinedConfidence(
        detection_confidence=det,
        ocr_confidence=ocr,
        final_confidence=final,
        low_ocr_confidence=low,
        review_priority=final,
    )
