"""Render PDF pages to images for OCR at a controlled DPI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.processing.ocr.models import RenderTransform
from app.processing.ocr.workfiles import allocate_ocr_path, safe_unlink_ocr

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RenderedPage:
    page_number: int
    image_path: Path
    transform: RenderTransform


def build_render_transform(
    page: fitz.Page,
    *,
    page_number: int,
    dpi: int,
    pixmap: fitz.Pixmap,
) -> RenderTransform:
    rotation = int(page.rotation) % 360
    scale = dpi / 72.0
    rect = page.rect
    return RenderTransform(
        page_number=page_number,
        dpi=dpi,
        page_width=float(rect.width),
        page_height=float(rect.height),
        pixel_width=int(pixmap.width),
        pixel_height=int(pixmap.height),
        rotation=rotation,
        scale_x=scale,
        scale_y=scale,
    )


def render_pdf_page(
    document_path: Path,
    page_number: int,
    *,
    dpi: int | None = None,
    job_id: str | None = None,
    root: Path | None = None,
) -> RenderedPage:
    """Render a single 1-based page to a temporary PNG. Caller must delete image_path."""
    dpi = dpi if dpi is not None else settings.ocr_render_dpi
    if dpi < 72 or dpi > 300:
        raise AppError(
            code="PDF_RENDER_FAILED",
            message="PDF page rendering failed.",
            status_code=500,
        )

    document = fitz.open(document_path)
    try:
        if page_number < 1 or page_number > document.page_count:
            raise AppError(
                code="PDF_RENDER_FAILED",
                message="PDF page rendering failed.",
                status_code=500,
            )
        page = document.load_page(page_number - 1)
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        try:
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        except Exception as exc:
            raise AppError(
                code="PDF_RENDER_FAILED",
                message="PDF page rendering failed.",
                status_code=500,
            ) from exc

        transform = build_render_transform(page, page_number=page_number, dpi=dpi, pixmap=pixmap)
        image_path = allocate_ocr_path(".png", root=root, job_id=job_id)
        try:
            pixmap.save(str(image_path))
        except Exception as exc:
            safe_unlink_ocr(image_path, root=root)
            raise AppError(
                code="PDF_RENDER_FAILED",
                message="PDF page rendering failed.",
                status_code=500,
            ) from exc

        logger.info(
            "pdf_page_rendered",
            page_number=page_number,
            dpi=dpi,
            pixel_width=transform.pixel_width,
            pixel_height=transform.pixel_height,
            rotation=transform.rotation,
        )
        return RenderedPage(
            page_number=page_number,
            image_path=image_path,
            transform=transform,
        )
    finally:
        document.close()
