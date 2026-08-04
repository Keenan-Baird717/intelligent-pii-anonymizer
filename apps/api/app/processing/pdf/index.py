from __future__ import annotations

from app.core.errors import AppError
from app.processing.pdf.constants import PAGE_SEPARATOR
from app.processing.pdf.types import ExtractedDocument, ExtractedPage


def page_for_offset(document: ExtractedDocument, offset: int) -> ExtractedPage:
    """Return the page whose text (excluding trailing separators) contains offset."""
    if offset < 0 or offset > len(document.full_text):
        raise AppError(
            code="ENTITY_MAPPING_FAILED",
            message="Entity offsets could not be mapped to the document.",
            status_code=400,
        )
    cursor = 0
    sep_len = len(document.page_separator)
    for index, page in enumerate(document.pages):
        page_end = cursor + len(page.text)
        if cursor <= offset < page_end or (offset == page_end and index == len(document.pages) - 1):
            return page
        if offset == page_end and index < len(document.pages) - 1:
            # Offset lands on the separator after this page — not mappable.
            raise AppError(
                code="ENTITY_MAPPING_FAILED",
                message="Entity offsets could not be mapped to the document.",
                status_code=400,
            )
        cursor = page_end
        if index < len(document.pages) - 1:
            cursor += sep_len
    raise AppError(
        code="ENTITY_MAPPING_FAILED",
        message="Entity offsets could not be mapped to the document.",
        status_code=400,
    )


def validate_offsets(document: ExtractedDocument, start: int, end: int) -> None:
    if start < 0 or end < start or end > len(document.full_text):
        raise AppError(
            code="ENTITY_MAPPING_FAILED",
            message="Entity offsets could not be mapped to the document.",
            status_code=400,
        )
    # Entity must not consist solely of page-separator characters.
    slice_text = document.full_text[start:end]
    if slice_text and set(slice_text) <= set(PAGE_SEPARATOR):
        raise AppError(
            code="ENTITY_MAPPING_FAILED",
            message="Entity offsets could not be mapped to the document.",
            status_code=400,
        )
