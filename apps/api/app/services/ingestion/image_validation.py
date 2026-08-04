from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.processing_job import ValidatedFileType

logger = get_logger(__name__)


@dataclass(frozen=True)
class ImageValidationResult:
    width: int
    height: int


_EXPECTED_FORMAT = {
    ValidatedFileType.png: "PNG",
    ValidatedFileType.jpeg: "JPEG",
}


def validate_image(
    path: Path,
    expected_type: ValidatedFileType,
    *,
    max_pixels: int | None = None,
) -> ImageValidationResult:
    """Decode an image only to validate structure and dimensions. No OCR or mutation."""
    if expected_type not in _EXPECTED_FORMAT:
        raise AppError(
            code="UNSUPPORTED_FILE_TYPE",
            message="Unsupported or missing file type.",
            status_code=400,
        )
    limit = max_pixels if max_pixels is not None else settings.max_image_pixels

    try:
        from PIL import Image, ImageFile, UnidentifiedImageError

        ImageFile.LOAD_TRUNCATED_IMAGES = False
        previous_limit = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = limit
    except ImportError as exc:
        logger.error("image_library_missing", error_code="STORAGE_FAILURE")
        raise AppError(
            code="STORAGE_FAILURE",
            message="Document validation is temporarily unavailable.",
            status_code=500,
        ) from exc

    image = None
    try:
        image = Image.open(path)
        image.load()
        fmt = (image.format or "").upper()
        expected = _EXPECTED_FORMAT[expected_type]
        if fmt != expected:
            raise AppError(
                code="IMAGE_FORMAT_MISMATCH",
                message="The image format does not match the declared type.",
                status_code=400,
            )
        # Reject animated / multi-frame inputs for the MVP.
        n_frames = getattr(image, "n_frames", 1) or 1
        if n_frames > 1:
            raise AppError(
                code="UNSUPPORTED_IMAGE_FRAMES",
                message="Animated or multi-frame images are not accepted.",
                status_code=400,
            )
        width, height = image.size
        if width <= 0 or height <= 0:
            raise AppError(
                code="INVALID_IMAGE_DIMENSIONS",
                message="The image dimensions are invalid.",
                status_code=400,
            )
        pixels = width * height
        if pixels > limit:
            raise AppError(
                code="IMAGE_PIXEL_LIMIT_EXCEEDED",
                message="The image exceeds the maximum allowed pixel count.",
                status_code=400,
            )
        # Touch EXIF/info only to ensure malformed metadata does not crash later paths.
        try:
            _ = image.getexif()
        except Exception:
            # Invalid EXIF is acceptable on input; it will be stripped from outputs.
            pass
        return ImageValidationResult(width=width, height=height)
    except AppError:
        raise
    except Image.DecompressionBombError as exc:
        logger.error("image_pixel_limit", error_code="IMAGE_PIXEL_LIMIT_EXCEEDED")
        raise AppError(
            code="IMAGE_PIXEL_LIMIT_EXCEEDED",
            message="The image exceeds the maximum allowed pixel count.",
            status_code=400,
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        logger.error("corrupt_image", error_code="CORRUPT_IMAGE")
        raise AppError(
            code="CORRUPT_IMAGE",
            message="The image could not be validated.",
            status_code=400,
        ) from exc
    except Exception as exc:
        logger.error("corrupt_image", error_code="CORRUPT_IMAGE")
        raise AppError(
            code="CORRUPT_IMAGE",
            message="The image could not be validated.",
            status_code=400,
        ) from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit
        if image is not None:
            try:
                image.close()
            except Exception:
                pass
