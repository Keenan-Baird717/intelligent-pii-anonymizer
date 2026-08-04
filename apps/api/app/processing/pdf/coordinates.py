from __future__ import annotations

from app.core.config import settings
from app.core.errors import AppError
from app.processing.pdf.constants import PAGE_SEPARATOR
from app.processing.pdf.index import validate_offsets
from app.processing.pdf.types import (
    BBox,
    DocumentEntityMapping,
    ExtractedDocument,
    MappedRectangle,
    PositionedSpan,
)


def map_offsets_to_rectangles(
    document: ExtractedDocument,
    start: int,
    end: int,
    *,
    padding_pts: float | None = None,
) -> list[MappedRectangle]:
    """Map global character offsets to PDF rectangles via span indices — never by string search."""
    validate_offsets(document, start, end)
    padding = settings.redaction_padding_pts if padding_pts is None else padding_pts

    if start == end:
        raise AppError(
            code="ENTITY_MAPPING_FAILED",
            message="Entity offsets could not be mapped to the document.",
            status_code=400,
        )

    # Skip ranges that are entirely within a page separator.
    slice_text = document.full_text[start:end]
    if slice_text and set(slice_text) <= set(PAGE_SEPARATOR):
        raise AppError(
            code="ENTITY_MAPPING_FAILED",
            message="Entity offsets could not be mapped to the document.",
            status_code=400,
        )

    overlapping: list[tuple[PositionedSpan, BBox]] = []
    page_dims: dict[int, tuple[float, float]] = {
        page.page_number: (page.width, page.height) for page in document.pages
    }

    for page in document.pages:
        for span in page.spans:
            if span.end <= start or span.start >= end:
                continue
            # Partial word coverage still uses the full word bbox (word-level extraction).
            width, height = page_dims[span.page_number]
            bbox = span.bbox.padded(padding, width, height)
            if bbox.x1 <= bbox.x0 or bbox.y1 <= bbox.y0:
                continue
            overlapping.append((span, bbox))

    if not overlapping:
        raise AppError(
            code="ENTITY_MAPPING_FAILED",
            message="Entity offsets could not be mapped to the document.",
            status_code=400,
        )

    merged = _merge_line_rects(overlapping)
    return merged


def map_entity(
    document: ExtractedDocument,
    start: int,
    end: int,
    *,
    padding_pts: float | None = None,
) -> DocumentEntityMapping:
    rectangles = map_offsets_to_rectangles(document, start, end, padding_pts=padding_pts)
    primary_page = rectangles[0].page_number
    return DocumentEntityMapping(
        start=start,
        end=end,
        page_number=primary_page,
        rectangles=rectangles,
    )


def _merge_line_rects(
    items: list[tuple[PositionedSpan, BBox]],
) -> list[MappedRectangle]:
    """Merge adjacent/overlapping rectangles on the same page and line."""
    # Group by (page, block, line)
    groups: dict[tuple[int, int, int], list[BBox]] = {}
    order: list[tuple[int, int, int]] = []
    for span, bbox in items:
        key = (span.page_number, span.block_no, span.line_no)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(bbox)

    result: list[MappedRectangle] = []
    for key in order:
        page_number = key[0]
        rects = groups[key]
        merged: list[BBox] = []
        for bbox in sorted(rects, key=lambda b: (b.y0, b.x0)):
            if merged and merged[-1].overlaps_or_adjacent(bbox):
                merged[-1] = merged[-1].merge(bbox)
            else:
                merged.append(bbox)
        for bbox in merged:
            result.append(MappedRectangle(page_number=page_number, bbox=bbox))
    return result
