from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PdfValidationResult:
    page_count: int


def validate_pdf(path: Path, *, max_pages: int | None = None) -> PdfValidationResult:
    """Open a PDF only to validate structure, encryption, page count, and active content.

    This is defensive parsing, not complete malware detection.
    """
    limit = max_pages if max_pages is not None else settings.max_pdf_pages
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        logger.error("pdf_library_missing", error_code="STORAGE_FAILURE")
        raise AppError(
            code="STORAGE_FAILURE",
            message="Document validation is temporarily unavailable.",
            status_code=500,
        ) from exc

    document = None
    try:
        document = fitz.open(path)
        if document.is_encrypted:
            raise AppError(
                code="PASSWORD_PROTECTED_PDF",
                message="Password-protected PDFs are not accepted.",
                status_code=400,
            )
        page_count = document.page_count
        if page_count <= 0:
            raise AppError(
                code="EMPTY_PDF",
                message="The PDF contains no pages.",
                status_code=400,
            )
        if page_count > limit:
            raise AppError(
                code="PDF_PAGE_LIMIT_EXCEEDED",
                message="The PDF exceeds the maximum allowed page count.",
                status_code=400,
            )
        reject_active_pdf_content(document)
        return PdfValidationResult(page_count=page_count)
    except AppError:
        raise
    except Exception as exc:
        logger.error("corrupt_pdf", error_code="CORRUPT_PDF")
        raise AppError(
            code="CORRUPT_PDF",
            message="The PDF could not be validated.",
            status_code=400,
        ) from exc
    finally:
        if document is not None:
            try:
                document.close()
            except Exception:
                pass


def reject_active_pdf_content(document: object) -> None:
    """Reject PDFs with embedded files, JavaScript, launch/external actions, or rich media."""
    import fitz

    assert isinstance(document, fitz.Document)

    # Embedded files / collections.
    try:
        emb = document.embfile_count()
    except Exception:
        emb = 0
    if emb and emb > 0:
        logger.warning("pdf_embedded_file_rejected", error_code="EMBEDDED_FILE_REJECTED")
        raise AppError(
            code="EMBEDDED_FILE_REJECTED",
            message="PDFs with embedded files are not accepted.",
            status_code=400,
        )

    # Document-level JavaScript / open actions where exposed by PyMuPDF.
    try:
        js = document.get_js() if hasattr(document, "get_js") else None
        if js:
            logger.warning("pdf_javascript_rejected", error_code="ACTIVE_PDF_CONTENT_REJECTED")
            raise AppError(
                code="ACTIVE_PDF_CONTENT_REJECTED",
                message="PDFs with active content are not accepted.",
                status_code=400,
            )
    except AppError:
        raise
    except Exception:
        pass

    try:
        names = document.name_and_js if hasattr(document, "name_and_js") else None
        if names:
            logger.warning("pdf_named_js_rejected", error_code="ACTIVE_PDF_CONTENT_REJECTED")
            raise AppError(
                code="ACTIVE_PDF_CONTENT_REJECTED",
                message="PDFs with active content are not accepted.",
                status_code=400,
            )
    except AppError:
        raise
    except Exception:
        pass

    for page_index in range(document.page_count):
        page = document.load_page(page_index)
        try:
            annots = page.annots()
        except Exception:
            annots = None
        if not annots:
            continue
        for annot in annots:
            try:
                info = annot.info or {}
                subtype = (annot.type[1] if annot.type else "") or ""
                subtype_l = str(subtype).lower()
                if subtype_l in {
                    "fileattachment",
                    "sound",
                    "movie",
                    "screen",
                    "richmedia",
                    "launch",
                }:
                    logger.warning(
                        "pdf_unsafe_annot_rejected",
                        error_code="UNSAFE_PDF_ACTION_REJECTED",
                    )
                    raise AppError(
                        code="UNSAFE_PDF_ACTION_REJECTED",
                        message="PDFs with unsafe annotations or actions are not accepted.",
                        status_code=400,
                    )
                # Inspect action dictionaries when available.
                try:
                    raw = annot.get_pdf_dict() if hasattr(annot, "get_pdf_dict") else None
                except Exception:
                    raw = None
                raw_text = str(raw or "").lower() + str(info).lower()
                if any(
                    token in raw_text
                    for token in (
                        "/js",
                        "/javascript",
                        "/launch",
                        "/gotor",
                        "/importdata",
                        "/submitform",
                        "/richmedia",
                        "/embeddedfile",
                        "/filespec",
                    )
                ):
                    logger.warning(
                        "pdf_unsafe_action_rejected",
                        error_code="UNSAFE_PDF_ACTION_REJECTED",
                    )
                    raise AppError(
                        code="UNSAFE_PDF_ACTION_REJECTED",
                        message="PDFs with unsafe annotations or actions are not accepted.",
                        status_code=400,
                    )
            except AppError:
                raise
            except Exception:
                continue


def sanitize_pdf_document(document: object) -> None:
    """Best-effort sanitization of a generated PDF before publication.

    Clears metadata, removes embedded files / JS / attachments where PyMuPDF allows.
    """
    import fitz

    assert isinstance(document, fitz.Document)
    try:
        document.set_metadata(
            {
                "title": "",
                "author": "",
                "subject": "",
                "keywords": "",
                "creator": "",
                "producer": "",
                "creationDate": "",
                "modDate": "",
            }
        )
    except Exception:
        pass
    try:
        document.del_xml_metadata()
    except Exception:
        pass
    try:
        while document.embfile_count() > 0:
            document.embfile_del(0)
    except Exception:
        pass
    # Remove file-attachment / rich-media annotations from output pages.
    for page_index in range(document.page_count):
        page = document.load_page(page_index)
        try:
            annots = list(page.annots() or [])
        except Exception:
            annots = []
        for annot in annots:
            try:
                subtype = (annot.type[1] if annot.type else "") or ""
                if str(subtype).lower() in {
                    "fileattachment",
                    "sound",
                    "movie",
                    "screen",
                    "richmedia",
                    "link",
                    "popup",
                }:
                    page.delete_annot(annot)
            except Exception:
                continue
