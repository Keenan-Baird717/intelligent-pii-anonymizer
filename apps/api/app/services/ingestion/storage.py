from __future__ import annotations

import os
import re
import secrets
import stat
from pathlib import Path

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)

_STORAGE_KEY_BYTES = 16
# Server-generated keys only: 32 hex chars + validated extension.
_STORAGE_KEY_RE = re.compile(r"^[0-9a-f]{32}\.(pdf|png|jpg|jpeg)$")
_QUARANTINE_RE = re.compile(r"^\.quarantine-[0-9a-f]{32}$")
# Temporary write targets use Path.with_suffix(".writing.pdf") → "{hex}.writing.pdf"
_ARTIFACT_WRITING_RE = re.compile(r"^[0-9a-f]{32}\.writing\.(pdf|png|jpg|jpeg)$")
# Also accept accidental "{hex}.pdf.writing" variants if any code path uses them.
_ARTIFACT_WRITING_ALT_RE = re.compile(r"^[0-9a-f]{32}\.(pdf|png|jpg|jpeg)\.writing$")


def ensure_upload_directory(path: Path | None = None) -> Path:
    root = (path or settings.temp_upload_path).resolve()
    try:
        root.mkdir(parents=True, exist_ok=True)
        _restrict_directory_permissions(root)
    except OSError as exc:
        logger.error("storage_directory_failure", error_code="STORAGE_FAILURE")
        raise AppError(
            code="STORAGE_FAILURE",
            message="Temporary storage is unavailable.",
            status_code=500,
        ) from exc
    if not root.is_dir():
        raise AppError(
            code="STORAGE_FAILURE",
            message="Temporary storage is unavailable.",
            status_code=500,
        )
    return root


def generate_storage_key(extension: str) -> str:
    if not extension.startswith("."):
        extension = f".{extension}"
    extension = extension.lower()
    if extension == ".jpeg":
        extension = ".jpg"
    if extension not in {".pdf", ".png", ".jpg"}:
        raise AppError(
            code="STORAGE_FAILURE",
            message="Temporary storage is unavailable.",
            status_code=500,
        )
    key = f"{secrets.token_hex(_STORAGE_KEY_BYTES)}{extension}"
    assert_valid_storage_key(key)
    return key


def assert_valid_storage_key(storage_key: str) -> None:
    if not storage_key or "\x00" in storage_key:
        raise AppError(
            code="STORAGE_FAILURE",
            message="Temporary storage is unavailable.",
            status_code=500,
        )
    if "/" in storage_key or "\\" in storage_key or ".." in storage_key:
        raise AppError(
            code="STORAGE_FAILURE",
            message="Temporary storage is unavailable.",
            status_code=500,
        )
    # Reject absolute / UNC / drive-relative forms even if somehow present.
    if storage_key.startswith(("/", "\\")) or (len(storage_key) >= 2 and storage_key[1] == ":"):
        raise AppError(
            code="STORAGE_FAILURE",
            message="Temporary storage is unavailable.",
            status_code=500,
        )
    if not _STORAGE_KEY_RE.fullmatch(storage_key):
        raise AppError(
            code="STORAGE_FAILURE",
            message="Temporary storage is unavailable.",
            status_code=500,
        )


def is_managed_filename(name: str) -> bool:
    """Return True if a filename looks like a server-managed upload/artifact/quarantine name."""
    if not name or "\x00" in name or "/" in name or "\\" in name:
        return False
    return bool(
        _STORAGE_KEY_RE.fullmatch(name)
        or _QUARANTINE_RE.fullmatch(name)
        or _ARTIFACT_WRITING_RE.fullmatch(name)
        or _ARTIFACT_WRITING_ALT_RE.fullmatch(name)
    )


def resolve_storage_path(storage_key: str, root: Path | None = None) -> Path:
    """Resolve a server-generated storage key under the controlled directory."""
    base = ensure_upload_directory(root)
    assert_valid_storage_key(storage_key)
    candidate = base / storage_key
    # Resolve without following the final component if it is a symlink.
    try:
        resolved_parent = candidate.parent.resolve(strict=False)
        resolved_parent.relative_to(base)
    except ValueError as exc:
        raise AppError(
            code="STORAGE_FAILURE",
            message="Temporary storage is unavailable.",
            status_code=500,
        ) from exc

    if candidate.exists() or candidate.is_symlink():
        _assert_safe_existing_path(candidate, base)

    # Final containment check on the logical path under base.
    try:
        (base / storage_key).resolve().relative_to(base)
    except ValueError as exc:
        raise AppError(
            code="STORAGE_FAILURE",
            message="Temporary storage is unavailable.",
            status_code=500,
        ) from exc
    return base / storage_key


def _assert_safe_existing_path(path: Path, base: Path) -> None:
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise AppError(
            code="STORAGE_FAILURE",
            message="Temporary storage is unavailable.",
            status_code=500,
        ) from exc

    if stat.S_ISLNK(st.st_mode):
        raise AppError(
            code="UNSAFE_STORAGE_PATH",
            message="Temporary storage path is unsafe.",
            status_code=400,
        )
    if not stat.S_ISREG(st.st_mode):
        raise AppError(
            code="UNSAFE_STORAGE_PATH",
            message="Temporary storage path is unsafe.",
            status_code=400,
        )
    try:
        path.resolve().relative_to(base)
    except ValueError as exc:
        raise AppError(
            code="STORAGE_FAILURE",
            message="Temporary storage is unavailable.",
            status_code=500,
        ) from exc


def write_stream_to_quarantine(
    chunks: object,
    *,
    max_bytes: int,
    chunk_size: int,
    root: Path | None = None,
) -> tuple[Path, int, bytes]:
    """Stream upload chunks to a quarantine file. Returns path, size, and header bytes."""
    base = ensure_upload_directory(root)
    quarantine_name = f".quarantine-{secrets.token_hex(16)}"
    if not _QUARANTINE_RE.fullmatch(quarantine_name):
        raise AppError(
            code="STORAGE_FAILURE",
            message="Temporary storage is unavailable.",
            status_code=500,
        )
    quarantine_path = base / quarantine_name
    try:
        quarantine_path.resolve().relative_to(base)
    except ValueError as exc:
        raise AppError(
            code="STORAGE_FAILURE",
            message="Temporary storage is unavailable.",
            status_code=500,
        ) from exc

    size = 0
    header = bytearray()
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(quarantine_path, flags, 0o600 if os.name != "nt" else 0o666)
        with os.fdopen(fd, "wb") as handle:
            _restrict_file_permissions(quarantine_path)
            for chunk in chunks:  # type: ignore[attr-defined]
                if not chunk:
                    continue
                size += len(chunk)
                if size > max_bytes:
                    raise AppError(
                        code="FILE_TOO_LARGE",
                        message="The uploaded file exceeds the maximum allowed size.",
                        status_code=413,
                    )
                if len(header) < 64:
                    needed = 64 - len(header)
                    header.extend(chunk[:needed])
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
    except AppError:
        safe_unlink(quarantine_path)
        raise
    except OSError as exc:
        safe_unlink(quarantine_path)
        logger.error("storage_write_failure", error_code="STORAGE_FAILURE")
        raise AppError(
            code="STORAGE_FAILURE",
            message="Temporary storage is unavailable.",
            status_code=500,
        ) from exc

    if size == 0:
        safe_unlink(quarantine_path)
        raise AppError(
            code="EMPTY_FILE",
            message="The uploaded file is empty.",
            status_code=400,
        )
    return quarantine_path, size, bytes(header)


def promote_quarantine(quarantine_path: Path, storage_key: str, root: Path | None = None) -> Path:
    final_path = resolve_storage_path(storage_key, root)
    try:
        # Refuse to promote through a symlink destination.
        if final_path.is_symlink() or quarantine_path.is_symlink():
            raise AppError(
                code="UNSAFE_STORAGE_PATH",
                message="Temporary storage path is unsafe.",
                status_code=400,
            )
        os.replace(quarantine_path, final_path)
        _restrict_file_permissions(final_path)
    except AppError:
        safe_unlink(quarantine_path)
        safe_unlink(final_path)
        raise
    except OSError as exc:
        safe_unlink(quarantine_path)
        safe_unlink(final_path)
        logger.error("storage_promote_failure", error_code="STORAGE_FAILURE")
        raise AppError(
            code="STORAGE_FAILURE",
            message="Temporary storage is unavailable.",
            status_code=500,
        ) from exc
    return final_path


def safe_unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        if path.is_symlink():
            path.unlink(missing_ok=True)
            return
        if path.exists():
            # Only unlink regular files.
            st = os.lstat(path)
            if stat.S_ISREG(st.st_mode):
                path.unlink(missing_ok=True)
    except OSError:
        logger.error("storage_unlink_failure", error_code="DELETE_FAILED")


def delete_stored_file(storage_key: str, root: Path | None = None) -> None:
    path = resolve_storage_path(storage_key, root)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise AppError(
            code="DELETE_FAILED",
            message="The job could not be deleted.",
            status_code=500,
        ) from exc

    if stat.S_ISLNK(st.st_mode):
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise AppError(
                code="DELETE_FAILED",
                message="The job could not be deleted.",
                status_code=500,
            ) from exc
        return
    if not stat.S_ISREG(st.st_mode):
        raise AppError(
            code="UNSAFE_STORAGE_PATH",
            message="Temporary storage path is unsafe.",
            status_code=400,
        )
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise AppError(
            code="DELETE_FAILED",
            message="The job could not be deleted.",
            status_code=500,
        ) from exc


def _restrict_directory_permissions(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        os.chmod(path, stat.S_IRWXU)
    except OSError:
        pass


def _restrict_file_permissions(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
