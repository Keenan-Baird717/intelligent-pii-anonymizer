"""Alias module — dataclasses live in types.py."""

from app.processing.pdf.types import (
    BBox,
    DocumentEntityMapping,
    ExtractedDocument,
    ExtractedPage,
    MappedRectangle,
    PositionedSpan,
)

__all__ = [
    "BBox",
    "DocumentEntityMapping",
    "ExtractedDocument",
    "ExtractedPage",
    "MappedRectangle",
    "PositionedSpan",
]
