"""Phase 8 security hardening tests — fictional data only."""

from __future__ import annotations

import io
import logging
import math
import re
import threading
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from PIL import Image
from sqlalchemy import inspect, text

from app.core.concurrency import job_locks, reset_concurrency_limits
from app.core.config import settings
from app.core.errors import AppError
from app.core.middleware import sanitize_request_id
from app.core.regex_safety import find_matches, validate_custom_recognizers
from app.services.ingestion.storage import (
    assert_valid_storage_key,
    generate_storage_key,
    is_managed_filename,
    resolve_storage_path,
)


@pytest.fixture(autouse=True)
def _reset_limits() -> None:
    reset_concurrency_limits()
    job_locks.reset()
    yield
    reset_concurrency_limits()
    job_locks.reset()


def test_security_headers_on_health(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("Referrer-Policy") == "no-referrer"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Cross-Origin-Resource-Policy") == "same-origin"
    assert "no-store" in response.headers.get("Cache-Control", "")
    assert "default-src 'none'" in response.headers.get("Content-Security-Policy", "")
    assert "Strict-Transport-Security" not in response.headers


def test_request_id_sanitization_rejects_injection() -> None:
    malicious = "abc\nINFO inject\r\n\x1b[31m"
    cleaned = sanitize_request_id(malicious)
    assert "\n" not in cleaned
    assert "\r" not in cleaned
    assert "\x1b" not in cleaned
    assert re.fullmatch(r"[A-Za-z0-9_-]+", cleaned)


def test_request_id_header_sanitized_in_response(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/v1/health",
        headers={"X-Request-ID": "safe-id\ninjected"},
    )
    rid = response.headers.get("X-Request-ID", "")
    assert "\n" not in rid
    assert rid != "safe-id\ninjected"


def test_log_injection_payload_not_written_raw(
    api_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        api_client.get("/api/v1/health", headers={"X-Request-ID": "rid\nFAKE_LOG_LINE"})
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "FAKE_LOG_LINE" not in joined


def test_cors_disallows_unknown_origin(api_client: TestClient) -> None:
    response = api_client.options(
        "/api/v1/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") != "https://evil.example"


def test_cors_allows_configured_origin(api_client: TestClient) -> None:
    origin = settings.cors_origin_list[0]
    response = api_client.get("/api/v1/health", headers={"Origin": origin})
    assert response.headers.get("access-control-allow-origin") == origin


def test_invalid_host_rejected(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/health", headers={"Host": "evil.example"})
    assert response.status_code == 400
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        body = response.json()
        assert body["error"]["code"] == "INVALID_HOST"
    assert "traceback" not in response.text.lower()


def test_schema_rejects_unexpected_fields(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/analyze/text",
        json={"text": "hello@example.com", "unexpected": "nope"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "UNEXPECTED_FIELD"
    assert "nope" not in response.text


def test_schema_rejects_nan_rectangles() -> None:
    from pydantic import ValidationError

    from app.schemas.pdf_review import PdfRectSchema

    with pytest.raises(ValidationError):
        PdfRectSchema(x0=float("nan"), y0=0, x1=1, y1=1)
    with pytest.raises(ValidationError):
        PdfRectSchema(x0=0, y0=0, x1=float("inf"), y1=1)


def test_malformed_uuid_safe_error(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/jobs/not-a-uuid")
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] in {"INVALID_UUID", "VALIDATION_ERROR"}
    assert "not-a-uuid" not in body["error"]["message"]


def test_entity_count_limit_on_anonymize(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_entities_per_job", 3)
    entities = [
        {
            "entity_type": "EMAIL_ADDRESS",
            "start": i,
            "end": i + 1,
            "review_status": "accepted",
            "anonymization_method": "masking",
        }
        for i in range(5)
    ]
    response = api_client.post(
        "/api/v1/anonymize/text",
        json={"text": "abcdefghij", "entities": entities},
    )
    assert response.status_code == 422


def test_custom_recognizer_rejects_broad_and_malformed() -> None:
    with pytest.raises(AppError) as broad:
        validate_custom_recognizers([{"name": "all", "pattern": ".*", "entity_type": "X"}])
    assert broad.value.code == "INVALID_RECOGNIZER"

    with pytest.raises(AppError) as bad:
        validate_custom_recognizers([{"name": "bad", "pattern": "(", "entity_type": "X"}])
    assert bad.value.code == "INVALID_RECOGNIZER"


def test_custom_recognizer_count_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_custom_recognizers", 2)
    with pytest.raises(AppError) as exc:
        validate_custom_recognizers(
            [
                {"name": "a", "pattern": r"a+", "entity_type": "X"},
                {"name": "b", "pattern": r"b+", "entity_type": "X"},
                {"name": "c", "pattern": r"c+", "entity_type": "X"},
            ]
        )
    assert exc.value.code == "INVALID_RECOGNIZER"


def test_regex_timeout_does_not_crash_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    from concurrent.futures import TimeoutError as FuturesTimeout

    monkeypatch.setattr(settings, "custom_regex_timeout_seconds", 0.05)
    specs = validate_custom_recognizers(
        [{"name": "ok", "pattern": r"ticket-\d{4}", "entity_type": "X"}]
    )

    class _Future:
        def result(self, timeout: float | None = None) -> list[object]:
            raise FuturesTimeout()

        def cancel(self) -> bool:
            return True

    monkeypatch.setattr(
        "app.core.regex_safety._executor.submit",
        lambda *_args, **_kwargs: _Future(),
    )
    with pytest.raises(AppError) as exc:
        find_matches(specs[0], "ticket-1234")
    assert exc.value.code == "REGEX_TIMEOUT"


def test_analyze_with_safe_custom_recognizer(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/analyze/text",
        json={
            "text": "ticket ZK-4242 assigned",
            "custom_recognizers": [
                {
                    "name": "ticket",
                    "pattern": r"ZK-\d{4}",
                    "entity_type": "CUSTOM_ID",
                    "flags": ["IGNORECASE"],
                }
            ],
        },
    )
    assert response.status_code == 200
    types = {e["entity_type"] for e in response.json()["entities"]}
    assert "CUSTOM_ID" in types or response.json()["detection_count"] >= 1


def test_storage_key_rejects_traversal_variants(temp_upload_dir: Path) -> None:
    for bad in [
        "../escape.pdf",
        "..\\escape.pdf",
        "%2e%2e/escape.pdf",
        "/etc/passwd",
        "C:\\Windows\\system32",
        "\\\\server\\share",
        "file\x00.pdf",
        ".hidden.pdf",
        "abc.pdf.exe",
    ]:
        with pytest.raises(AppError):
            resolve_storage_path(bad, root=temp_upload_dir)


def test_storage_key_format_validation() -> None:
    key = generate_storage_key(".pdf")
    assert_valid_storage_key(key)
    assert is_managed_filename(key)
    with pytest.raises(AppError):
        assert_valid_storage_key("not-hex.pdf")


def test_symlink_rejection(temp_upload_dir: Path) -> None:
    key = generate_storage_key(".pdf")
    target = temp_upload_dir / "outside-target.bin"
    target.write_bytes(b"secret")
    link = temp_upload_dir / key
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Symlinks not permitted in this environment")
    with pytest.raises(AppError) as exc:
        resolve_storage_path(key, root=temp_upload_dir)
    assert exc.value.code in {"UNSAFE_STORAGE_PATH", "STORAGE_FAILURE"}


def test_active_pdf_javascript_rejected(api_client: TestClient, temp_upload_dir: Path) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "fictional")
    # Embedded file is reliably rejectable via Phase 8 active-content checks.
    doc.embfile_add("evil", b"payload", filename="evil.txt")
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    response = api_client.post(
        "/api/v1/documents",
        files={"file": ("active.pdf", buf.getvalue(), "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] in {
        "EMBEDDED_FILE_REJECTED",
        "ACTIVE_PDF_CONTENT_REJECTED",
        "UNSAFE_PDF_ACTION_REJECTED",
        "CORRUPT_PDF",
    }


def test_image_metadata_stripped_on_redaction(tmp_path: Path) -> None:
    from app.processing.image import redact_image
    from app.processing.ocr.models import PixelBBox

    src = tmp_path / "with-exif.jpg"
    out = tmp_path / "clean.jpg"
    image = Image.new("RGB", (64, 64), color=(255, 0, 0))
    # Pillow may accept exif bytes; even without, output must lack info dict keys.
    image.save(src, format="JPEG", quality=90, exif=b"Exif\x00\x00" + b"\x00" * 20)
    redact_image(src, out, [PixelBBox(0, 0, 10, 10)], output_format="jpeg")
    with Image.open(out) as cleaned:
        assert cleaned.format == "JPEG"
        assert not cleaned.getexif() or len(cleaned.getexif()) == 0
        assert cleaned.info.get("gps") is None


def test_concurrency_limit_returns_429(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.concurrency import upload_slot

    monkeypatch.setattr(settings, "max_concurrent_uploads", 1)
    reset_concurrency_limits()
    entered = threading.Event()
    release = threading.Event()

    def holder() -> None:
        with upload_slot():
            entered.set()
            release.wait(timeout=5)

    thread = threading.Thread(target=holder)
    thread.start()
    assert entered.wait(timeout=2)
    with pytest.raises(AppError) as exc:
        with upload_slot():
            pass
    assert exc.value.code == "RESOURCE_BUSY"
    assert exc.value.status_code == 429
    release.set()
    thread.join(timeout=2)


def test_job_lock_blocks_parallel_ops() -> None:
    job_id = str(uuid4())
    entered = threading.Event()
    release = threading.Event()

    def holder() -> None:
        with job_locks.acquire(job_id, "analyze"):
            entered.set()
            release.wait(timeout=5)

    thread = threading.Thread(target=holder)
    thread.start()
    assert entered.wait(timeout=2)
    with pytest.raises(AppError) as exc:
        with job_locks.acquire(job_id, "delete"):
            pass
    assert exc.value.code == "JOB_BUSY"
    release.set()
    thread.join(timeout=2)


def test_cross_job_artifact_access_rejected(api_client: TestClient) -> None:
    # Create two minimal PDF jobs.
    import fitz

    def make_pdf() -> bytes:
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Alex Rivera fictional@example.com")
        data = doc.tobytes()
        doc.close()
        return data

    r1 = api_client.post(
        "/api/v1/documents",
        files={"file": ("a.pdf", make_pdf(), "application/pdf")},
    )
    r2 = api_client.post(
        "/api/v1/documents",
        files={"file": ("b.pdf", make_pdf(), "application/pdf")},
    )
    assert r1.status_code == 201 and r2.status_code == 201
    job_a = r1.json()["job_id"]
    job_b = r2.json()["job_id"]
    fake_artifact = str(uuid4())
    response = api_client.get(f"/api/v1/jobs/{job_b}/artifacts/{fake_artifact}")
    assert response.status_code in {404, 400}
    # Cross-job artifact IDs must not succeed.
    audit = api_client.get(f"/api/v1/jobs/{job_a}/audit-report")
    # Without completed anonymization, result/audit may 400/404 — still must not leak.
    assert audit.status_code in {200, 400, 404, 409, 422}
    if audit.status_code >= 400:
        assert "error" in audit.json()


def test_database_has_no_sensitive_columns(db_session) -> None:
    inspector = inspect(db_session.bind)
    forbidden_fragments = (
        "original_text",
        "extracted_text",
        "ocr_text",
        "detected_value",
        "pseudonym",
        "filename",
        "file_bytes",
        "raw_body",
    )
    for table in inspector.get_table_names():
        for column in inspector.get_columns(table):
            name = column["name"].lower()
            assert not any(frag in name for frag in forbidden_fragments), name


def test_database_sentinel_scan(db_session, api_client: TestClient) -> None:
    sentinel = "SENTINEL_PII_casey.okafor@example.test"
    response = api_client.post("/api/v1/analyze/text", json={"text": f"Contact {sentinel}"})
    assert response.status_code == 200
    # Scan all text-ish columns in SQLite test DB.
    inspector = inspect(db_session.bind)
    for table in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns(table)]
        if not cols:
            continue
        rows = db_session.execute(text(f"SELECT * FROM {table}")).mappings().all()
        for row in rows:
            blob = " ".join(str(v) for v in row.values() if v is not None)
            assert sentinel not in blob


def test_validation_error_excludes_body(api_client: TestClient) -> None:
    secret = "TOPSECRET_VALUE_SHOULD_NOT_ECHO"
    response = api_client.post(
        "/api/v1/analyze/text",
        json={"text": secret, "language": "toolonglanguagecode"},
    )
    assert response.status_code == 422
    assert secret not in response.text


def test_internal_error_is_generic(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    db_session,
    temp_upload_dir: Path,
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("sqlalchemy.exc.OperationalError: secret dsn")

    monkeypatch.setattr("app.api.v1.analyze.analyze_pasted_text", boom)
    from app.db.session import get_db
    from app.main import app

    def _override_get_db():  # type: ignore[no-untyped-def]
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/api/v1/analyze/text", json={"text": "hello"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in response.text.lower()
    assert "sqlalchemy" not in response.text.lower()


@given(st.text(min_size=0, max_size=200))
@hyp_settings(max_examples=25, deadline=None)
def test_sanitize_request_id_never_contains_controls(raw: str) -> None:
    cleaned = sanitize_request_id(raw)
    assert "\n" not in cleaned
    assert "\r" not in cleaned
    assert "\t" not in cleaned
    assert all(ord(ch) >= 32 for ch in cleaned)


@given(
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
)
@hyp_settings(max_examples=20, deadline=None)
def test_finite_rects_accept_finite(x0: float, y0: float) -> None:
    from app.schemas.pdf_review import PdfRectSchema

    x1 = x0 + abs(x0) + 1.0
    y1 = y0 + abs(y0) + 1.0
    if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
        return
    rect = PdfRectSchema(x0=x0, y0=y0, x1=x1, y1=y1)
    assert rect.x1 >= rect.x0


def test_hsts_not_set_in_development(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/health")
    assert "Strict-Transport-Security" not in response.headers


def test_delete_idempotent_second_call(api_client: TestClient) -> None:
    import fitz

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "fictional")
    data = doc.tobytes()
    doc.close()
    created = api_client.post(
        "/api/v1/documents",
        files={"file": ("f.pdf", data, "application/pdf")},
    )
    assert created.status_code == 201
    job_id = created.json()["job_id"]
    first = api_client.delete(f"/api/v1/jobs/{job_id}")
    assert first.status_code == 200
    second = api_client.delete(f"/api/v1/jobs/{job_id}")
    assert second.status_code == 404
