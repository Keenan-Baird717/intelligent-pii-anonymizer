"""Build indexed OCR text with stable offsets — never map by substring search."""

from __future__ import annotations

from app.core.config import settings
from app.core.errors import AppError
from app.processing.ocr.adapter import RawOcrResult, raw_word_pixel_bbox
from app.processing.ocr.models import (
    OcrCoordinateMapping,
    OcrTextIndex,
    OcrWord,
    PixelBBox,
    RenderTransform,
)
from app.processing.pdf.constants import PAGE_SEPARATOR


def build_ocr_text_index(
    raw: RawOcrResult,
    *,
    page_number: int = 1,
    render_transform: RenderTransform | None = None,
    rotation: int = 0,
) -> OcrTextIndex:
    """Index a single page/image OCR result with word offsets."""
    return build_multi_page_ocr_index(
        [(page_number, raw, render_transform, rotation)],
    )


def build_multi_page_ocr_index(
    pages: list[tuple[int, RawOcrResult, RenderTransform | None, int]],
) -> OcrTextIndex:
    """
    Build multi-page OCR text.

    Separators:
    - single space between words on the same line
    - newline between lines / blocks
    - PAGE_SEPARATOR between pages
    Separators are recorded as non-drawable ranges.
    """
    pieces: list[str] = []
    words: list[OcrWord] = []
    separators: list[tuple[int, int]] = []
    offset = 0
    reading_order = 0

    for page_idx, (page_number, raw, transform, rotation) in enumerate(pages):
        if page_idx > 0:
            sep_start = offset
            pieces.append(PAGE_SEPARATOR)
            offset += len(PAGE_SEPARATOR)
            separators.append((sep_start, offset))

        sorted_words = sorted(
            raw.words,
            key=lambda w: (w.block_no, w.line_no, w.word_no, w.left, w.top),
        )
        prev_block: int | None = None
        prev_line: int | None = None

        for raw_word in sorted_words:
            if prev_block is not None and prev_line is not None:
                if raw_word.block_no != prev_block or raw_word.line_no != prev_line:
                    sep_start = offset
                    pieces.append("\n")
                    offset += 1
                    separators.append((sep_start, offset))
                else:
                    sep_start = offset
                    pieces.append(" ")
                    offset += 1
                    separators.append((sep_start, offset))

            start = offset
            pieces.append(raw_word.text)
            offset += len(raw_word.text)
            end = offset
            pixel = raw_word_pixel_bbox(raw_word).clip(
                float(raw.image_width), float(raw.image_height)
            )
            pdf_bbox = None
            if transform is not None:
                try:
                    pdf_bbox = transform.pixel_to_pdf(pixel)
                except ValueError:
                    pdf_bbox = None
            words.append(
                OcrWord(
                    page_number=page_number,
                    text=raw_word.text,
                    start=start,
                    end=end,
                    pixel_bbox=pixel,
                    confidence=raw_word.confidence,
                    line_no=raw_word.line_no,
                    block_no=raw_word.block_no,
                    reading_order=reading_order,
                    pdf_bbox=pdf_bbox,
                    rotation=rotation,
                    drawable=True,
                )
            )
            reading_order += 1
            prev_block = raw_word.block_no
            prev_line = raw_word.line_no

    return OcrTextIndex(
        full_text="".join(pieces),
        words=tuple(words),
        separator_ranges=tuple(separators),
    )


def map_ocr_offsets(
    index: OcrTextIndex,
    start: int,
    end: int,
    *,
    low_threshold: float | None = None,
) -> OcrCoordinateMapping:
    """Map entity offsets to OCR word rectangles via the index — never by string search."""
    if start < 0 or end < start or end > len(index.full_text):
        raise AppError(
            code="OCR_COORDINATE_MAPPING_FAILED",
            message="OCR coordinates could not be mapped for a detection.",
            status_code=400,
        )
    if start == end:
        raise AppError(
            code="OCR_COORDINATE_MAPPING_FAILED",
            message="OCR coordinates could not be mapped for a detection.",
            status_code=400,
        )

    # Reject ranges that are only separators.
    for sep_start, sep_end in index.separator_ranges:
        if start >= sep_start and end <= sep_end:
            raise AppError(
                code="OCR_COORDINATE_MAPPING_FAILED",
                message="OCR coordinates could not be mapped for a detection.",
                status_code=400,
            )

    overlapping = [word for word in index.words if word.end > start and word.start < end]
    if not overlapping:
        raise AppError(
            code="OCR_COORDINATE_MAPPING_FAILED",
            message="OCR coordinates could not be mapped for a detection.",
            status_code=400,
        )

    threshold = (
        float(settings.ocr_low_confidence_threshold)
        if low_threshold is None
        else float(low_threshold)
    )
    confidences = [word.confidence for word in overlapping]
    avg_conf = sum(confidences) / len(confidences)
    low = any(conf < threshold for conf in confidences) or avg_conf < threshold

    pixel_rects = _merge_line_pixel_rects(overlapping)
    pdf_rects: list[tuple[float, float, float, float]] = []
    for word in overlapping:
        if word.pdf_bbox is not None:
            pdf_rects.append(word.pdf_bbox)
    pdf_merged = _merge_pdf_rects_by_line(overlapping)

    return OcrCoordinateMapping(
        start=start,
        end=end,
        page_number=overlapping[0].page_number,
        pixel_rectangles=tuple(pixel_rects),
        pdf_rectangles=tuple(pdf_merged if pdf_merged else pdf_rects),
        ocr_confidence=avg_conf / 100.0,  # normalize 0-1 for API consistency with detector
        low_ocr_confidence=low,
    )


def _merge_line_pixel_rects(words: list[OcrWord]) -> list[PixelBBox]:
    groups: dict[tuple[int, int, int], list[PixelBBox]] = {}
    order: list[tuple[int, int, int]] = []
    for word in words:
        key = (word.page_number, word.block_no, word.line_no)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(word.pixel_bbox)

    result: list[PixelBBox] = []
    for key in order:
        boxes = groups[key]
        merged: PixelBBox | None = None
        for box in sorted(boxes, key=lambda b: (b.y0, b.x0)):
            if merged is None:
                merged = box
            else:
                merged = PixelBBox(
                    x0=min(merged.x0, box.x0),
                    y0=min(merged.y0, box.y0),
                    x1=max(merged.x1, box.x1),
                    y1=max(merged.y1, box.y1),
                )
        if merged is not None:
            result.append(merged)
    return result


def _merge_pdf_rects_by_line(
    words: list[OcrWord],
) -> list[tuple[float, float, float, float]]:
    groups: dict[tuple[int, int, int], list[tuple[float, float, float, float]]] = {}
    order: list[tuple[int, int, int]] = []
    for word in words:
        if word.pdf_bbox is None:
            continue
        key = (word.page_number, word.block_no, word.line_no)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(word.pdf_bbox)

    result: list[tuple[float, float, float, float]] = []
    for key in order:
        boxes = groups[key]
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes)
        y1 = max(b[3] for b in boxes)
        if x1 > x0 and y1 > y0:
            result.append((x0, y0, x1, y1))
    return result
