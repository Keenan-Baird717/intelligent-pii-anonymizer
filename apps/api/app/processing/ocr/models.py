"""OCR result models. Never persist raw OCR text to PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class PixelBBox:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        for value in (self.x0, self.y0, self.x1, self.y1):
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError("Invalid OCR bounding box coordinate")
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("OCR bounding box must have positive area")

    def clip(self, width: float, height: float) -> PixelBBox:
        x0 = max(0.0, min(self.x0, width))
        y0 = max(0.0, min(self.y0, height))
        x1 = max(0.0, min(self.x1, width))
        y1 = max(0.0, min(self.y1, height))
        if x1 <= x0 or y1 <= y0:
            raise ValueError("Clipped OCR bounding box has zero area")
        return PixelBBox(x0=x0, y0=y0, x1=x1, y1=y1)

    def to_dict(self) -> dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}


@dataclass(slots=True, frozen=True)
class RenderTransform:
    """Deterministic page-render transform for pixel ↔ PDF coordinate mapping."""

    page_number: int  # 1-based
    dpi: int
    page_width: float
    page_height: float
    pixel_width: int
    pixel_height: int
    rotation: int  # 0, 90, 180, 270
    scale_x: float
    scale_y: float

    def pixel_to_pdf(self, box: PixelBBox) -> tuple[float, float, float, float]:
        from app.processing.ocr.transforms import pixel_to_pdf_bbox

        return pixel_to_pdf_bbox(self, box)


@dataclass(slots=True, frozen=True)
class OcrWord:
    page_number: int  # 1-based; 1 for single images
    text: str
    start: int
    end: int
    pixel_bbox: PixelBBox
    confidence: float  # 0-100
    line_no: int
    block_no: int
    reading_order: int
    pdf_bbox: tuple[float, float, float, float] | None = None
    rotation: int = 0
    drawable: bool = True


@dataclass(slots=True, frozen=True)
class OcrLine:
    page_number: int
    line_no: int
    block_no: int
    words: tuple[OcrWord, ...]


@dataclass(slots=True)
class OcrPage:
    page_number: int
    width_px: int
    height_px: int
    words: list[OcrWord] = field(default_factory=list)
    average_confidence: float = 0.0
    preprocessing_used: bool = False
    render_transform: RenderTransform | None = None
    failed: bool = False
    failure_code: str | None = None


@dataclass(slots=True)
class OcrQualitySummary:
    average_confidence: float
    meaningful_word_count: int
    printable_ratio: float
    low_confidence_word_count: int
    preprocessing_used: bool


@dataclass(slots=True)
class OcrDocument:
    pages: list[OcrPage]
    full_text: str
    words: list[OcrWord]
    quality: OcrQualitySummary
    page_separator: str
    source_kind: str = "ocr"


@dataclass(slots=True, frozen=True)
class OcrTextIndex:
    """Indexed OCR text with word offset ranges. Separators are non-drawable."""

    full_text: str
    words: tuple[OcrWord, ...]
    separator_ranges: tuple[tuple[int, int], ...]


@dataclass(slots=True, frozen=True)
class OcrCoordinateMapping:
    start: int
    end: int
    page_number: int
    pixel_rectangles: tuple[PixelBBox, ...]
    pdf_rectangles: tuple[tuple[float, float, float, float], ...]
    ocr_confidence: float
    low_ocr_confidence: bool
