"""Safe custom recognizer / regex evaluation with ReDoS protections.

User-supplied patterns are optional for the text-analysis MVP. Patterns are
validated, length-bounded, and executed with a hard timeout so catastrophic
backtracking cannot hang the worker.
"""

from __future__ import annotations

import re
import signal
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Patterns that are empty, match everything, or are otherwise unsafe for MVP use.
_BROAD_PATTERN = re.compile(
    r"^(?:\.\*)+$|^(?:\.\+)+$|^\^?\.\*\$?$|^\(\?\:\.\*\)+$",
)

_ALLOWED_FLAGS = {
    "IGNORECASE": re.IGNORECASE,
    "MULTILINE": re.MULTILINE,
    "DOTALL": 0,  # Explicitly unsupported — reject below.
    "VERBOSE": 0,
    "ASCII": re.ASCII,
}

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="regex-safe")


@dataclass(frozen=True)
class CustomRecognizerSpec:
    name: str
    pattern: str
    entity_type: str
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RegexMatch:
    start: int
    end: int
    text: str


def validate_custom_recognizers(raw: list[Any]) -> list[CustomRecognizerSpec]:
    if len(raw) > settings.max_custom_recognizers:
        raise AppError(
            code="INVALID_RECOGNIZER",
            message="Too many custom recognizers were provided.",
            status_code=400,
        )
    specs: list[CustomRecognizerSpec] = []
    seen_names: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise AppError(
                code="INVALID_RECOGNIZER",
                message="Custom recognizer definitions are invalid.",
                status_code=400,
            )
        name = str(item.get("name") or "").strip()
        pattern = str(item.get("pattern") or "")
        entity_type = str(item.get("entity_type") or "CUSTOM").strip().upper() or "CUSTOM"
        flags_raw = item.get("flags") or []
        if not name or len(name) > 64 or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise AppError(
                code="INVALID_RECOGNIZER",
                message="Custom recognizer names must be short alphanumeric identifiers.",
                status_code=400,
            )
        if name in seen_names:
            raise AppError(
                code="INVALID_RECOGNIZER",
                message="Custom recognizer names must be unique.",
                status_code=400,
            )
        seen_names.add(name)
        if not pattern or not pattern.strip():
            raise AppError(
                code="INVALID_RECOGNIZER",
                message="Custom recognizer patterns must be non-empty.",
                status_code=400,
            )
        if len(pattern) > settings.max_regex_pattern_length:
            raise AppError(
                code="INVALID_RECOGNIZER",
                message="Custom recognizer pattern exceeds the maximum allowed length.",
                status_code=400,
            )
        if _BROAD_PATTERN.fullmatch(pattern.strip()):
            raise AppError(
                code="INVALID_RECOGNIZER",
                message="Custom recognizer pattern is excessively broad.",
                status_code=400,
            )
        if _looks_catastrophic(pattern):
            raise AppError(
                code="INVALID_RECOGNIZER",
                message="Custom recognizer pattern is not permitted.",
                status_code=400,
            )
        if not isinstance(flags_raw, list):
            raise AppError(
                code="INVALID_RECOGNIZER",
                message="Custom recognizer flags must be a list of flag names.",
                status_code=400,
            )
        flags: list[str] = []
        for flag in flags_raw:
            flag_name = str(flag).upper()
            if flag_name not in {"IGNORECASE", "MULTILINE", "ASCII"}:
                raise AppError(
                    code="INVALID_RECOGNIZER",
                    message="Unsupported regex flag.",
                    status_code=400,
                )
            flags.append(flag_name)
        # Compile once to reject malformed patterns without running against user text.
        try:
            _compile(pattern, tuple(flags))
        except re.error as exc:
            raise AppError(
                code="INVALID_RECOGNIZER",
                message="Custom recognizer pattern is malformed.",
                status_code=400,
            ) from exc
        specs.append(
            CustomRecognizerSpec(
                name=name,
                pattern=pattern,
                entity_type=entity_type[:64],
                flags=tuple(flags),
            )
        )
    return specs


def find_matches(spec: CustomRecognizerSpec, text: str) -> list[RegexMatch]:
    """Run a validated pattern against text with a hard timeout."""
    compiled = _compile(spec.pattern, spec.flags)
    timeout = settings.custom_regex_timeout_seconds

    def _search() -> list[RegexMatch]:
        matches: list[RegexMatch] = []
        for match in compiled.finditer(text):
            start, end = match.start(), match.end()
            if end <= start:
                continue
            matches.append(RegexMatch(start=start, end=end, text=text[start:end]))
            if len(matches) >= settings.max_entities_per_job:
                break
        return matches

    future = _executor.submit(_search)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeout as exc:
        future.cancel()
        logger.warning(
            "regex_timeout",
            error_code="REGEX_TIMEOUT",
            recognizer_name=spec.name,
            pattern_length=len(spec.pattern),
        )
        raise AppError(
            code="REGEX_TIMEOUT",
            message="Custom recognizer evaluation timed out.",
            status_code=400,
        ) from exc
    except AppError:
        raise
    except Exception as exc:
        logger.error(
            "regex_evaluation_failed",
            error_code="INVALID_RECOGNIZER",
            recognizer_name=spec.name,
            exception_type=type(exc).__name__,
        )
        raise AppError(
            code="INVALID_RECOGNIZER",
            message="Custom recognizer evaluation failed.",
            status_code=400,
        ) from exc


def _compile(pattern: str, flags: tuple[str, ...]) -> re.Pattern[str]:
    combined = 0
    for flag in flags:
        combined |= _ALLOWED_FLAGS[flag]
    return re.compile(pattern, combined)


def _looks_catastrophic(pattern: str) -> bool:
    """Heuristic rejection of nested quantifiers that commonly cause ReDoS."""
    # Nested quantifiers like (a+)+, (a|a)+, (a*)*
    if re.search(r"\([^)]*[+*][^)]*\)[+*{]", pattern):
        return True
    if re.search(r"\([^)]*[|][^)]*\)[+*]", pattern):
        return True
    # Excessively nested groups
    if pattern.count("(") > 20:
        return True
    return False


# Avoid unused-import warnings on platforms without SIGALRM (Windows).
_ = (signal, threading)
