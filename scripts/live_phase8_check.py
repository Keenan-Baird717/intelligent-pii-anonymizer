"""Phase 8 live security smoke checks against the local Compose stack."""

from __future__ import annotations

import json
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8000"


def call(
    method: str,
    path: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    req = Request(BASE + path, data=data, headers=headers or {}, method=method)
    try:
        with urlopen(req, timeout=60) as resp:
            return resp.status, {k: v for k, v in resp.headers.items()}, resp.read()
    except HTTPError as exc:
        return exc.code, {k: v for k, v in exc.headers.items()}, exc.read()


def main() -> None:
    status, headers, body = call(
        "POST",
        "/api/v1/analyze/text",
        data=json.dumps(
            {"text": "Casey Okafor casey.okafor@example.test phone 902-555-0182"}
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    cache = headers.get("Cache-Control") or headers.get("cache-control")
    nosniff = headers.get("X-Content-Type-Options") or headers.get("x-content-type-options")
    print("analyze", status, cache, nosniff)
    print("detections", json.loads(body).get("detection_count"))

    status, _, body = call("GET", "/api/v1/health", headers={"Host": "evil.example"})
    print("bad_host", status, body[:80])

    # Client HTTP libraries reject newline request IDs before they reach the server;
    # server-side sanitization is covered by pytest. Use a path-separator payload here.
    status, headers, _ = call(
        "GET", "/api/v1/health", headers={"X-Request-ID": "abc/../injected"}
    )
    rid = headers.get("X-Request-ID") or headers.get("x-request-id")
    print("sanitized_rid", repr(rid))
    assert rid is not None and "/" not in rid and ".." not in rid

    _, headers, _ = call("GET", "/api/v1/health", headers={"Origin": "https://evil.example"})
    print("cors_evil", headers.get("Access-Control-Allow-Origin"))
    _, headers, _ = call("GET", "/api/v1/health", headers={"Origin": "http://localhost:3000"})
    print("cors_good", headers.get("Access-Control-Allow-Origin"))

    pe = bytes([0x4D, 0x5A]) + b"\x00" * 32
    boundary = "----bound" + uuid.uuid4().hex
    payload = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="evil.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode() + pe + f"\r\n--{boundary}--\r\n".encode()
    status, _, body = call(
        "POST",
        "/api/v1/documents",
        data=payload,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    print("pe_upload", status, body[:160])

    # Cross-job artifact rejection with two PDFs if available via PyMuPDF.
    try:
        import fitz
    except ImportError:
        print("cross_job skipped (no fitz on host)")
        return

    def pdf_bytes() -> bytes:
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Alex Rivera fictional@example.com")
        data = doc.tobytes()
        doc.close()
        return data

    def upload_pdf(name: str) -> str:
        data = pdf_bytes()
        boundary = "----up" + uuid.uuid4().hex
        payload = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
        status, _, body = call(
            "POST",
            "/api/v1/documents",
            data=payload,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        assert status == 201, body
        return json.loads(body)["job_id"]

    job_a = upload_pdf("a.pdf")
    job_b = upload_pdf("b.pdf")
    fake = "00000000-0000-4000-8000-000000000001"
    status, _, _ = call("GET", f"/api/v1/jobs/{job_b}/artifacts/{fake}")
    print("cross_job_artifact", status)
    call("DELETE", f"/api/v1/jobs/{job_a}")
    call("DELETE", f"/api/v1/jobs/{job_b}")
    status, _, _ = call("GET", f"/api/v1/jobs/{job_a}")
    print("after_delete", status)


if __name__ == "__main__":
    main()
