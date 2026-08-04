from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import AppError
from app.models.processing_job import ValidatedFileType
from app.services.ingestion.signatures import DetectedKind

SUPPORTED_EXTENSIONS = {
    ".pdf": ValidatedFileType.pdf,
    ".png": ValidatedFileType.png,
    ".jpg": ValidatedFileType.jpeg,
    ".jpeg": ValidatedFileType.jpeg,
}

SUPPORTED_MIME_TYPES = {
    "application/pdf": ValidatedFileType.pdf,
    "image/png": ValidatedFileType.png,
    "image/jpeg": ValidatedFileType.jpeg,
}

SIGNATURE_TO_TYPE = {
    DetectedKind.pdf: ValidatedFileType.pdf,
    DetectedKind.png: ValidatedFileType.png,
    DetectedKind.jpeg: ValidatedFileType.jpeg,
}


@dataclass(frozen=True)
class ClientFileHints:
    extension: str
    mime_type: str
    file_type: ValidatedFileType


def normalize_extension(filename: str | None) -> str:
    """Return a single lowercase extension from the final path segment only."""
    if not filename:
        raise AppError(
            code="UNSUPPORTED_FILE_TYPE",
            message="Unsupported or missing file type.",
            status_code=400,
        )
    # Strip path components from client filename without using them for storage.
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not name or name in {".", ".."}:
        raise AppError(
            code="UNSUPPORTED_FILE_TYPE",
            message="Unsupported or missing file type.",
            status_code=400,
        )
    lower = name.lower()
    # Reject obvious double-extension disguises like report.pdf.exe
    parts = lower.split(".")
    if len(parts) < 2:
        raise AppError(
            code="UNSUPPORTED_FILE_TYPE",
            message="Unsupported or missing file type.",
            status_code=400,
        )
    # Only the final extension is considered; intermediate names are ignored for type.
    extension = f".{parts[-1]}"
    if extension not in SUPPORTED_EXTENSIONS:
        raise AppError(
            code="UNSUPPORTED_FILE_TYPE",
            message="Unsupported or missing file type.",
            status_code=400,
        )
    # Reject if an earlier segment looks like a supported type followed by unsupported
    # (e.g. document.pdf.exe already caught). Also reject .exe/.bat/.js etc. earlier.
    dangerous_middle = {
        "exe",
        "bat",
        "cmd",
        "com",
        "dll",
        "scr",
        "js",
        "vbs",
        "ps1",
        "msi",
        "apk",
    }
    if any(part in dangerous_middle for part in parts[1:-1]):
        raise AppError(
            code="UNSUPPORTED_FILE_TYPE",
            message="Unsupported or missing file type.",
            status_code=400,
        )
    return extension


def normalize_mime_type(content_type: str | None) -> str:
    if not content_type:
        raise AppError(
            code="MIME_TYPE_MISMATCH",
            message="The declared content type is missing or unsupported.",
            status_code=400,
        )
    mime = content_type.split(";", 1)[0].strip().lower()
    if mime not in SUPPORTED_MIME_TYPES:
        raise AppError(
            code="MIME_TYPE_MISMATCH",
            message="The declared content type is missing or unsupported.",
            status_code=400,
        )
    return mime


def resolve_client_hints(filename: str | None, content_type: str | None) -> ClientFileHints:
    extension = normalize_extension(filename)
    mime_type = normalize_mime_type(content_type)
    ext_type = SUPPORTED_EXTENSIONS[extension]
    mime_as_type = SUPPORTED_MIME_TYPES[mime_type]
    if ext_type != mime_as_type:
        raise AppError(
            code="MIME_TYPE_MISMATCH",
            message="The file extension and declared content type do not match.",
            status_code=400,
        )
    return ClientFileHints(extension=extension, mime_type=mime_type, file_type=ext_type)


def canonical_extension(file_type: ValidatedFileType, client_extension: str) -> str:
    if file_type is ValidatedFileType.jpeg:
        return client_extension if client_extension in {".jpg", ".jpeg"} else ".jpg"
    if file_type is ValidatedFileType.png:
        return ".png"
    return ".pdf"
