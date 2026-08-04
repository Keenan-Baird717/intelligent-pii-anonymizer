from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.main import app
from tests.helpers.fictional_files import make_image_only_pdf, make_pdf_with_text

img = Image.new("RGB", (800, 200), "white")
draw = ImageDraw.Draw(img)
draw.text((20, 60), "Contact fictional.user@example.com phone 902-555-0182", fill="black")
buf = BytesIO()
img.save(buf, format="PNG")
png = buf.getvalue()

client = TestClient(app)

r = client.post(
    "/api/v1/documents",
    files={
        "file": (
            "t.pdf",
            make_pdf_with_text(
                ["Contact Alice at fictional.user@example.com enough filler words here"]
            ),
            "application/pdf",
        )
    },
)
print("upload_text_pdf", r.status_code)
jid = r.json()["job_id"]
a = client.post(f"/api/v1/jobs/{jid}/analyze")
print(
    "analyze_text_pdf",
    a.status_code,
    a.json().get("detection_count"),
    (a.json().get("coverage") or {}).get("fully_analyzed"),
)

r2 = client.post(
    "/api/v1/documents",
    files={"file": ("s.pdf", make_image_only_pdf(), "application/pdf")},
)
print("upload_scan", r2.status_code)
a2 = client.post(f"/api/v1/jobs/{r2.json()['job_id']}/analyze")
print("analyze_scan", a2.status_code, a2.json().get("error", a2.json().get("coverage")))

r3 = client.post("/api/v1/documents", files={"file": ("f.png", png, "image/png")})
print("upload_png", r3.status_code, r3.json().get("file_type"))
a3 = client.post(f"/api/v1/jobs/{r3.json()['job_id']}/analyze")
body = a3.json()
print(
    "analyze_png",
    a3.status_code,
    body.get("detection_count"),
    body.get("warning_code"),
    body.get("coverage"),
)
if a3.status_code == 200:
    ents = body.get("entities", [])
    print("sources", sorted({e.get("source_kind") for e in ents}))
    print("has_ocr_conf", any(e.get("ocr_confidence") is not None for e in ents))
    print("leak", "storage_key" in body, "/var/" in str(body))
