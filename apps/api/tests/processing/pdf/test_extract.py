"""Unit tests for PDF text extraction and classification."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.processing.pdf.constants import PAGE_SEPARATOR
from app.processing.pdf.extract import extract_document
from tests.helpers.fictional_files import (
    make_fictional_pdf_bytes,
    make_image_only_pdf,
    make_pdf_with_repeated_token,
    make_pdf_with_text,
    write_bytes,
)


def test_extract_single_page_text(tmp_path: Path) -> None:
    path = write_bytes(tmp_path / "one.pdf", make_fictional_pdf_bytes(text="Widget Report"))
    doc = extract_document(path)
    assert len(doc.pages) == 1
    assert doc.pages[0].page_number == 1
    assert "Widget" in doc.full_text
    assert doc.pages[0].has_text is True
    assert doc.pages_with_text == [1]
    assert doc.pages_needing_ocr == []
    assert all(span.page_number == 1 for span in doc.pages[0].spans)


def test_extract_multipage_with_separator_and_repeated_token(tmp_path: Path) -> None:
    path = write_bytes(
        tmp_path / "multi.pdf",
        make_pdf_with_text(["alpha alpha contact line", "beta gamma alpha line"]),
    )
    doc = extract_document(path)
    assert len(doc.pages) == 2
    assert PAGE_SEPARATOR in doc.full_text
    assert doc.full_text.count("alpha") >= 3

    alphas = [
        (span.start, span.end, span.page_number)
        for page in doc.pages
        for span in page.spans
        if doc.full_text[span.start : span.end] == "alpha"
    ]
    assert len(alphas) >= 3
    # At least two distinct offsets for the repeated token.
    starts = {start for start, _, _ in alphas}
    assert len(starts) >= 2
    assert {page for _, _, page in alphas} == {1, 2}

    page2_spans = doc.pages[1].spans
    assert page2_spans
    assert page2_spans[0].start > len(doc.pages[0].text)


def test_extract_repeated_token_same_page_different_offsets(tmp_path: Path) -> None:
    path = write_bytes(tmp_path / "repeat.pdf", make_pdf_with_repeated_token(token="alpha"))
    doc = extract_document(path)
    alphas = [
        (span.start, span.end)
        for page in doc.pages
        for span in page.spans
        if doc.full_text[span.start : span.end] == "alpha"
    ]
    assert len(alphas) == 2
    assert alphas[0][0] != alphas[1][0]
    assert alphas[0][1] != alphas[1][1]
    assert doc.full_text[alphas[0][0] : alphas[0][1]] == "alpha"
    assert doc.full_text[alphas[1][0] : alphas[1][1]] == "alpha"


def test_ocr_required_for_image_only_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "min_pdf_text_chars", 20)
    path = write_bytes(tmp_path / "scan.pdf", make_image_only_pdf())
    with pytest.raises(AppError) as exc_info:
        extract_document(path)
    assert exc_info.value.code == "OCR_REQUIRED"
    assert exc_info.value.status_code == 422
