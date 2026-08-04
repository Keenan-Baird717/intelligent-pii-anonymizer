"""Lightweight single-instance concurrency controls for expensive MVP operations.

Limits are per API process. They do not replace distributed rate limiting.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from app.core.config import settings
from app.core.errors import AppError


@dataclass(frozen=True)
class ConcurrencySlot:
    name: str


class _BoundedSemaphorePool:
    def __init__(self) -> None:
        self._locks = threading.Lock()
        self._semaphores: dict[str, threading.BoundedSemaphore] = {}

    def _get(self, name: str, limit: int) -> threading.BoundedSemaphore:
        with self._locks:
            existing = self._semaphores.get(name)
            if existing is None:
                existing = threading.BoundedSemaphore(limit)
                self._semaphores[name] = existing
            return existing

    def reset(self) -> None:
        """Test helper — recreate semaphores from current settings."""
        with self._locks:
            self._semaphores.clear()

    @contextmanager
    def acquire(self, name: str, limit: int) -> Iterator[ConcurrencySlot]:
        semaphore = self._get(name, limit)
        acquired = semaphore.acquire(blocking=False)
        if not acquired:
            raise AppError(
                code="RESOURCE_BUSY",
                message="The service is busy processing other documents. Please retry shortly.",
                status_code=429,
                headers={"Retry-After": str(settings.concurrency_retry_after_seconds)},
            )
        try:
            yield ConcurrencySlot(name=name)
        finally:
            semaphore.release()


_pool = _BoundedSemaphorePool()


def reset_concurrency_limits() -> None:
    _pool.reset()


@contextmanager
def upload_slot() -> Iterator[ConcurrencySlot]:
    with _pool.acquire("upload", settings.max_concurrent_uploads) as slot:
        yield slot


@contextmanager
def document_job_slot() -> Iterator[ConcurrencySlot]:
    with _pool.acquire("document", settings.max_concurrent_document_jobs) as slot:
        yield slot


@contextmanager
def ocr_slot() -> Iterator[ConcurrencySlot]:
    with _pool.acquire("ocr", settings.max_concurrent_ocr_jobs) as slot:
        yield slot


@contextmanager
def redaction_slot() -> Iterator[ConcurrencySlot]:
    with _pool.acquire("redaction", settings.max_concurrent_redactions) as slot:
        yield slot


@contextmanager
def regex_test_slot() -> Iterator[ConcurrencySlot]:
    # Reuse document limit for custom-recognizer testing to avoid a fourth pool class.
    with _pool.acquire("regex_test", settings.max_concurrent_document_jobs) as slot:
        yield slot


class JobLockRegistry:
    """Per-job exclusive locks for analyze / redact / delete races (single instance)."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._holders: dict[str, str] = {}

    def _lock_for(self, job_id: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(job_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[job_id] = lock
            return lock

    @contextmanager
    def acquire(self, job_id: str, operation: str) -> Iterator[None]:
        lock = self._lock_for(job_id)
        if not lock.acquire(blocking=False):
            raise AppError(
                code="JOB_BUSY",
                message="This job is currently being processed. Please retry shortly.",
                status_code=409,
                headers={"Retry-After": str(settings.concurrency_retry_after_seconds)},
            )
        with self._guard:
            self._holders[job_id] = operation
        try:
            yield
        finally:
            with self._guard:
                self._holders.pop(job_id, None)
            lock.release()

    def is_locked(self, job_id: str) -> bool:
        with self._guard:
            return job_id in self._holders

    def reset(self) -> None:
        with self._guard:
            self._locks.clear()
            self._holders.clear()


job_locks = JobLockRegistry()


async def run_in_thread_with_slot(slot_cm: object, func: object, *args: object) -> object:
    """Optional async helper; MVP routes remain sync but keep slots release-safe."""
    loop = asyncio.get_running_loop()

    def _runner() -> object:
        with slot_cm:  # type: ignore[attr-defined]
            return func(*args)  # type: ignore[operator]

    return await loop.run_in_executor(None, _runner)
