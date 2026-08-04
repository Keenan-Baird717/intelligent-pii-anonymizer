"""Generate fictional PDF/PNG/JPEG fixtures for tests. Never use real documents or PII."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path


def make_fictional_pdf_bytes(*, pages: int = 1, text: str = "Fictional Acme Corp report") -> bytes:
    import fitz

    document = fitz.open()
    try:
        for index in range(pages):
            page = document.new_page()
            page.insert_text((72, 72), f"{text} — page {index + 1}")
        return document.tobytes()
    finally:
        document.close()


def make_pdf_with_text(pages: list[str]) -> bytes:
    """Build a multi-page PDF where each entry is the text drawn on that page."""
    import fitz

    if not pages:
        raise ValueError("pages must contain at least one page of text")

    document = fitz.open()
    try:
        for page_text in pages:
            page = document.new_page()
            # Insert near the top-left; keep content simple for stable word extraction.
            page.insert_text((72, 72), page_text)
        return document.tobytes()
    finally:
        document.close()


def make_pdf_with_repeated_token(
    *,
    token: str = "alpha",
    first_line: str | None = None,
    second_line: str | None = None,
) -> bytes:
    """PDF with the same token twice at different positions (different offsets/rects)."""
    import fitz

    line_one = first_line or f"prefix {token} middle"
    line_two = second_line or f"suffix {token} end"

    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), line_one)
        page.insert_text((72, 200), line_two)
        return document.tobytes()
    finally:
        document.close()


def make_image_only_pdf(*, width: int = 32, height: int = 24) -> bytes:
    """PDF page that contains only an embedded PNG image and no extractable text."""
    import fitz

    png = make_fictional_png_bytes(width=width, height=height, color=(10, 20, 30))
    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_image(fitz.Rect(50, 50, 250, 200), stream=png)
        return document.tobytes()
    finally:
        document.close()


def _render_fictional_text_png(
    lines: list[str],
    *,
    width: int = 900,
    height: int = 320,
    font_size: int = 28,
) -> bytes:
    """High-contrast PNG with large fictional text for reliable Tesseract OCR."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", font_size)
    except OSError:
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()
    y = 40
    for line in lines:
        draw.text((40, y), line, fill=(0, 0, 0), font=font)
        y += font_size + 18
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def make_scanned_pdf_bytes(
    lines: list[str] | None = None,
    *,
    rotation: int = 0,
    page_width: float = 612,
    page_height: float = 792,
    crop: tuple[float, float, float, float] | None = None,
) -> bytes:
    """Build an image-only scanned PDF containing OCR-readable fictional text."""
    import fitz

    text_lines = lines or [
        "CONTROLWORD keep visible",
        "Contact fictional.user@example.com today",
        "Phone 902-555-0182 for support",
    ]
    png = _render_fictional_text_png(text_lines)
    document = fitz.open()
    try:
        page = document.new_page(width=page_width, height=page_height)
        page.insert_image(page.rect, stream=png)
        if crop is not None:
            page.set_cropbox(fitz.Rect(*crop))
        if rotation:
            page.set_rotation(rotation % 360)
        return document.tobytes()
    finally:
        document.close()


def make_mixed_pdf_bytes() -> bytes:
    """Mixed fictional PDF: embedded text, scanned image, and text+image page."""
    import fitz

    document = fitz.open()
    try:
        # Page 1 — embedded text only
        page1 = document.new_page()
        page1.insert_text(
            (72, 72),
            "CONTROLWORD page one Contact Alice Example at text.user@example.com filler words",
        )
        # Page 2 — scanned image only
        png = _render_fictional_text_png(
            [
                "CONTROLWORD page two",
                "Email scan.user@example.com please",
                "KeepVisibleToken remains here",
            ]
        )
        page2 = document.new_page()
        page2.insert_image(page2.rect, stream=png)
        # Page 3 — embedded text + image (mixed)
        page3 = document.new_page()
        page3.insert_text(
            (72, 72),
            "CONTROLWORD page three embedded mixed.user@example.com enough words",
        )
        small = _render_fictional_text_png(
            ["IMAGESECRETTOKEN on mixed page"],
            width=600,
            height=180,
            font_size=26,
        )
        page3.insert_image(fitz.Rect(72, 200, 500, 360), stream=small)
        return document.tobytes()
    finally:
        document.close()


def make_ocr_png_bytes(
    lines: list[str] | None = None,
    *,
    width: int = 900,
    height: int = 320,
) -> bytes:
    return _render_fictional_text_png(
        lines
        or [
            "CONTROLWORD image keep",
            "Contact fictional.user@example.com please",
            "Phone 902-555-0182 remains",
        ],
        width=width,
        height=height,
    )


# Aliases used by earlier Phase 5 drafts / alternate call sites.
make_image_only_pdf_bytes = make_image_only_pdf


def make_multipage_repeated_text_pdf_bytes(
    *,
    page_texts: list[str] | None = None,
) -> bytes:
    """Create a multi-page PDF with known text for coordinate-mapping tests."""
    texts = page_texts or ["alpha alpha contact", "beta gamma alpha", "omega alpha end"]
    return make_pdf_with_text(texts)


def make_password_protected_pdf_bytes(
    *,
    user_password: str = "test-user-pw",
    owner_password: str = "test-owner-pw",
    text: str = "Fictional locked memo",
) -> bytes:
    import fitz

    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), text)
        buffer = BytesIO()
        document.save(
            buffer,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw=user_password,
            owner_pw=owner_password,
        )
        return buffer.getvalue()
    finally:
        document.close()


def make_fictional_png_bytes(
    *, width: int = 32, height: int = 24, color: tuple[int, int, int] = (10, 20, 30)
) -> bytes:
    from PIL import Image

    image = Image.new("RGB", (width, height), color=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def make_fictional_jpeg_bytes(
    *,
    width: int = 40,
    height: int = 30,
    color: tuple[int, int, int] = (200, 100, 50),
) -> bytes:
    from PIL import Image

    image = Image.new("RGB", (width, height), color=color)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def write_bytes(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def corrupt_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n% fictional corrupt payload\ntrailer\n%%EOF"


def corrupt_png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 32 + b"not-a-real-chunk"


def corrupt_jpeg_bytes() -> bytes:
    return b"\xff\xd8\xff\xe0" + b"\x00" * 16 + b"corrupt-jpeg-payload"


def pe_header_bytes() -> bytes:
    return b"MZ" + b"\x00" * 60 + b"fictional-pe"


def zip_header_bytes() -> bytes:
    return b"PK\x03\x04" + b"\x00" * 26 + b"fictional-zip"


def rar_header_bytes() -> bytes:
    return b"Rar!\x1a\x07\x00" + b"\x00" * 16


def seven_z_header_bytes() -> bytes:
    return b"7z\xbc\xaf\x27\x1c" + b"\x00" * 16


def gzip_header_bytes() -> bytes:
    return b"\x1f\x8b" + b"\x08" + b"\x00" * 16


def elf_header_bytes() -> bytes:
    return b"\x7fELF" + b"\x00" * 16
