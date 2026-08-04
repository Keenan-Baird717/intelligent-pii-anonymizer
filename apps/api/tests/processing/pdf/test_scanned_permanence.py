"""Phase 6 permanence, rotation, and transform tests for scanned PDF redaction."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from app.core.errors import AppError
from app.processing.ocr.models import PixelBBox, RenderTransform
from app.processing.ocr.transforms import pdf_to_pixel_bbox, pixel_to_pdf_bbox
from app.processing.pdf.redact import (
    apply_redactions,
    extract_page_image_bytes,
    page_annotation_count,
    page_has_recoverable_source_image,
)
from app.processing.pdf.types import BBox
from app.processing.pdf.verify import verify_scanned_page_redaction
from tests.helpers.fictional_files import (
    make_pdf_with_text,
    make_scanned_pdf_bytes,
    write_bytes,
)

SECRET = "SECRETTOKENXYZ"
CONTROL = "CONTROLWORD"


def _transform(
    *,
    rotation: int = 0,
    page_width: float = 100,
    page_height: float = 200,
    dpi: int = 72,
) -> RenderTransform:
    scale = dpi / 72.0
    if rotation % 180 == 0:
        pw, ph = page_width, page_height
    else:
        # Pixmap for rotated pages uses visual dimensions.
        pw, ph = page_width, page_height
    return RenderTransform(
        page_number=1,
        dpi=dpi,
        page_width=page_width,
        page_height=page_height,
        pixel_width=int(pw * scale),
        pixel_height=int(ph * scale),
        rotation=rotation,
        scale_x=scale,
        scale_y=scale,
    )


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_pdf_pixel_roundtrip_via_pymupdf_matrix(rotation: int) -> None:
    """Annotation-space rectangles round-trip through rotation_matrix * zoom."""
    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=300)
        page.set_rotation(rotation)
        zoom = 2.0
        mat = page.rotation_matrix * fitz.Matrix(zoom, zoom)
        original = fitz.Rect(20, 30, 80, 90)
        mapped = (original * mat).normalize()
        restored = (mapped * ~mat).normalize()
        assert abs(restored.x0 - original.x0) < 1.0
        assert abs(restored.y0 - original.y0) < 1.0
        assert abs(restored.x1 - original.x1) < 1.0
        assert abs(restored.y1 - original.y1) < 1.0
    finally:
        doc.close()


def test_pixel_to_pdf_rotation_0_still_stable() -> None:
    transform = _transform(rotation=0, page_width=100, page_height=200, dpi=72)
    box = PixelBBox(10, 20, 30, 40)
    x0, y0, x1, y1 = pixel_to_pdf_bbox(transform, box)
    restored = pdf_to_pixel_bbox(transform, x0, y0, x1, y1)
    assert abs(restored.x0 - box.x0) < 1.0
    assert abs(restored.y0 - box.y0) < 1.0


def test_raster_redaction_removes_sensitive_pixels(tmp_path: Path) -> None:
    source = write_bytes(
        tmp_path / "scan.pdf",
        make_scanned_pdf_bytes([f"Hide {SECRET} now", "KeepVisibleToken here", f"{CONTROL} keep"]),
    )
    source_bytes = source.read_bytes()
    output = tmp_path / "out.pdf"

    # Cover most of the page so stretched scanned text is fully removed; leave a
    # bottom strip for CONTROLWORD OCR verification.
    secret_box = BBox(x0=10, y0=10, x1=602, y1=620)
    apply_redactions(source, output, [(1, secret_box)], pixel_redact_pages={1}, dpi=150)

    assert source.read_bytes() == source_bytes
    assert output.exists()
    document = fitz.open(output)
    try:
        assert document.page_count == 1
        page = document.load_page(0)
        assert abs(page.rect.width - 612) < 1
        assert abs(page.rect.height - 792) < 1
        assert page.get_text("text").strip() == ""
        assert page_annotation_count(output, 1) == 0
        assert page_has_recoverable_source_image(output, 1) is False
        images = extract_page_image_bytes(output, 1)
        assert len(images) == 1
        # Original source image bytes must not be recoverable unchanged.
        assert source_bytes not in images[0]
        assert SECRET.encode() not in images[0]
    finally:
        document.close()

    verify_scanned_page_redaction(
        output,
        page_number=1,
        rectangles=[secret_box],
        forbidden_substrings=[SECRET],
        required_substrings=[CONTROL],
        dpi=150,
        source_path=source,
    )


def test_raster_redaction_failure_deletes_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_bytes(tmp_path / "scan.pdf", make_scanned_pdf_bytes([f"{SECRET} {CONTROL}"]))
    output = tmp_path / "out.pdf"

    def boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("simulated failure")

    monkeypatch.setattr("app.processing.pdf.redact.fitz.Page.get_pixmap", boom)
    with pytest.raises(AppError) as exc_info:
        apply_redactions(
            source,
            output,
            [(1, BBox(x0=10, y0=10, x1=200, y1=80))],
            pixel_redact_pages={1},
            dpi=120,
        )
    assert exc_info.value.code == "REDACTION_FAILED"
    assert not output.exists()
    assert not output.with_suffix(".writing.pdf").exists()


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_rotated_scanned_page_redaction(tmp_path: Path, rotation: int) -> None:
    source = write_bytes(
        tmp_path / f"rot{rotation}.pdf",
        make_scanned_pdf_bytes(
            [f"Redact {SECRET} please", "NeighborToken stays", f"{CONTROL} visible"],
            rotation=rotation,
        ),
    )
    source_doc = fitz.open(source)
    try:
        src_page = source_doc.load_page(0)
        src_w, src_h = float(src_page.rect.width), float(src_page.rect.height)
        # Annotation-space band covering the upper portion of the mediabox.
        mb = src_page.mediabox
        box = BBox(
            x0=float(mb.x0) + 10,
            y0=float(mb.y0) + 10,
            x1=float(mb.x1) - 10,
            y1=float(mb.y0) + float(mb.height) * 0.78,
        )
    finally:
        source_doc.close()

    output = tmp_path / f"out{rotation}.pdf"
    apply_redactions(source, output, [(1, box)], pixel_redact_pages={1}, dpi=140)

    out_doc = fitz.open(output)
    try:
        assert out_doc.page_count == 1
        page = out_doc.load_page(0)
        assert abs(float(page.rect.width) - src_w) < 1.5
        assert abs(float(page.rect.height) - src_h) < 1.5
        assert page_annotation_count(output, 1) == 0
    finally:
        out_doc.close()

    verify_scanned_page_redaction(
        output,
        page_number=1,
        rectangles=[box],
        forbidden_substrings=[SECRET],
        required_substrings=[CONTROL],
        dpi=140,
        source_path=source,
    )


def test_cropbox_and_nondefault_dimensions(tmp_path: Path) -> None:
    source = write_bytes(
        tmp_path / "crop.pdf",
        make_scanned_pdf_bytes(
            [f"{SECRET} hide", f"{CONTROL} crop"],
            page_width=500,
            page_height=700,
            crop=(10, 10, 490, 690),
        ),
    )
    output = tmp_path / "out.pdf"
    box = BBox(x0=15, y0=15, x1=485, y1=540)
    apply_redactions(source, output, [(1, box)], pixel_redact_pages={1}, dpi=120)
    doc = fitz.open(output)
    try:
        page = doc.load_page(0)
        assert page.rect.width > 0
        assert page.rect.height > 0
    finally:
        doc.close()
    verify_scanned_page_redaction(
        output,
        page_number=1,
        rectangles=[box],
        forbidden_substrings=[SECRET],
        required_substrings=[CONTROL],
        dpi=120,
        source_path=source,
    )


def test_multiple_rectangles_and_boundary_clip(tmp_path: Path) -> None:
    source = write_bytes(
        tmp_path / "multi.pdf",
        make_scanned_pdf_bytes(
            [f"ONE {SECRET} TWO", "KeepVisibleToken end", f"{CONTROL} multi"],
            page_width=612,
            page_height=792,
        ),
    )
    output = tmp_path / "out.pdf"
    boxes = [
        BBox(x0=-10, y0=10, x1=320, y1=620),  # clipped at left boundary
        BBox(x0=280, y0=10, x1=700, y1=620),  # clipped at right boundary
    ]
    apply_redactions(source, output, [(1, b) for b in boxes], pixel_redact_pages={1}, dpi=130)
    assert page_annotation_count(output, 1) == 0
    verify_scanned_page_redaction(
        output,
        page_number=1,
        rectangles=boxes,
        forbidden_substrings=[SECRET],
        required_substrings=[CONTROL],
        dpi=130,
        source_path=source,
    )


def test_multipage_scanned_redaction(tmp_path: Path) -> None:
    import fitz as fm

    doc = fm.open()
    try:
        for index, secret in enumerate(["ALPHASECRET", "BETASECRET"], start=1):
            png = __import__(
                "tests.helpers.fictional_files", fromlist=["_render_fictional_text_png"]
            )._render_fictional_text_png([f"Hide {secret}", "KeepVisible", f"{CONTROL}{index}"])
            page = doc.new_page()
            page.insert_image(page.rect, stream=png)
        data = doc.tobytes()
    finally:
        doc.close()

    source = write_bytes(tmp_path / "multi-page.pdf", data)
    output = tmp_path / "out.pdf"
    boxes = [
        (1, BBox(x0=10, y0=10, x1=602, y1=620)),
        (2, BBox(x0=10, y0=10, x1=602, y1=620)),
    ]
    apply_redactions(source, output, boxes, pixel_redact_pages={1, 2}, dpi=130)
    out = fitz.open(output)
    try:
        assert out.page_count == 2
    finally:
        out.close()
    for page_number, box in boxes:
        verify_scanned_page_redaction(
            output,
            page_number=page_number,
            rectangles=[box],
            forbidden_substrings=["ALPHASECRET" if page_number == 1 else "BETASECRET"],
            required_substrings=[f"{CONTROL}{page_number}"],
            dpi=130,
            source_path=source,
        )


def test_text_page_still_uses_true_redaction(tmp_path: Path) -> None:
    source = write_bytes(
        tmp_path / "text.pdf",
        make_pdf_with_text([f"{SECRET} keep {CONTROL} visible words"]),
    )
    source_bytes = source.read_bytes()
    output = tmp_path / "out.pdf"
    # Approximate first-word region; use extract to get exact rect without string search.
    doc = fitz.open(source)
    try:
        words = doc.load_page(0).get_text("words")
        secret_word = next(w for w in words if w[4] == SECRET)
        box = BBox(x0=secret_word[0], y0=secret_word[1], x1=secret_word[2], y1=secret_word[3])
    finally:
        doc.close()

    apply_redactions(source, output, [(1, box)], pixel_redact_pages=set(), dpi=150)
    assert source.read_bytes() == source_bytes
    text = fitz.open(output).get_page_text(0)
    assert SECRET not in text
    assert CONTROL in text
