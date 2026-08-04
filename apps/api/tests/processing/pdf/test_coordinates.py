"""Coordinate mapping tests — map via span offsets, never string search."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import AppError
from app.processing.pdf.constants import PAGE_SEPARATOR
from app.processing.pdf.coordinates import map_entity, map_offsets_to_rectangles
from app.processing.pdf.extract import extract_document
from tests.helpers.fictional_files import (
    make_pdf_with_repeated_token,
    make_pdf_with_text,
    write_bytes,
)


def _alpha_spans(doc) -> list[tuple[int, int, int]]:  # type: ignore[no-untyped-def]
    """Collect (start, end, page) for each 'alpha' span using the span index only."""
    found: list[tuple[int, int, int]] = []
    for page in doc.pages:
        for span in page.spans:
            token = doc.full_text[span.start : span.end]
            if token == "alpha":
                found.append((span.start, span.end, span.page_number))
    return found


def test_second_alpha_maps_to_different_rect_than_first(tmp_path: Path) -> None:
    path = write_bytes(tmp_path / "alpha.pdf", make_pdf_with_repeated_token(token="alpha"))
    doc = extract_document(path)
    alphas = _alpha_spans(doc)
    assert len(alphas) == 2

    first_start, first_end, _ = alphas[0]
    second_start, second_end, _ = alphas[1]
    assert first_start != second_start

    first_rects = map_offsets_to_rectangles(doc, first_start, first_end)
    second_rects = map_offsets_to_rectangles(doc, second_start, second_end)
    assert first_rects and second_rects

    first_bbox = first_rects[0].bbox
    second_bbox = second_rects[0].bbox
    # Same token text, different geometry — proves offset-based mapping, not string search.
    assert (first_bbox.x0, first_bbox.y0, first_bbox.x1, first_bbox.y1) != (
        second_bbox.x0,
        second_bbox.y0,
        second_bbox.x1,
        second_bbox.y1,
    )
    assert first_bbox.y0 != second_bbox.y0

    mapping = map_entity(doc, second_start, second_end)
    assert mapping.start == second_start
    assert mapping.end == second_end
    assert mapping.rectangles


def test_map_repeated_alpha_on_different_pages(tmp_path: Path) -> None:
    path = write_bytes(
        tmp_path / "pages.pdf",
        make_pdf_with_text(["alpha alpha contact", "beta gamma alpha"]),
    )
    doc = extract_document(path)
    alphas = _alpha_spans(doc)
    assert len(alphas) >= 3
    pages_seen = {page for _, _, page in alphas}
    assert 1 in pages_seen and 2 in pages_seen

    first_start, first_end, first_page = alphas[0]
    last_start, last_end, last_page = alphas[-1]
    first_rects = map_offsets_to_rectangles(doc, first_start, first_end)
    last_rects = map_offsets_to_rectangles(doc, last_start, last_end)
    assert first_rects and last_rects
    assert all(r.page_number == first_page for r in first_rects)
    assert last_rects[0].page_number == last_page
    assert first_page != last_page


def test_separator_only_entity_fails(tmp_path: Path) -> None:
    path = write_bytes(
        tmp_path / "sep.pdf",
        make_pdf_with_text(["hello world enough text", "other page enough text"]),
    )
    doc = extract_document(path)
    sep_start = len(doc.pages[0].text)
    sep_end = sep_start + len(PAGE_SEPARATOR)
    assert doc.full_text[sep_start:sep_end] == PAGE_SEPARATOR
    with pytest.raises(AppError) as exc_info:
        map_offsets_to_rectangles(doc, sep_start, sep_end)
    assert exc_info.value.code == "ENTITY_MAPPING_FAILED"
