"""Controlled OCR scratch directory.

OCR must write rendered page images and preprocessed variants to disk so the
Tesseract subprocess can read them. Those files can transiently hold document
imagery, so they live in a locked-down directory *under* the upload root (never a
world-writable temp dir), use crypto-random names, are always path-contained, are
never followed through symlinks, and are deleted eagerly. Nothing here is ever
logged with a filename, path, or content.
"""

from __future__ import annotations

import os
import secrets
import shutil
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.core.errors import AppError
from app.core.logging import get_logger
from app.services.ingestion.storage import ensure_upload_directory

logger = get_logger(__name__)

_WORK_SUBDIR = "ocr-work"
_NAME_BYTES = 16


def _restrict_dir(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        os.chmod(path, stat.S_IRWXU)
    except OSError:
        pass


def _restrict_file(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _fail() -> AppError:
    logger.error("ocr_workfile_failure", error_code="TEMPORARY_WORK_FILE_FAILURE")
    return AppError(
        code="TEMPORARY_WORK_FILE_FAILURE",
        message="A temporary OCR work file could not be created.",
        status_code=500,
    )


def _sanitize_job_id(job_id: object | None) -> str | None:
    if job_id is None:
        return None
    raw = str(job_id)
    safe = "".join(ch for ch in raw if ch in "0123456789abcdefABCDEF-")
    return safe or None


def ocr_work_root(root: Path | None = None) -> Path:
    """Return (creating if needed) the OCR scratch root beneath the upload dir."""
    base = ensure_upload_directory(root)
    work = (base / _WORK_SUBDIR).resolve()
    try:
        work.relative_to(base)
    except ValueError as exc:
        raise _fail() from exc
    try:
        work.mkdir(parents=True, exist_ok=True)
        _restrict_dir(work)
    except OSError as exc:
        raise _fail() from exc
    if work.is_symlink() or not work.is_dir():
        raise _fail()
    return work


def _contained_child(parent: Path, name: str) -> Path:
    if not name or "/" in name or "\\" in name or ".." in name:
        raise _fail()
    candidate = (parent / name).resolve()
    try:
        candidate.relative_to(parent)
    except ValueError as exc:
        raise _fail() from exc
    return candidate


def _target_dir(root: Path | None, job_id: object | None) -> Path:
    work = ocr_work_root(root)
    safe = _sanitize_job_id(job_id)
    if safe is None:
        return work
    job_dir = _contained_child(work, safe)
    try:
        job_dir.mkdir(parents=True, exist_ok=True)
        _restrict_dir(job_dir)
    except OSError as exc:
        raise _fail() from exc
    if job_dir.is_symlink() or not job_dir.is_dir():
        raise _fail()
    return job_dir


def allocate_ocr_path(
    suffix: str = ".png",
    *,
    root: Path | None = None,
    job_id: object | None = None,
) -> Path:
    """Return a crypto-random, path-contained work-file path (not yet created)."""
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    work_dir = _target_dir(root, job_id)
    name = f"{secrets.token_hex(_NAME_BYTES)}{suffix}"
    return _contained_child(work_dir, name)


def safe_unlink_ocr(path: Path | None, *, root: Path | None = None) -> None:
    """Delete a work file, refusing to follow symlinks. Never raises."""
    _ = root  # accepted for call-site symmetry; containment enforced at allocation.
    if path is None:
        return
    try:
        if path.is_symlink():
            path.unlink(missing_ok=True)
            return
        if path.exists():
            path.unlink(missing_ok=True)
    except OSError:
        logger.error("ocr_workfile_unlink_failure", error_code="TEMPORARY_WORK_FILE_FAILURE")


@contextmanager
def temporary_ocr_file(
    suffix: str = ".png",
    *,
    root: Path | None = None,
    job_id: object | None = None,
) -> Iterator[Path]:
    """Yield a crypto-random work-file path, always deleting it on exit."""
    path = allocate_ocr_path(suffix, root=root, job_id=job_id)
    try:
        yield path
    finally:
        safe_unlink_ocr(path, root=root)


def cleanup_job_ocr_files(job_id: object, *, root: Path | None = None) -> None:
    """Delete a job's OCR scratch subdirectory and everything inside it."""
    try:
        work = ocr_work_root(root)
    except AppError:
        return
    safe = _sanitize_job_id(job_id)
    if safe is None:
        return
    try:
        job_dir = _contained_child(work, safe)
    except AppError:
        return
    if job_dir.is_symlink():
        safe_unlink_ocr(job_dir, root=root)
        return
    if job_dir.is_dir():
        shutil.rmtree(job_dir, ignore_errors=True)


# Aliases used by callers / Phase 6 services.
cleanup_job_ocr_work = cleanup_job_ocr_files


def ensure_ocr_work_directory(*, root: Path | None = None) -> Path:
    return ocr_work_root(root)


def reconcile_abandoned_ocr_files(
    *,
    root: Path | None = None,
    known_job_ids: set[str] | None = None,
) -> int:
    _ = known_job_ids
    return reconcile_ocr_workspace(root=root)


def reconcile_ocr_workspace(
    *,
    root: Path | None = None,
    max_age_seconds: int = 3600,
) -> int:
    """Remove OCR scratch entries older than ``max_age_seconds`` (crash recovery)."""
    try:
        work = ocr_work_root(root)
    except AppError:
        return 0
    now = time.time()
    removed = 0
    try:
        entries = list(work.iterdir())
    except OSError:
        return 0
    for entry in entries:
        try:
            if entry.is_symlink():
                safe_unlink_ocr(entry, root=root)
                removed += 1
                continue
            age = now - entry.stat().st_mtime
            if age < max_age_seconds:
                continue
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            removed += 1
        except OSError:
            continue
    if removed:
        logger.info("ocr_workfile_reconcile_removed", removed_count=removed)
    return removed
