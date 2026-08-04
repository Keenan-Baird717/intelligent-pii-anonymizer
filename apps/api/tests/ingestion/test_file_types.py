import pytest

from app.core.errors import AppError
from app.models.processing_job import ValidatedFileType
from app.services.ingestion.file_types import (
    canonical_extension,
    normalize_extension,
    normalize_mime_type,
    resolve_client_hints,
)


def test_jpg_and_jpeg_extensions_map_to_jpeg() -> None:
    assert normalize_extension("photo.jpg") == ".jpg"
    assert normalize_extension("photo.jpeg") == ".jpeg"
    assert resolve_client_hints("photo.jpg", "image/jpeg").file_type is ValidatedFileType.jpeg
    assert resolve_client_hints("photo.jpeg", "image/jpeg").file_type is ValidatedFileType.jpeg


def test_canonical_extension_preserves_jpg_jpeg() -> None:
    assert canonical_extension(ValidatedFileType.jpeg, ".jpg") == ".jpg"
    assert canonical_extension(ValidatedFileType.jpeg, ".jpeg") == ".jpeg"
    assert canonical_extension(ValidatedFileType.png, ".png") == ".png"
    assert canonical_extension(ValidatedFileType.pdf, ".pdf") == ".pdf"


def test_path_traversal_filename_uses_final_segment() -> None:
    assert normalize_extension("../../etc/passwd.pdf") == ".pdf"
    assert normalize_extension("..\\..\\Windows\\System32\\fictional.pdf") == ".pdf"


def test_windows_path_filename() -> None:
    hints = resolve_client_hints(
        r"C:\Users\fake\Alice_Smith_SSN_999.pdf",
        "application/pdf",
    )
    assert hints.extension == ".pdf"
    assert hints.file_type is ValidatedFileType.pdf


def test_double_extension_exe_rejected() -> None:
    with pytest.raises(AppError) as exc:
        normalize_extension("report.pdf.exe")
    assert exc.value.code == "UNSUPPORTED_FILE_TYPE"


def test_double_extension_dangerous_middle_rejected() -> None:
    with pytest.raises(AppError) as exc:
        normalize_extension("malware.exe.pdf")
    assert exc.value.code == "UNSUPPORTED_FILE_TYPE"


def test_unsupported_extension() -> None:
    with pytest.raises(AppError) as exc:
        normalize_extension("notes.txt")
    assert exc.value.code == "UNSUPPORTED_FILE_TYPE"


def test_missing_filename() -> None:
    with pytest.raises(AppError) as exc:
        normalize_extension(None)
    assert exc.value.code == "UNSUPPORTED_FILE_TYPE"


def test_unsupported_mime() -> None:
    with pytest.raises(AppError) as exc:
        normalize_mime_type("application/zip")
    assert exc.value.code == "MIME_TYPE_MISMATCH"


def test_extension_mime_mismatch() -> None:
    with pytest.raises(AppError) as exc:
        resolve_client_hints("doc.pdf", "image/png")
    assert exc.value.code == "MIME_TYPE_MISMATCH"


def test_mime_strips_parameters() -> None:
    assert normalize_mime_type("application/pdf; charset=binary") == "application/pdf"


def test_fictional_pii_filename_still_resolves_extension() -> None:
    # Filename may contain fictional PII-looking tokens; only extension is used.
    hints = resolve_client_hints("Jane_Doe_SSN_123-45-6789.pdf", "application/pdf")
    assert hints.file_type is ValidatedFileType.pdf
