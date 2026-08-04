"""Live Phase 7 smoke check against local Docker API."""

from __future__ import annotations

import json

import fitz
import httpx

c = httpx.Client(base_url="http://localhost:8000", timeout=60)
h = c.get("/api/v1/health")
print("health", h.status_code, h.json())

doc = fitz.open()
page = doc.new_page()
page.insert_text(
    (72, 72),
    "Contact Alice at fictional.user@example.com CONTROLWORD filler words enough",
)
data = doc.tobytes()
doc.close()

up = c.post("/api/v1/documents", files={"file": ("memo.pdf", data, "application/pdf")})
print("upload", up.status_code)
jid = up.json()["job_id"]
an = c.post(f"/api/v1/jobs/{jid}/analyze")
print("analyze", an.status_code, an.json().get("detection_count"))
for entity in an.json().get("entities", []):
    if entity.get("entity_type") == "EMAIL_ADDRESS":
        c.patch(
            f"/api/v1/jobs/{jid}/entities/{entity['id']}",
            json={"review_status": "accepted"},
        )
anon = c.post(f"/api/v1/jobs/{jid}/anonymize", json={"default_method": "redaction"})
print("anon", anon.status_code, anon.json().get("status"))
res = c.get(f"/api/v1/jobs/{jid}/result")
body = res.json()
print("result", res.status_code, body.get("verification_status"))
assert "storage_key" not in json.dumps(body)
assert "fictional.user" not in res.text
aud = c.get(f"/api/v1/jobs/{jid}/audit-report")
print(
    "audit",
    aud.status_code,
    aud.headers.get("content-disposition"),
    aud.headers.get("cache-control"),
)
assert aud.json()["schema_version"] == "1.0"
assert "fictional.user" not in aud.text
print("delete", c.delete(f"/api/v1/jobs/{jid}").status_code)
print(
    "after",
    c.get(f"/api/v1/jobs/{jid}/result").status_code,
    c.get(f"/api/v1/jobs/{jid}/audit-report").status_code,
)
print("ok")
