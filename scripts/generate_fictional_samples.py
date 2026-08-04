#!/usr/bin/env python3
"""Generate synthetic demo samples under samples/fictional/.

All content is fictional. No network access. No real PII.

Regenerate (from repository root, with API deps available)::

    python scripts/generate_fictional_samples.py

Or via Docker::

    docker compose exec api python -c "print('use host script with apps/api on PYTHONPATH')"

The script refuses to write outside samples/fictional and only overwrites
known sample filenames listed in ALLOWED_OUTPUTS.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = (ROOT / "samples" / "fictional").resolve()
API_ROOT = ROOT / "apps" / "api"

sys.path.insert(0, str(API_ROOT))

from tests.helpers.fictional_files import (  # noqa: E402
    make_mixed_pdf_bytes,
    make_pdf_with_text,
    make_scanned_pdf_bytes,
)

ALLOWED_OUTPUTS = frozenset(
    {
        "README.md",
        "fictional-text-example.txt",
        "fictional-text-document.pdf",
        "fictional-scanned-document.pdf",
        "fictional-mixed-document.pdf",
        "fictional-id-card.png",
        "fictional-contact-sheet.jpg",
        # Keep Phase 5/8 Playwright fixtures regenerable from the dedicated script;
        # this generator does not touch those filenames.
    }
)

FICTIONAL_TEXT = """\
SYNTHETIC DEMO SAMPLE — NOT REAL PERSONAL DATA
==============================================

Northstar Demo Clinic
Patient intake (fictional)

Name: Casey Okafor
Email: casey.okafor@example.com
Phone: 902-555-0182
Postal code: B3H 1Y2
Organization: Harbour Example Bank
Contact: Jordan Example <jordan.example@example.com>
Alternate: Avery Fiction at avery.fiction@example.org

Notes: This file is generated for portfolio demonstrations only.
Do not treat any value as a real identifier.
"""


def _assert_safe_path(path: Path) -> Path:
    resolved = path.resolve()
    if not str(resolved).startswith(str(OUT_DIR)):
        raise SystemExit(f"Refusing to write outside samples/fictional: {resolved}")
    if resolved.name not in ALLOWED_OUTPUTS:
        raise SystemExit(f"Refusing to write unexpected filename: {resolved.name}")
    return resolved


def _write_bytes(name: str, data: bytes) -> Path:
    path = _assert_safe_path(OUT_DIR / name)
    path.write_bytes(data)
    return path


def _write_text(name: str, text: str) -> Path:
    path = _assert_safe_path(OUT_DIR / name)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for candidate in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _make_id_card_png() -> bytes:
    """Clearly labeled fictional ID-card style image (no EXIF/GPS)."""
    image = Image.new("RGB", (720, 420), color=(248, 250, 252))
    draw = ImageDraw.Draw(image)
    title = _load_font(28)
    body = _load_font(22)
    small = _load_font(16)

    draw.rectangle((24, 24, 696, 396), outline=(15, 118, 110), width=3)
    draw.rectangle((24, 24, 696, 90), fill=(15, 118, 110))
    draw.text((40, 42), "FICTIONAL DEMO ID — NOT A REAL DOCUMENT", fill=(255, 255, 255), font=title)
    draw.text((40, 120), "Name: Casey Okafor", fill=(15, 23, 42), font=body)
    draw.text((40, 160), "Org: Northstar Demo Clinic", fill=(15, 23, 42), font=body)
    draw.text((40, 200), "Email: casey.okafor@example.com", fill=(15, 23, 42), font=body)
    draw.text((40, 240), "Phone: 902-555-0182", fill=(15, 23, 42), font=body)
    draw.text((40, 280), "Postal: B3H 1Y2", fill=(15, 23, 42), font=body)
    draw.text(
        (40, 340),
        "Synthetic sample for OCR redaction demos. No real person.",
        fill=(71, 85, 105),
        font=small,
    )

    from io import BytesIO

    buffer = BytesIO()
    # Explicitly omit EXIF; Pillow JPEG/PNG saves without GPS by default.
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _make_contact_sheet_jpg() -> bytes:
    """Fictional contact sheet JPEG without EXIF metadata."""
    image = Image.new("RGB", (900, 520), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    title = _load_font(26)
    body = _load_font(22)
    draw.rectangle((20, 20, 880, 500), outline=(15, 23, 42), width=2)
    draw.text((40, 40), "Harbour Example Bank — FICTIONAL CONTACT SHEET", fill=(15, 23, 42), font=title)
    lines = [
        "Jordan Example  jordan.example@example.com  902-555-0147",
        "Avery Fiction   avery.fiction@example.org  416-555-0133",
        "Casey Okafor    casey.okafor@example.com   B3H 1Y2",
        "CONTROLWORD keep-visible for OCR demos",
    ]
    y = 110
    for line in lines:
        draw.text((40, y), line, fill=(15, 23, 42), font=body)
        y += 50
    draw.text((40, 430), "SYNTHETIC — reserved example.com / 555 numbers only", fill=(100, 116, 139), font=body)

    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92, optimize=True)
    return buffer.getvalue()


def _write_readme() -> Path:
    content = """# Fictional sample files

All files in this directory are **synthetic**. They use obviously fictional names,
`example.com` / `example.org` addresses, and reserved `555` telephone numbers.

| File | Purpose |
|------|---------|
| `fictional-text-example.txt` | Pasted-text / README demo copy |
| `fictional-text-document.pdf` | Embedded-text PDF redaction demo |
| `fictional-scanned-document.pdf` | Image-only scanned PDF + OCR demo |
| `fictional-mixed-document.pdf` | Mixed embedded + scanned pages |
| `fictional-id-card.png` | PNG OCR / image redaction demo |
| `fictional-contact-sheet.jpg` | JPEG OCR / image redaction demo |

Regenerate with:

```bash
python scripts/generate_fictional_samples.py
```

Do not add real documents, real personal data, EXIF GPS, or production uploads here.
"""
    return _write_text("README.md", content)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not OUT_DIR.is_dir():
        raise SystemExit(f"Output directory missing: {OUT_DIR}")

    written: list[Path] = []
    written.append(_write_readme())
    written.append(_write_text("fictional-text-example.txt", FICTIONAL_TEXT))

    text_pdf = make_pdf_with_text(
        [
            "SYNTHETIC DEMO — Northstar Demo Clinic intake. "
            "Casey Okafor casey.okafor@example.com phone 902-555-0182 "
            "postal B3H 1Y2 Harbour Example Bank filler words for extraction."
        ]
    )
    written.append(_write_bytes("fictional-text-document.pdf", text_pdf))

    scanned = make_scanned_pdf_bytes(
        [
            "SYNTHETIC SCANNED PAGE",
            "Contact Jordan Example at jordan.example@example.com",
            "Phone 902-555-0147 Harbour Example Bank",
            "CONTROLWORD keep visible",
        ]
    )
    written.append(_write_bytes("fictional-scanned-document.pdf", scanned))

    written.append(_write_bytes("fictional-mixed-document.pdf", make_mixed_pdf_bytes()))
    written.append(_write_bytes("fictional-id-card.png", _make_id_card_png()))
    written.append(_write_bytes("fictional-contact-sheet.jpg", _make_contact_sheet_jpg()))

    for path in written:
        print(f"Wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
