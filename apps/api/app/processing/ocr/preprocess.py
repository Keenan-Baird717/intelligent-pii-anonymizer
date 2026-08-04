"""Conservative image preprocessing for OCR. Never modifies the original upload."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.processing.ocr.adapter import OcrEngine, RawOcrResult, get_default_ocr_engine
from app.processing.ocr.workfiles import safe_unlink_ocr, temporary_ocr_file

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PreprocessTransform:
    """Inverse transform metadata to map OCR boxes back to original image pixels."""

    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation_degrees: float = 0.0
    deskew_degrees: float = 0.0
    original_width: int = 0
    original_height: int = 0
    processed_width: int = 0
    processed_height: int = 0

    def map_box_to_original(
        self, x0: float, y0: float, x1: float, y1: float
    ) -> tuple[float, float, float, float]:
        """Map processed-image pixel box back to original coordinates."""
        # Undo scale first.
        sx = self.scale_x if self.scale_x else 1.0
        sy = self.scale_y if self.scale_y else 1.0
        ox0, oy0, ox1, oy1 = x0 / sx, y0 / sy, x1 / sx, y1 / sy
        # Deskew/rotation for MVP preprocessing is mild; when non-zero, approximate inverse
        # by treating deskew as identity if absolute angle < 0.5 degrees.
        if abs(self.deskew_degrees) >= 0.5 or abs(self.rotation_degrees) >= 0.5:
            # Without a full affine inverse stored, reject unsafe mapping.
            raise AppError(
                code="OCR_COORDINATE_MAPPING_FAILED",
                message="OCR coordinates could not be mapped for a detection.",
                status_code=400,
            )
        w = float(self.original_width)
        h = float(self.original_height)
        return (
            max(0.0, min(ox0, w)),
            max(0.0, min(oy0, h)),
            max(0.0, min(ox1, w)),
            max(0.0, min(oy1, h)),
        )


@dataclass(frozen=True, slots=True)
class OcrPassResult:
    result: RawOcrResult
    preprocessing_used: bool
    transform: PreprocessTransform
    score: float


def _quality_score(result: RawOcrResult) -> tuple[float, float, int, float]:
    words = result.words
    if not words:
        return 0.0, 0.0, 0, 0.0
    avg_conf = sum(w.confidence for w in words) / len(words)
    meaningful = sum(1 for w in words if any(ch.isalnum() for ch in w.text))
    total_chars = sum(len(w.text) for w in words) or 1
    printable = sum(sum(1 for ch in w.text if ch.isprintable()) for w in words) / total_chars
    # Deterministic composite score.
    score = (avg_conf / 100.0) * 0.5 + min(meaningful / 50.0, 1.0) * 0.3 + printable * 0.2
    return score, avg_conf, meaningful, printable


def _write_processed_variant(
    source: Path,
    dest: Path,
    *,
    deskew: bool,
) -> PreprocessTransform:
    """Apply grayscale + Otsu threshold (+ optional mild deskew). Uses opencv-headless."""
    import cv2
    import numpy as np
    from PIL import Image

    with Image.open(source) as img:
        img = img.convert("RGB")
        original_width, original_height = img.size
        rgb = np.array(img)

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    # Mild denoise
    gray = cv2.medianBlur(gray, 3)
    # Otsu threshold
    _thresh_val, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    deskew_degrees = 0.0
    if deskew and settings.ocr_deskew_enabled:
        coords = np.column_stack(np.where(binary < 128))
        if coords.size > 0:
            rect = cv2.minAreaRect(coords)
            angle = rect[-1]
            if angle < -45:
                angle = 90 + angle
            if abs(angle) <= 15:
                deskew_degrees = float(angle)
                (h, w) = binary.shape[:2]
                matrix = cv2.getRotationMatrix2D((w / 2, h / 2), deskew_degrees, 1.0)
                binary = cv2.warpAffine(
                    binary,
                    matrix,
                    (w, h),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_REPLICATE,
                )

    # Limited upscale for very small images
    scale = 1.0
    h, w = binary.shape[:2]
    if min(h, w) < 800:
        scale = min(2.0, 800.0 / float(min(h, w)))
        binary = cv2.resize(binary, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    if not cv2.imwrite(str(dest), binary):
        raise AppError(
            code="PREPROCESSING_FAILED",
            message="Image preprocessing failed.",
            status_code=500,
        )

    return PreprocessTransform(
        scale_x=scale,
        scale_y=scale,
        rotation_degrees=0.0,
        deskew_degrees=deskew_degrees if abs(deskew_degrees) < 0.5 else 0.0,
        # When deskew applied beyond tolerance we zero it in transform to force safe path;
        # for mild deskew (<0.5) treat as identity for coordinate mapping.
        original_width=original_width,
        original_height=original_height,
        processed_width=int(binary.shape[1]),
        processed_height=int(binary.shape[0]),
    )


def run_ocr_with_optional_preprocess(
    image_path: Path,
    *,
    engine: OcrEngine | None = None,
    job_id: str | None = None,
    root: Path | None = None,
) -> OcrPassResult:
    """
    Run baseline OCR, optionally compare one processed pass, pick the better result.

    Maximum two OCR passes. Temporary processed images are always deleted.
    """
    engine = engine or get_default_ocr_engine()
    from PIL import Image

    with Image.open(image_path) as img:
        original_width, original_height = img.size

    identity = PreprocessTransform(
        original_width=original_width,
        original_height=original_height,
        processed_width=original_width,
        processed_height=original_height,
    )

    try:
        baseline = engine.run(image_path)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="OCR_FAILED",
            message="OCR could not process the image.",
            status_code=500,
        ) from exc

    base_score, *_ = _quality_score(baseline)
    best = OcrPassResult(
        result=baseline,
        preprocessing_used=False,
        transform=identity,
        score=base_score,
    )

    if not settings.ocr_preprocessing_enabled:
        logger.info(
            "ocr_preprocess_skipped",
            preprocessing_used=False,
            average_ocr_confidence=_quality_score(baseline)[1],
            meaningful_word_count=_quality_score(baseline)[2],
        )
        return best

    processed_path: Path | None = None
    try:
        with temporary_ocr_file(".png", root=root, job_id=job_id) as processed_path:
            try:
                transform = _write_processed_variant(
                    image_path,
                    processed_path,
                    deskew=settings.ocr_deskew_enabled,
                )
                processed = engine.run(processed_path)
                proc_score, avg_conf, meaningful, _printable = _quality_score(processed)
                if proc_score > best.score:
                    best = OcrPassResult(
                        result=processed,
                        preprocessing_used=True,
                        transform=transform,
                        score=proc_score,
                    )
                logger.info(
                    "ocr_preprocess_compared",
                    preprocessing_used=best.preprocessing_used,
                    average_ocr_confidence=avg_conf,
                    meaningful_word_count=meaningful,
                )
            except AppError as exc:
                if exc.code == "PREPROCESSING_FAILED":
                    logger.info("ocr_preprocess_skipped", preprocessing_used=False)
                else:
                    # OCR failure on processed image — keep baseline.
                    logger.info("ocr_preprocess_skipped", preprocessing_used=False)
    finally:
        safe_unlink_ocr(processed_path, root=root)

    return best
