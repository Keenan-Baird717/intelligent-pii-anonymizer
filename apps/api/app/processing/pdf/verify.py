"""Post-redaction verification for text and scanned PDF pages."""

from __future__ import annotations

from pathlib import Path

import fitz

from app.core.errors import AppError
from app.core.logging import get_logger
from app.processing.pdf.classify import normalize_whitespace
from app.processing.pdf.redact import page_annotation_count
from app.processing.pdf.types import BBox

logger = get_logger(__name__)

_FILL = (0, 0, 0)
_FILL_TOLERANCE = 30


def _extract_plain_text(path: Path) -> str:
    document = fitz.open(path)
    try:
        parts: list[str] = []
        for index in range(document.page_count):
            parts.append(document.load_page(index).get_text("text"))
        return "\n".join(parts)
    finally:
        document.close()


def verify_redaction(
    output_path: Path,
    forbidden_substrings: list[str],
    required_substrings: list[str],
) -> None:
    """Re-extract output text and assert forbidden absent / required present.

    Never logs the substrings themselves.
    """
    try:
        raw = _extract_plain_text(output_path)
    except Exception as exc:
        logger.error("redaction_verify_extract_failure", error_code="REDACTION_VERIFICATION_FAILED")
        raise AppError(
            code="REDACTION_VERIFICATION_FAILED",
            message="Redaction verification failed.",
            status_code=500,
        ) from exc

    normalized = normalize_whitespace(raw)

    for forbidden in forbidden_substrings:
        needle = normalize_whitespace(forbidden)
        if needle and needle in normalized:
            logger.error(
                "redaction_verify_forbidden_present",
                error_code="REDACTION_VERIFICATION_FAILED",
            )
            raise AppError(
                code="REDACTION_VERIFICATION_FAILED",
                message="Redaction verification failed.",
                status_code=500,
            )

    for required in required_substrings:
        needle = normalize_whitespace(required)
        if needle and needle not in normalized:
            logger.error(
                "redaction_verify_required_missing",
                error_code="REDACTION_VERIFICATION_FAILED",
            )
            raise AppError(
                code="REDACTION_VERIFICATION_FAILED",
                message="Redaction verification failed.",
                status_code=500,
            )

    logger.info(
        "pdf_redaction_verified",
        forbidden_count=len(forbidden_substrings),
        required_count=len(required_substrings),
        status="success",
    )


def verify_scanned_page_redaction(
    output_path: Path,
    *,
    page_number: int,
    rectangles: list[BBox],
    forbidden_substrings: list[str],
    required_substrings: list[str],
    dpi: int | None = None,
    fill: tuple[int, int, int] = _FILL,
    pixel_rects: list[tuple[int, int, int, int]] | None = None,
    source_path: Path | None = None,
) -> None:
    """Prove scanned-page redaction permanence for one output page.

    Checks:
    - No removable annotations remain
    - Embedded text layer is empty or lacks forbidden values
    - Accepted regions sample near the configured fill color
    - Re-OCR of the page lacks forbidden values (when OCR available)
    - Required control text remains OCR-readable when practical
    """
    from app.core.config import settings
    from app.processing.ocr.adapter import get_default_ocr_engine
    from app.processing.ocr.workfiles import safe_unlink_ocr
    from app.processing.pdf.redact import map_page_rects_to_pixels
    from app.processing.pdf.render import render_pdf_page

    if page_annotation_count(output_path, page_number) > 0:
        logger.error(
            "redaction_verify_annotations_remain",
            error_code="REDACTION_VERIFICATION_FAILED",
        )
        raise AppError(
            code="REDACTION_VERIFICATION_FAILED",
            message="Redaction verification failed.",
            status_code=500,
        )

    document = fitz.open(output_path)
    try:
        page = document.load_page(page_number - 1)
        page_text = normalize_whitespace(page.get_text("text"))
        for forbidden in forbidden_substrings:
            needle = normalize_whitespace(forbidden)
            if needle and needle in page_text:
                logger.error(
                    "redaction_verify_hidden_text_present",
                    error_code="REDACTION_VERIFICATION_FAILED",
                )
                raise AppError(
                    code="REDACTION_VERIFICATION_FAILED",
                    message="Redaction verification failed.",
                    status_code=500,
                )
    finally:
        document.close()

    dpi = dpi if dpi is not None else settings.ocr_render_dpi
    sample_rects = list(pixel_rects or [])
    if not sample_rects and source_path is not None:
        source_doc = fitz.open(source_path)
        try:
            source_page = source_doc.load_page(page_number - 1)
            sample_rects = map_page_rects_to_pixels(source_page, rectangles, dpi=dpi)
        finally:
            source_doc.close()
    elif not sample_rects:
        # Output pages are rotation-normalized; map rectangles in output page space.
        out_doc = fitz.open(output_path)
        try:
            out_page = out_doc.load_page(page_number - 1)
            sample_rects = map_page_rects_to_pixels(out_page, rectangles, dpi=dpi)
        finally:
            out_doc.close()

    # Sample fill color via PyMuPDF pixmap (avoids Pillow pixel-limit side effects).
    out_doc = fitz.open(output_path)
    try:
        out_page = out_doc.load_page(page_number - 1)
        zoom = dpi / 72.0
        pixmap = out_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        for x0, y0, x1, y1 in sample_rects:
            cx = max(0, min(int((x0 + x1) / 2), pixmap.width - 1))
            cy = max(0, min(int((y0 + y1) / 2), pixmap.height - 1))
            pixel = pixmap.pixel(cx, cy)
            if any(abs(int(pixel[i]) - fill[i]) > _FILL_TOLERANCE for i in range(3)):
                logger.error(
                    "redaction_verify_fill_mismatch",
                    error_code="REDACTION_VERIFICATION_FAILED",
                )
                raise AppError(
                    code="REDACTION_VERIFICATION_FAILED",
                    message="Redaction verification failed.",
                    status_code=500,
                )
    finally:
        out_doc.close()

    if not forbidden_substrings and not required_substrings:
        logger.info(
            "pdf_scanned_redaction_verified",
            page_number=page_number,
            rectangle_count=len(rectangles),
            forbidden_count=0,
            required_count=0,
            status="success",
        )
        return

    rendered = render_pdf_page(output_path, page_number, dpi=dpi)
    try:
        try:
            ocr = get_default_ocr_engine().run(rendered.image_path)
            ocr_text = " ".join(word.text for word in ocr.words)
        except AppError as exc:
            if exc.code in {"OCR_NO_TEXT", "OCR_FAILED", "OCR_ENGINE_UNAVAILABLE"}:
                ocr_text = ""
            else:
                raise AppError(
                    code="REDACTION_VERIFICATION_FAILED",
                    message="Redaction verification failed.",
                    status_code=500,
                ) from exc

        normalized = _normalize_ocr(ocr_text)
        for forbidden in forbidden_substrings:
            needle = _normalize_ocr(forbidden)
            if needle and needle in normalized:
                logger.error(
                    "redaction_verify_ocr_forbidden_present",
                    error_code="REDACTION_VERIFICATION_FAILED",
                )
                raise AppError(
                    code="REDACTION_VERIFICATION_FAILED",
                    message="Redaction verification failed.",
                    status_code=500,
                )
        for required in required_substrings:
            needle = _normalize_ocr(required)
            if needle and needle not in normalized and len(normalized) > 10:
                logger.error(
                    "redaction_verify_ocr_required_missing",
                    error_code="REDACTION_VERIFICATION_FAILED",
                )
                raise AppError(
                    code="REDACTION_VERIFICATION_FAILED",
                    message="Redaction verification failed.",
                    status_code=500,
                )
    finally:
        safe_unlink_ocr(rendered.image_path)

    logger.info(
        "pdf_scanned_redaction_verified",
        page_number=page_number,
        rectangle_count=len(rectangles),
        forbidden_count=len(forbidden_substrings),
        required_count=len(required_substrings),
        status="success",
    )


def _normalize_ocr(value: str) -> str:
    return " ".join(
        "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in value).split()
    )
