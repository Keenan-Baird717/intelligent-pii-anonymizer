from pathlib import Path

import pytest

from app.core.errors import AppError
from app.models.processing_job import ValidatedFileType
from app.services.ingestion.image_validation import validate_image
from tests.helpers.fictional_files import (
    corrupt_jpeg_bytes,
    corrupt_png_bytes,
    make_fictional_jpeg_bytes,
    make_fictional_png_bytes,
    write_bytes,
)


def test_valid_png(tmp_path: Path) -> None:
    path = write_bytes(tmp_path / "ok.png", make_fictional_png_bytes(width=16, height=12))
    result = validate_image(path, ValidatedFileType.png)
    assert result.width == 16
    assert result.height == 12


def test_valid_jpeg(tmp_path: Path) -> None:
    path = write_bytes(tmp_path / "ok.jpg", make_fictional_jpeg_bytes(width=20, height=10))
    result = validate_image(path, ValidatedFileType.jpeg)
    assert result.width == 20
    assert result.height == 10


def test_corrupt_png(tmp_path: Path) -> None:
    path = write_bytes(tmp_path / "bad.png", corrupt_png_bytes())
    with pytest.raises(AppError) as exc:
        validate_image(path, ValidatedFileType.png)
    assert exc.value.code == "CORRUPT_IMAGE"


def test_corrupt_jpeg(tmp_path: Path) -> None:
    path = write_bytes(tmp_path / "bad.jpg", corrupt_jpeg_bytes())
    with pytest.raises(AppError) as exc:
        validate_image(path, ValidatedFileType.jpeg)
    assert exc.value.code == "CORRUPT_IMAGE"


def test_format_mismatch_png_expected_jpeg(tmp_path: Path) -> None:
    path = write_bytes(tmp_path / "mismatch.png", make_fictional_png_bytes())
    with pytest.raises(AppError) as exc:
        validate_image(path, ValidatedFileType.jpeg)
    assert exc.value.code == "IMAGE_FORMAT_MISMATCH"


def test_pixel_limit(tmp_path: Path) -> None:
    path = write_bytes(tmp_path / "big.png", make_fictional_png_bytes(width=100, height=100))
    with pytest.raises(AppError) as exc:
        validate_image(path, ValidatedFileType.png, max_pixels=50)
    assert exc.value.code == "IMAGE_PIXEL_LIMIT_EXCEEDED"
