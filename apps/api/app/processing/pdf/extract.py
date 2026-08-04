from __future__ import annotations

from pathlib import Path

import fitz

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.processing.pdf.classify import count_meaningful_chars, is_scanned_like
from app.processing.pdf.constants import PAGE_SEPARATOR
from app.processing.pdf.types import BBox, ExtractedDocument, ExtractedPage, PositionedSpan

logger = get_logger(__name__)


def extract_document(path: Path, *, raise_on_scanned: bool = True) -> ExtractedDocument:
    """Extract text and word-level coordinates from a text-based PDF.

    Never logs extracted text. When raise_on_scanned is True (Phase 5 default),
    raises OCR_REQUIRED for scanned-like documents. Phase 6 analysis passes
    raise_on_scanned=False and runs OCR on pages_needing_ocr instead.
    """
    document = fitz.open(path)
    try:
        pages: list[ExtractedPage] = []
        all_spans: list[PositionedSpan] = []
        page_texts: list[str] = []
        global_offset = 0

        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            page_number = page_index + 1  # 1-based
            width = float(page.rect.width)
            height = float(page.rect.height)
            words = page.get_text("words")  # x0, y0, x1, y1, word, block, line, word_no
            words = sorted(words, key=lambda w: (w[5], w[6], w[7], w[0], w[1]))

            pieces: list[str] = []
            page_spans: list[PositionedSpan] = []
            local_offset = 0
            prev_block: int | None = None
            prev_line: int | None = None

            for word in words:
                x0, y0, x1, y1, raw, block_no, line_no, _word_no = word
                token = str(raw)
                if not token:
                    continue
                if prev_block is not None and prev_line is not None:
                    if line_no != prev_line or block_no != prev_block:
                        pieces.append("\n")
                        local_offset += 1
                    else:
                        pieces.append(" ")
                        local_offset += 1
                start_local = local_offset
                pieces.append(token)
                local_offset += len(token)
                end_local = local_offset
                bbox = BBox(x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1)).clip(
                    width, height
                )
                span = PositionedSpan(
                    page_number=page_number,
                    start=global_offset + start_local,
                    end=global_offset + end_local,
                    text_length=len(token),
                    bbox=bbox,
                    block_no=int(block_no),
                    line_no=int(line_no),
                )
                page_spans.append(span)
                all_spans.append(span)
                prev_block = int(block_no)
                prev_line = int(line_no)

            page_text = "".join(pieces)
            has_images = bool(page.get_images(full=True))
            has_text = count_meaningful_chars(page_text) > 0
            extracted_page = ExtractedPage(
                page_number=page_number,
                width=width,
                height=height,
                text=page_text,
                spans=page_spans,
                has_text=has_text,
                has_images=has_images,
            )
            pages.append(extracted_page)
            page_texts.append(page_text)
            global_offset += len(page_text)
            if page_index < document.page_count - 1:
                global_offset += len(PAGE_SEPARATOR)

        full_text = PAGE_SEPARATOR.join(page_texts)
        pages_with_text = [p.page_number for p in pages if p.has_text]
        pages_needing_ocr = [p.page_number for p in pages if (not p.has_text) and p.has_images]

        result = ExtractedDocument(
            pages=pages,
            full_text=full_text,
            page_separator=PAGE_SEPARATOR,
            pages_with_text=pages_with_text,
            pages_needing_ocr=pages_needing_ocr,
        )

        if raise_on_scanned and is_scanned_like(result, min_chars=settings.min_pdf_text_chars):
            raise AppError(
                code="OCR_REQUIRED",
                message=(
                    "This PDF appears to be image-based and requires OCR, "
                    "which is not available yet."
                ),
                status_code=422,
            )

        logger.info(
            "pdf_extraction_completed",
            page_count=len(pages),
            pages_with_text=len(pages_with_text),
            pages_needing_ocr=len(pages_needing_ocr),
            text_length=len(full_text),
            status="success",
        )
        return result
    finally:
        document.close()
