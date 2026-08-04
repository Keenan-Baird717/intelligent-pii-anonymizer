"""Focused OCR unit tests with mocked adapter (no document text logged)."""

from __future__ import annotations

from app.processing.ocr.adapter import RawOcrResult, RawOcrWord, parse_tsv
from app.processing.ocr.confidence import combine_confidence
from app.processing.ocr.index import build_ocr_text_index, map_ocr_offsets
from app.processing.ocr.models import PixelBBox, RenderTransform
from app.processing.ocr.transforms import pixel_to_pdf_bbox


def test_parse_tsv_filters_low_confidence() -> None:
    tsv = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t10\t10\t40\t12\t90\talpha\n"
        "5\t1\t1\t1\t1\t2\t60\t10\t40\t12\t10\tnoise\n"
    )
    words, _w, _h = parse_tsv(tsv, min_confidence=35)
    assert len(words) == 1
    assert words[0].text == "alpha"


def test_index_repeated_words_map_distinct_offsets() -> None:
    raw = RawOcrResult(
        words=[
            RawOcrWord("alpha", 10, 10, 40, 12, 90, 1, 1, 1),
            RawOcrWord("alpha", 10, 40, 40, 12, 88, 1, 2, 1),
        ],
        image_width=200,
        image_height=200,
    )
    index = build_ocr_text_index(raw)
    assert index.full_text.count("alpha") == 2
    first = map_ocr_offsets(index, 0, 5)
    second = map_ocr_offsets(
        index, index.full_text.rfind("alpha"), index.full_text.rfind("alpha") + 5
    )
    assert first.pixel_rectangles[0].y0 != second.pixel_rectangles[0].y0


def test_combine_confidence_keeps_detection_separate() -> None:
    combined = combine_confidence(
        detection_confidence=0.9,
        ocr_confidence=0.4,
        checksum_valid=True,
        low_ocr_confidence=True,
    )
    assert combined.detection_confidence == 0.9
    assert combined.ocr_confidence == 0.4
    assert combined.low_ocr_confidence is True


def test_checksum_invalid_not_promoted_by_high_ocr() -> None:
    combined = combine_confidence(
        detection_confidence=0.8,
        ocr_confidence=0.99,
        checksum_valid=False,
    )
    assert combined.final_confidence is not None
    assert combined.final_confidence <= 0.4


def test_pixel_to_pdf_rotation_0() -> None:
    transform = RenderTransform(
        page_number=1,
        dpi=72,
        page_width=100,
        page_height=200,
        pixel_width=100,
        pixel_height=200,
        rotation=0,
        scale_x=1.0,
        scale_y=1.0,
    )
    box = PixelBBox(10, 20, 30, 40)
    x0, y0, x1, y1 = pixel_to_pdf_bbox(transform, box)
    assert x0 == 10
    assert x1 == 30
    assert y1 > y0


def test_ocr_index_does_not_embed_paths_in_mapping() -> None:
    raw = RawOcrResult(
        words=[RawOcrWord("secret-value@example.com", 1, 1, 10, 10, 90, 1, 1, 1)],
        image_width=50,
        image_height=50,
    )
    index = build_ocr_text_index(raw)
    mapping = map_ocr_offsets(index, 0, len("secret-value@example.com"))
    assert mapping.pixel_rectangles
    # Mapping metadata must not include the sensitive string as a field value beyond offsets.
    assert "secret-value@example.com" not in repr(mapping.pixel_rectangles)
