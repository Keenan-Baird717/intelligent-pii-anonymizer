from __future__ import annotations

from dataclasses import dataclass, field

from app.processing.pdf.constants import PAGE_SEPARATOR


@dataclass(slots=True, frozen=True)
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("Invalid bounding box: max must be >= min")

    def clip(self, width: float, height: float) -> BBox:
        x0 = max(0.0, min(self.x0, width))
        y0 = max(0.0, min(self.y0, height))
        x1 = max(0.0, min(self.x1, width))
        y1 = max(0.0, min(self.y1, height))
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        return BBox(x0=x0, y0=y0, x1=x1, y1=y1)

    def padded(self, padding: float, width: float, height: float) -> BBox:
        return BBox(
            x0=self.x0 - padding,
            y0=self.y0 - padding,
            x1=self.x1 + padding,
            y1=self.y1 + padding,
        ).clip(width, height)

    def overlaps_or_adjacent(self, other: BBox, *, gap: float = 2.0) -> bool:
        if self.y1 < other.y0 - gap or other.y1 < self.y0 - gap:
            return False
        if self.x1 < other.x0 - gap or other.x1 < self.x0 - gap:
            return False
        return True

    def merge(self, other: BBox) -> BBox:
        return BBox(
            x0=min(self.x0, other.x0),
            y0=min(self.y0, other.y0),
            x1=max(self.x1, other.x1),
            y1=max(self.y1, other.y1),
        )

    def to_dict(self) -> dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> BBox:
        return cls(
            x0=float(data["x0"]),
            y0=float(data["y0"]),
            x1=float(data["x1"]),
            y1=float(data["y1"]),
        )


@dataclass(slots=True, frozen=True)
class PositionedSpan:
    """One extracted word (or token) with global character offsets into full_text."""

    page_number: int  # 1-based
    start: int
    end: int
    text_length: int
    bbox: BBox
    block_no: int
    line_no: int


@dataclass(slots=True)
class ExtractedPage:
    page_number: int  # 1-based
    width: float
    height: float
    text: str
    spans: list[PositionedSpan] = field(default_factory=list)
    has_text: bool = False
    has_images: bool = False


@dataclass(slots=True)
class ExtractedDocument:
    pages: list[ExtractedPage]
    full_text: str
    page_separator: str = PAGE_SEPARATOR
    pages_with_text: list[int] = field(default_factory=list)
    pages_needing_ocr: list[int] = field(default_factory=list)

    @property
    def is_partial_text(self) -> bool:
        return bool(self.pages_needing_ocr) and bool(self.pages_with_text)


@dataclass(slots=True, frozen=True)
class MappedRectangle:
    page_number: int  # 1-based
    bbox: BBox


@dataclass(slots=True, frozen=True)
class DocumentEntityMapping:
    start: int
    end: int
    page_number: int  # 1-based primary page
    rectangles: list[MappedRectangle]
