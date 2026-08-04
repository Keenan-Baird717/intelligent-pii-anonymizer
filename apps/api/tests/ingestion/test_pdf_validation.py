from pathlib import Path

import pytest

from app.core.errors import AppError
from app.services.ingestion.pdf_validation import validate_pdf
from tests.helpers.fictional_files import (
    make_fictional_pdf_bytes,
    make_password_protected_pdf_bytes,
    write_bytes,
)


def test_valid_pdf(tmp_path: Path) -> None:
    path = write_bytes(tmp_path / "ok.pdf", make_fictional_pdf_bytes(pages=2))
    result = validate_pdf(path, max_pages=50)
    assert result.page_count == 2


def test_corrupt_pdf(tmp_path: Path) -> None:
    path = write_bytes(tmp_path / "bad.pdf", b"%PDF-1.4\nnot-valid")
    with pytest.raises(AppError) as exc:
        validate_pdf(path)
    assert exc.value.code == "CORRUPT_PDF"


def test_password_protected_pdf(tmp_path: Path) -> None:
    path = write_bytes(tmp_path / "locked.pdf", make_password_protected_pdf_bytes())
    with pytest.raises(AppError) as exc:
        validate_pdf(path)
    assert exc.value.code == "PASSWORD_PROTECTED_PDF"


def test_pdf_page_limit(tmp_path: Path) -> None:
    path = write_bytes(tmp_path / "many.pdf", make_fictional_pdf_bytes(pages=5))
    with pytest.raises(AppError) as exc:
        validate_pdf(path, max_pages=3)
    assert exc.value.code == "PDF_PAGE_LIMIT_EXCEEDED"
