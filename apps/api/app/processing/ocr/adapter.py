"""Injectable Tesseract OCR adapter.

The engine is invoked as a subprocess with an explicit argv list (never
``shell=True``) and a hard timeout that kills the process on expiry. Every failure
mode is converted to a safe ``AppError`` code. OCR text, the raw TSV, work-file
paths, and image bytes are never logged.

The public surface is intentionally small and mockable: implementations of the
:class:`OcrEngine` protocol expose a single ``run(image_path) -> RawOcrResult``
method, so unit tests can inject a fake engine without a real Tesseract binary.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.processing.ocr.models import PixelBBox

logger = get_logger(__name__)

_SUPPORTED_LANGUAGES = frozenset({"eng"})
# Tesseract TSV columns: level page block par line word left top width height conf text
_TSV_MIN_COLUMNS = 12
_WORD_LEVEL = 5
_PAGE_LEVEL = 1


@dataclass(slots=True, frozen=True)
class RawOcrWord:
    """One raw word row from the OCR engine, in rendered-pixel coordinates."""

    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float  # 0-100
    block_no: int
    line_no: int
    word_no: int


@dataclass(slots=True, frozen=True)
class RawOcrResult:
    """Raw per-image OCR output. ``words`` is unordered; the index sorts it."""

    words: list[RawOcrWord] = field(default_factory=list)
    image_width: int = 0
    image_height: int = 0


def raw_word_pixel_bbox(word: RawOcrWord) -> PixelBBox:
    """Build a positive-area pixel bbox from a raw word's left/top/width/height."""
    return PixelBBox(
        x0=float(word.left),
        y0=float(word.top),
        x1=float(word.left + word.width),
        y1=float(word.top + word.height),
    )


class OcrEngine(Protocol):
    """Mockable OCR engine interface. Implementations must never log content."""

    def run(self, image_path: Path) -> RawOcrResult: ...


def _validate_language(language: str) -> str:
    cleaned = (language or "").strip().lower()
    if cleaned not in _SUPPORTED_LANGUAGES:
        raise AppError(
            code="UNSUPPORTED_OCR_LANGUAGE",
            message="The requested OCR language is not supported.",
            status_code=400,
        )
    return cleaned


def _resolve_executable() -> str:
    exe = settings.ocr_executable.strip()
    has_separator = "/" in exe or "\\" in exe
    if has_separator:
        if Path(exe).exists():
            return exe
    else:
        resolved = shutil.which(exe)
        if resolved:
            return resolved
    raise AppError(
        code="OCR_ENGINE_UNAVAILABLE",
        message="The OCR engine is not available.",
        status_code=503,
    )


def ensure_tesseract_available() -> str:
    """Locate the OCR engine and confirm it runs. Raises OCR_ENGINE_UNAVAILABLE."""
    executable = _resolve_executable()
    try:
        result = subprocess.run(  # noqa: S603 — argv list, no shell
            [executable, "--version"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
        raise AppError(
            code="OCR_ENGINE_UNAVAILABLE",
            message="The OCR engine is not available.",
            status_code=503,
        ) from exc
    if result.returncode != 0:
        raise AppError(
            code="OCR_ENGINE_UNAVAILABLE",
            message="The OCR engine is not available.",
            status_code=503,
        )
    logger.info("ocr_engine_available", status="success")
    return executable


def parse_tsv(tsv_text: str, *, min_confidence: int) -> tuple[list[RawOcrWord], int, int]:
    """Parse Tesseract TSV into (words, image_width, image_height).

    Word rows below ``min_confidence`` or with non-positive size are dropped. The
    page-level row (level 1) supplies image dimensions when present.
    """
    words: list[RawOcrWord] = []
    image_width = 0
    image_height = 0
    for index, line in enumerate(tsv_text.splitlines()):
        if index == 0 and line.lower().startswith("level"):
            continue
        parts = line.split("\t")
        if len(parts) < _TSV_MIN_COLUMNS:
            continue
        try:
            level = int(parts[0])
            left = int(parts[6])
            top = int(parts[7])
            width = int(parts[8])
            height = int(parts[9])
        except ValueError:
            continue
        if level == _PAGE_LEVEL:
            image_width = max(image_width, width)
            image_height = max(image_height, height)
            continue
        if level != _WORD_LEVEL:
            continue
        text = parts[11].strip()
        if not text:
            continue
        try:
            conf = float(parts[10])
            block_no = int(parts[2])
            line_no = int(parts[4])
            word_no = int(parts[5])
        except ValueError:
            continue
        if conf < 0:  # tesseract emits -1 for structural rows
            continue
        if conf < min_confidence:
            continue
        if width <= 0 or height <= 0:
            continue
        words.append(
            RawOcrWord(
                text=text,
                left=left,
                top=top,
                width=width,
                height=height,
                confidence=conf,
                block_no=block_no,
                line_no=line_no,
                word_no=word_no,
            )
        )
    return words, image_width, image_height


def _image_dimensions(image_path: Path) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            return int(img.width), int(img.height)
    except Exception:
        return 0, 0


class TesseractAdapter:
    """Concrete :class:`OcrEngine` backed by the Tesseract CLI."""

    def __init__(
        self,
        *,
        executable: str | None = None,
        language: str | None = None,
        timeout_seconds: int | None = None,
        min_confidence: int | None = None,
    ) -> None:
        self._executable = executable
        self._language = _validate_language(language or settings.ocr_language)
        self._timeout = timeout_seconds or settings.ocr_timeout_seconds
        self._min_confidence = (
            min_confidence if min_confidence is not None else settings.ocr_min_word_confidence
        )

    def _exe(self) -> str:
        if self._executable is None:
            self._executable = _resolve_executable()
        return self._executable

    def run(self, image_path: Path) -> RawOcrResult:
        argv = [
            self._exe(),
            str(image_path),
            "stdout",
            "-l",
            self._language,
            "--psm",
            "3",
            "tsv",
        ]
        try:
            result = subprocess.run(  # noqa: S603 — argv list, no shell
                argv,
                capture_output=True,
                timeout=self._timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise AppError(
                code="OCR_ENGINE_UNAVAILABLE",
                message="The OCR engine is not available.",
                status_code=503,
            ) from exc
        except subprocess.TimeoutExpired as exc:
            logger.error("ocr_timeout", error_code="OCR_TIMEOUT")
            raise AppError(
                code="OCR_TIMEOUT",
                message="OCR timed out while processing the document.",
                status_code=504,
            ) from exc
        except (subprocess.SubprocessError, OSError) as exc:
            logger.error("ocr_failed", error_code="OCR_FAILED")
            raise AppError(
                code="OCR_FAILED",
                message="OCR could not process the document.",
                status_code=500,
            ) from exc

        if result.returncode != 0:
            logger.error("ocr_nonzero_exit", error_code="OCR_FAILED")
            raise AppError(
                code="OCR_FAILED",
                message="OCR could not process the document.",
                status_code=500,
            )

        tsv_text = result.stdout.decode("utf-8", errors="replace")
        words, width, height = parse_tsv(tsv_text, min_confidence=self._min_confidence)
        if width <= 0 or height <= 0:
            width, height = _image_dimensions(image_path)
        return RawOcrResult(words=words, image_width=width, image_height=height)


def get_default_ocr_engine() -> OcrEngine:
    return TesseractAdapter()
