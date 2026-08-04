"""Redaction application and post-redaction text verification."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from app.core.errors import AppError
from app.processing.pdf.coordinates import map_offsets_to_rectangles
from app.processing.pdf.extract import extract_document
from app.processing.pdf.redact import apply_redactions
from app.processing.pdf.types import BBox
from app.processing.pdf.verify import verify_redaction
from tests.helpers.fictional_files import make_pdf_with_text, write_bytes


def test_redaction_removes_forbidden_keeps_required(tmp_path: Path) -> None:
    source = write_bytes(
        tmp_path / "src.pdf",
        make_pdf_with_text(["SECRETTOKEN keepme visible text", "keepme again visible"]),
    )
    doc = extract_document(source)
    target_start = target_end = None
    for page in doc.pages:
        for span in page.spans:
            if doc.full_text[span.start : span.end] == "SECRETTOKEN":
                target_start, target_end = span.start, span.end
                break
        if target_start is not None:
            break
    assert target_start is not None and target_end is not None

    mapped = map_offsets_to_rectangles(doc, target_start, target_end)
    rectangles = [(r.page_number, r.bbox) for r in mapped]
    output = tmp_path / "out.pdf"
    apply_redactions(source, output, rectangles)

    # Source must remain unchanged.
    original = extract_document(source)
    assert "SECRETTOKEN" in original.full_text

    verify_redaction(output, forbidden_substrings=["SECRETTOKEN"], required_substrings=["keepme"])

    with fitz.open(output) as redacted:
        text = "".join(redacted.load_page(i).get_text("text") for i in range(redacted.page_count))
    assert "SECRETTOKEN" not in text
    assert "keepme" in text


def test_verify_fails_when_forbidden_still_present(tmp_path: Path) -> None:
    source = write_bytes(
        tmp_path / "src.pdf",
        make_pdf_with_text(["LEAKEDVALUE remains visible in document"]),
    )
    output = tmp_path / "copy.pdf"
    apply_redactions(source, output, [])  # copy only — no rectangles
    with pytest.raises(AppError) as exc_info:
        verify_redaction(output, forbidden_substrings=["LEAKEDVALUE"], required_substrings=[])
    assert exc_info.value.code == "REDACTION_VERIFICATION_FAILED"


def test_apply_redactions_refuses_in_place(tmp_path: Path) -> None:
    source = write_bytes(
        tmp_path / "same.pdf",
        make_pdf_with_text(["enough fictional content for extraction"]),
    )
    with pytest.raises(AppError) as exc_info:
        apply_redactions(source, source, [(1, BBox(x0=10, y0=10, x1=50, y1=30))])
    assert exc_info.value.code == "REDACTION_FAILED"
