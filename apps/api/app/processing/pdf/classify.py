from __future__ import annotations

import re

from app.processing.pdf.types import ExtractedDocument, ExtractedPage


def count_meaningful_chars(text: str) -> int:
    """Count alphanumeric characters used for OCR-threshold decisions."""
    return sum(1 for ch in text if ch.isalnum())


def page_has_meaningful_text(page: ExtractedPage, *, min_chars: int = 1) -> bool:
    return count_meaningful_chars(page.text) >= min_chars


def is_scanned_like(document: ExtractedDocument, *, min_chars: int) -> bool:
    """True when overall text is below threshold and at least one page has images."""
    total = count_meaningful_chars(document.full_text)
    has_images = any(page.has_images for page in document.pages)
    return total < min_chars and has_images


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
