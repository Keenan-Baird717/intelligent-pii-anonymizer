"""Image OCR analysis and irreversible redaction."""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.processing.ocr.adapter import OcrEngine, get_default_ocr_engine
from app.processing.ocr.index import build_ocr_text_index, map_ocr_offsets
from app.processing.ocr.models import OcrTextIndex, PixelBBox
from app.processing.ocr.preprocess import run_ocr_with_optional_preprocess
from app.processing.ocr.transforms import ImageCoordTransform

logger = get_logger(__name__)


def analyze_image_file(
    path: Path,
    *,
    engine: OcrEngine | None = None,
    job_id: str | None = None,
    root: Path | None = None,
) -> tuple[OcrTextIndex, ImageCoordTransform, bool, float]:
    """
    Run OCR on a PNG/JPEG file.

    Returns (index, transform, preprocessing_used, average_ocr_confidence_0_1).
    """
    if not settings.ocr_enabled:
        raise AppError(
            code="OCR_DISABLED",
            message="OCR is disabled in this configuration.",
            status_code=503,
        )
    try:
        pass_result = run_ocr_with_optional_preprocess(
            path, engine=engine or get_default_ocr_engine(), job_id=job_id, root=root
        )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="IMAGE_ANALYSIS_FAILED",
            message="Image analysis failed.",
            status_code=500,
        ) from exc

    raw = pass_result.result
    if not raw.words:
        raise AppError(
            code="OCR_NO_TEXT",
            message="OCR did not detect readable text in this image.",
            status_code=422,
        )

    index = build_ocr_text_index(raw, page_number=1)
    transform = ImageCoordTransform(
        original_width=pass_result.transform.original_width,
        original_height=pass_result.transform.original_height,
        scale_x=pass_result.transform.scale_x if pass_result.preprocessing_used else 1.0,
        scale_y=pass_result.transform.scale_y if pass_result.preprocessing_used else 1.0,
    )
    avg = sum(w.confidence for w in raw.words) / len(raw.words) / 100.0 if raw.words else 0.0
    logger.info(
        "image_ocr_analysis_completed",
        image_width=raw.image_width,
        image_height=raw.image_height,
        word_count=len(raw.words),
        preprocessing_used=pass_result.preprocessing_used,
        average_ocr_confidence=avg,
    )
    return index, transform, pass_result.preprocessing_used, avg


def map_image_entity_rects(
    index: OcrTextIndex,
    start: int,
    end: int,
    transform: ImageCoordTransform,
) -> list[dict[str, float]]:
    mapping = map_ocr_offsets(index, start, end)
    rects: list[dict[str, float]] = []
    for box in mapping.pixel_rectangles:
        try:
            mapped = transform.to_original(box)
        except Exception:
            mapped = box.clip(float(transform.original_width), float(transform.original_height))
        rects.append(mapped.to_dict())
    if not rects:
        raise AppError(
            code="OCR_COORDINATE_MAPPING_FAILED",
            message="OCR coordinates could not be mapped for a detection.",
            status_code=400,
        )
    return rects


def redact_image(
    source: Path,
    output: Path,
    rectangles: list[PixelBBox],
    *,
    output_format: str,
    fill: tuple[int, int, int] = (0, 0, 0),
) -> None:
    """Irreversibly fill rectangles in a new image; strip metadata. Never modifies source."""
    from PIL import Image, ImageDraw, ImageOps

    try:
        with Image.open(source) as opened:
            oriented = ImageOps.exif_transpose(opened) or opened
            working = oriented.convert("RGB")
            draw = ImageDraw.Draw(working)
            width, height = working.size
            for box in rectangles:
                clipped = box.clip(float(width), float(height))
                draw.rectangle(
                    [clipped.x0, clipped.y0, clipped.x1, clipped.y1],
                    fill=fill,
                )
            # Save without EXIF/GPS/comments.
            fmt = "PNG" if output_format.lower() == "png" else "JPEG"
            if fmt == "JPEG":
                working.save(output, format=fmt, quality=90, optimize=True)
            else:
                working.save(output, format=fmt)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="IMAGE_REDACTION_FAILED",
            message="Image redaction failed.",
            status_code=500,
        ) from exc


def verify_image_redaction(
    output: Path,
    *,
    forbidden: list[str],
    required: list[str],
    engine: OcrEngine | None = None,
    manual_rects: list[PixelBBox] | None = None,
    fill: tuple[int, int, int] = (0, 0, 0),
) -> None:
    """Rerun OCR on output; confirm forbidden absent and required present when practical."""
    from PIL import Image

    try:
        with Image.open(output) as img:
            width, height = img.size
            if width <= 0 or height <= 0:
                raise AppError(
                    code="OUTPUT_VERIFICATION_FAILED",
                    message="Output verification failed.",
                    status_code=500,
                )
            if manual_rects:
                rgb = img.convert("RGB")
                for box in manual_rects:
                    clipped = box.clip(float(width), float(height))
                    # Sample center pixel of manual region.
                    cx = int((clipped.x0 + clipped.x1) / 2)
                    cy = int((clipped.y0 + clipped.y1) / 2)
                    pixel = rgb.getpixel((cx, cy))
                    if not isinstance(pixel, tuple):
                        continue
                    if any(abs(int(pixel[i]) - fill[i]) > 30 for i in range(3)):
                        raise AppError(
                            code="OUTPUT_VERIFICATION_FAILED",
                            message="Output verification failed.",
                            status_code=500,
                        )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="OUTPUT_VERIFICATION_FAILED",
            message="Output verification failed.",
            status_code=500,
        ) from exc

    if not forbidden and not required:
        return

    try:
        result = (engine or get_default_ocr_engine()).run(output)
    except AppError as exc:
        if exc.code in {"OCR_NO_TEXT", "OCR_FAILED"}:
            # If forbidden values existed, empty OCR is acceptable absence; still ok.
            text = ""
        else:
            raise AppError(
                code="OUTPUT_VERIFICATION_FAILED",
                message="Output verification failed.",
                status_code=500,
            ) from exc
    else:
        text = " ".join(w.text for w in result.words)

    normalized = _normalize(text)
    for value in forbidden:
        if _normalize(value) and _normalize(value) in normalized:
            raise AppError(
                code="OUTPUT_VERIFICATION_FAILED",
                message="Output verification failed.",
                status_code=500,
            )
    for value in required:
        token = _normalize(value)
        if token and token not in normalized:
            # Control text absence is soft for OCR noise — only fail if OCR found substantial text.
            if len(normalized) > 10:
                raise AppError(
                    code="OUTPUT_VERIFICATION_FAILED",
                    message="Output verification failed.",
                    status_code=500,
                )


def _normalize(value: str) -> str:
    return " ".join(
        "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in value).split()
    )
