"""Deterministic PDF page ↔ rendered-pixel transforms for OCR mapping."""

from __future__ import annotations

from dataclasses import dataclass

import fitz

from app.core.errors import AppError
from app.processing.ocr.models import PixelBBox, RenderTransform


def pixel_to_pdf_bbox(
    transform: RenderTransform,
    box: PixelBBox,
) -> tuple[float, float, float, float]:
    """
    Convert a top-left pixel bbox from a DPI render into PDF annotation space.

    Uses the same ``rotation_matrix * zoom`` convention as ``page.get_pixmap`` so
    OCR boxes align with ``add_redact_annot`` / draw coordinates for rotations
    0/90/180/270.
    """
    try:
        x0, y0, x1, y1 = _map_pixel_box_to_pdf(transform, box)
    except ValueError as exc:
        raise AppError(
            code="INVALID_OCR_COORDINATES",
            message="OCR coordinates are invalid.",
            status_code=400,
        ) from exc
    return _clip_pdf_bbox(transform, x0, y0, x1, y1)


def pdf_to_pixel_bbox(
    transform: RenderTransform,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> PixelBBox:
    """Inverse of ``pixel_to_pdf_bbox``."""
    try:
        px0, py0, px1, py1 = _map_pdf_box_to_pixel(transform, x0, y0, x1, y1)
    except ValueError as exc:
        raise AppError(
            code="INVALID_OCR_COORDINATES",
            message="OCR coordinates are invalid.",
            status_code=400,
        ) from exc
    for value in (px0, py0, px1, py1):
        if value != value or value in (float("inf"), float("-inf")):
            raise AppError(
                code="INVALID_OCR_COORDINATES",
                message="OCR coordinates are invalid.",
                status_code=400,
            )
    try:
        return PixelBBox(px0, py0, px1, py1).clip(
            float(transform.pixel_width), float(transform.pixel_height)
        )
    except ValueError as exc:
        raise AppError(
            code="INVALID_OCR_COORDINATES",
            message="OCR coordinates are invalid.",
            status_code=400,
        ) from exc


def _rotation_matrix(transform: RenderTransform) -> fitz.Matrix:
    """Build the PyMuPDF rotation matrix for the page mediabox dimensions.

    ``RenderTransform.page_width/height`` are visual ``page.rect`` sizes. For
    90/270 the mediabox is swapped relative to the visual rect.
    """
    rot = transform.rotation % 360
    # Mediabox dimensions (unrotated).
    if rot in (90, 270):
        mb_w, mb_h = transform.page_height, transform.page_width
    else:
        mb_w, mb_h = transform.page_width, transform.page_height

    if rot == 0:
        return fitz.Matrix(1, 0, 0, 1, 0, 0)
    if rot == 90:
        return fitz.Matrix(0, 1, -1, 0, mb_h, 0)
    if rot == 180:
        return fitz.Matrix(-1, 0, 0, -1, mb_w, mb_h)
    if rot == 270:
        return fitz.Matrix(0, -1, 1, 0, 0, mb_w)
    raise ValueError("Unsupported page rotation")


def _page_to_pix_matrix(transform: RenderTransform) -> fitz.Matrix:
    zoom = transform.dpi / 72.0
    return _rotation_matrix(transform) * fitz.Matrix(zoom, zoom)


def _map_pixel_box_to_pdf(
    transform: RenderTransform,
    box: PixelBBox,
) -> tuple[float, float, float, float]:
    mat = _page_to_pix_matrix(transform)
    inv = ~mat
    mapped = (fitz.Rect(box.x0, box.y0, box.x1, box.y1) * inv).normalize()
    return mapped.x0, mapped.y0, mapped.x1, mapped.y1


def _map_pdf_box_to_pixel(
    transform: RenderTransform,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> tuple[float, float, float, float]:
    mat = _page_to_pix_matrix(transform)
    mapped = (fitz.Rect(x0, y0, x1, y1) * mat).normalize()
    return mapped.x0, mapped.y0, mapped.x1, mapped.y1


def _clip_pdf_bbox(
    transform: RenderTransform,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> tuple[float, float, float, float]:
    for value in (x0, y0, x1, y1):
        if value != value or value in (float("inf"), float("-inf")):
            raise AppError(
                code="INVALID_OCR_COORDINATES",
                message="OCR coordinates are invalid.",
                status_code=400,
            )

    rot = transform.rotation % 360
    if rot in (90, 270):
        max_x, max_y = transform.page_height, transform.page_width
    else:
        max_x, max_y = transform.page_width, transform.page_height

    x0 = max(0.0, min(x0, max_x))
    x1 = max(0.0, min(x1, max_x))
    y0 = max(0.0, min(y0, max_y))
    y1 = max(0.0, min(y1, max_y))
    if x1 <= x0 or y1 <= y0:
        raise AppError(
            code="INVALID_OCR_COORDINATES",
            message="OCR coordinates are invalid.",
            status_code=400,
        )
    return x0, y0, x1, y1


@dataclass(frozen=True, slots=True)
class ImageCoordTransform:
    """Map OCR boxes from a possibly preprocessed image back to original pixels."""

    original_width: int
    original_height: int
    scale_x: float = 1.0
    scale_y: float = 1.0

    def to_original(self, box: PixelBBox) -> PixelBBox:
        sx = self.scale_x if self.scale_x else 1.0
        sy = self.scale_y if self.scale_y else 1.0
        mapped = PixelBBox(
            x0=box.x0 / sx,
            y0=box.y0 / sy,
            x1=box.x1 / sx,
            y1=box.y1 / sy,
        )
        return mapped.clip(float(self.original_width), float(self.original_height))
