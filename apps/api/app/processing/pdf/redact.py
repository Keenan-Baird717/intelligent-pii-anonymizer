"""PDF redaction with irreversible scanned-page pixel replacement.

Embedded-text pages use PyMuPDF true text redaction (Phase 5).
Scanned / OCR / mixed image pages use rasterize → paint → rebuild so the
original page image objects and hidden text layers are not retained.
"""

from __future__ import annotations

import math
import os
from collections import defaultdict
from pathlib import Path

import fitz

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.processing.pdf.types import BBox

logger = get_logger(__name__)

_FILL_RGB = (0, 0, 0)


def apply_redactions(
    source_path: Path,
    output_path: Path,
    rectangles: list[tuple[int, BBox]],
    *,
    pixel_redact_pages: set[int] | None = None,
    dpi: int | None = None,
) -> None:
    """Apply redactions and write a new PDF. Never modifies ``source_path``.

    ``rectangles`` use 1-based page numbers in PDF user-space points.
    Pages listed in ``pixel_redact_pages`` are rasterized, painted, and rebuilt
    without retaining the original page content stream or embedded images.
    Other pages with rectangles use PyMuPDF text redaction.
    """
    if output_path.resolve() == source_path.resolve():
        raise AppError(
            code="REDACTION_FAILED",
            message="Redaction could not be applied.",
            status_code=500,
        )

    pixel_pages = set(pixel_redact_pages or ())
    dpi = dpi if dpi is not None else settings.ocr_render_dpi
    if dpi < 72 or dpi > 300:
        raise AppError(
            code="REDACTION_FAILED",
            message="Redaction could not be applied.",
            status_code=500,
        )

    by_page: dict[int, list[BBox]] = defaultdict(list)
    for page_number, bbox in rectangles:
        by_page[page_number].append(bbox)

    temp_out = output_path.with_suffix(".writing.pdf")
    if temp_out.exists():
        temp_out.unlink(missing_ok=True)
    if output_path.exists():
        output_path.unlink(missing_ok=True)

    source = fitz.open(source_path)
    output = fitz.open()
    try:
        for page_index in range(source.page_count):
            page_number = page_index + 1
            page = source.load_page(page_index)
            page_rects = by_page.get(page_number, [])

            if page_number in pixel_pages and page_rects:
                _append_raster_redacted_page(
                    output,
                    page,
                    page_number=page_number,
                    rectangles=page_rects,
                    dpi=dpi,
                )
            elif page_rects:
                _append_text_redacted_page(output, source, page_index, page_rects)
            else:
                output.insert_pdf(source, from_page=page_index, to_page=page_index)

        from app.services.ingestion.pdf_validation import sanitize_pdf_document

        sanitize_pdf_document(output)
        output.save(temp_out, garbage=4, deflate=True, incremental=False)
        logger.info(
            "pdf_redaction_applied",
            page_count=source.page_count,
            rectangle_count=len(rectangles),
            pixel_page_count=len(pixel_pages),
            status="success",
        )
    except AppError:
        output.close()
        source.close()
        if temp_out.exists():
            temp_out.unlink(missing_ok=True)
        if output_path.exists():
            output_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        output.close()
        source.close()
        if temp_out.exists():
            temp_out.unlink(missing_ok=True)
        if output_path.exists():
            output_path.unlink(missing_ok=True)
        logger.error("redaction_apply_failure", error_code="REDACTION_FAILED")
        raise AppError(
            code="REDACTION_FAILED",
            message="Redaction could not be applied.",
            status_code=500,
        ) from exc
    finally:
        if not output.is_closed:
            output.close()
        if not source.is_closed:
            source.close()

    try:
        os.replace(temp_out, output_path)
    except OSError as exc:
        if temp_out.exists():
            temp_out.unlink(missing_ok=True)
        if output_path.exists():
            output_path.unlink(missing_ok=True)
        raise AppError(
            code="REDACTION_FAILED",
            message="Redaction could not be applied.",
            status_code=500,
        ) from exc


def _append_text_redacted_page(
    output: fitz.Document,
    source: fitz.Document,
    page_index: int,
    rectangles: list[BBox],
) -> None:
    """Copy one page and apply PyMuPDF true text redaction."""
    start = output.page_count
    output.insert_pdf(source, from_page=page_index, to_page=page_index)
    page = output.load_page(start)
    for bbox in rectangles:
        clipped = _clip_to_page(page, bbox)
        if clipped is None:
            continue
        page.add_redact_annot(
            fitz.Rect(clipped.x0, clipped.y0, clipped.x1, clipped.y1),
            fill=_FILL_RGB,
        )
    page.apply_redactions()


def _append_raster_redacted_page(
    output: fitz.Document,
    page: fitz.Page,
    *,
    page_number: int,
    rectangles: list[BBox],
    dpi: int,
) -> None:
    """Rasterize, paint opaque fills, rebuild page without original content."""
    from PIL import Image, ImageDraw

    rotation = int(page.rotation) % 360
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    try:
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    except Exception as exc:
        raise AppError(
            code="REDACTION_FAILED",
            message="Redaction could not be applied.",
            status_code=500,
        ) from exc

    # Map page annotation/user-space rectangles into pixmap pixels. Empirically,
    # ``rotation_matrix * zoom`` matches get_pixmap placement for 0/90/180/270.
    page_to_pix = page.rotation_matrix * matrix

    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = None
    try:
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        draw = ImageDraw.Draw(image)
        for bbox in rectangles:
            clipped = _clip_to_page_mediabox(page, bbox)
            if clipped is None:
                continue
            mapped = (
                fitz.Rect(clipped.x0, clipped.y0, clipped.x1, clipped.y1) * page_to_pix
            ).normalize()
            x0 = max(0, min(int(mapped.x0), pixmap.width - 1))
            y0 = max(0, min(int(mapped.y0), pixmap.height - 1))
            x1 = max(0, min(int(math.ceil(mapped.x1)), pixmap.width))
            y1 = max(0, min(int(math.ceil(mapped.y1)), pixmap.height))
            if x1 <= x0 or y1 <= y0:
                continue
            draw.rectangle([x0, y0, x1, y1], fill=_FILL_RGB)
        from io import BytesIO

        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        png_bytes = buffer.getvalue()
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit

    # Replacement page matches the visual page.rect. The raster already includes
    # rotation, so the rebuilt page is normalized to rotation 0 while preserving
    # displayed width/height. Original content streams / images are not copied.
    new_page = output.new_page(width=float(page.rect.width), height=float(page.rect.height))
    new_page.insert_image(new_page.rect, stream=png_bytes)

    logger.info(
        "pdf_page_raster_redacted",
        page_number=page_number,
        dpi=dpi,
        rectangle_count=len(rectangles),
        pixel_width=pixmap.width,
        pixel_height=pixmap.height,
        source_rotation=rotation,
        output_rotation=0,
    )


def _clip_to_page_mediabox(page: fitz.Page, bbox: BBox) -> BBox | None:
    """Clip to the unrotated mediabox (annotation coordinate space)."""
    rect = page.mediabox
    x0 = max(float(rect.x0), min(bbox.x0, float(rect.x1)))
    x1 = max(float(rect.x0), min(bbox.x1, float(rect.x1)))
    y0 = max(float(rect.y0), min(bbox.y0, float(rect.y1)))
    y1 = max(float(rect.y0), min(bbox.y1, float(rect.y1)))
    if x1 <= x0 or y1 <= y0:
        return None
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _clip_to_page(page: fitz.Page, bbox: BBox) -> BBox | None:
    rect = page.rect
    x0 = max(float(rect.x0), min(bbox.x0, float(rect.x1)))
    x1 = max(float(rect.x0), min(bbox.x1, float(rect.x1)))
    y0 = max(float(rect.y0), min(bbox.y0, float(rect.y1)))
    y1 = max(float(rect.y0), min(bbox.y1, float(rect.y1)))
    if x1 <= x0 or y1 <= y0:
        return None
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


def map_page_rects_to_pixels(
    page: fitz.Page,
    rectangles: list[BBox],
    *,
    dpi: int,
) -> list[tuple[int, int, int, int]]:
    """Map PDF annotation-space rectangles to pixmap pixel boxes for ``page``."""
    zoom = dpi / 72.0
    page_to_pix = page.rotation_matrix * fitz.Matrix(zoom, zoom)
    # Need pixmap size for clipping.
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    results: list[tuple[int, int, int, int]] = []
    for bbox in rectangles:
        clipped = _clip_to_page_mediabox(page, bbox)
        if clipped is None:
            continue
        mapped = (
            fitz.Rect(clipped.x0, clipped.y0, clipped.x1, clipped.y1) * page_to_pix
        ).normalize()
        x0 = max(0, min(int(mapped.x0), pixmap.width - 1))
        y0 = max(0, min(int(mapped.y0), pixmap.height - 1))
        x1 = max(0, min(int(math.ceil(mapped.x1)), pixmap.width))
        y1 = max(0, min(int(math.ceil(mapped.y1)), pixmap.height))
        if x1 > x0 and y1 > y0:
            results.append((x0, y0, x1, y1))
    return results


def page_has_recoverable_source_image(path: Path, page_number: int) -> bool:
    """Return True if the page embeds more than a single full-page replacement image.

    Used by permanence tests. A raster-rebuilt page should contain exactly one
    image XObject (the redacted raster) and no recoverable pre-redaction scan.
    """
    document = fitz.open(path)
    try:
        if page_number < 1 or page_number > document.page_count:
            return False
        page = document.load_page(page_number - 1)
        images = page.get_images(full=True)
        # More than one embedded image suggests original content may remain.
        return len(images) > 1
    finally:
        document.close()


def page_annotation_count(path: Path, page_number: int) -> int:
    document = fitz.open(path)
    try:
        if page_number < 1 or page_number > document.page_count:
            return 0
        annots = document.load_page(page_number - 1).annots()
        if annots is None:
            return 0
        return sum(1 for _ in annots)
    finally:
        document.close()


def extract_page_image_bytes(path: Path, page_number: int) -> list[bytes]:
    """Extract raw embedded image bytes from a page (for permanence assertions)."""
    document = fitz.open(path)
    try:
        if page_number < 1 or page_number > document.page_count:
            return []
        page = document.load_page(page_number - 1)
        results: list[bytes] = []
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                extracted = document.extract_image(xref)
            except Exception:
                continue
            data = extracted.get("image")
            if isinstance(data, bytes | bytearray):
                results.append(bytes(data))
        return results
    finally:
        document.close()
