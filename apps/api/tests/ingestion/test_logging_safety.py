"""Safe logging assertions for upload paths."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from app.core.errors import AppError
from app.services.ingestion.upload import ingest_upload
from tests.helpers.fictional_files import make_fictional_pdf_bytes

FICTIONAL_FILENAME = "CaseyOkafor-fictional-secret.pdf"
SECRET_MARKER = "UNIQUE_FICTIONAL_SECRET_PAYLOAD_XYZ"


class _CapturingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def _capture(self, event: str, **kwargs: object) -> None:
        self.events.append((event, dict(kwargs)))

    def info(self, event: str, **kwargs: object) -> None:
        self._capture(event, **kwargs)

    def error(self, event: str, **kwargs: object) -> None:
        self._capture(event, **kwargs)

    def warning(self, event: str, **kwargs: object) -> None:
        self._capture(event, **kwargs)

    def debug(self, event: str, **kwargs: object) -> None:
        self._capture(event, **kwargs)


def test_upload_logs_exclude_filename_and_contents(
    db_session: Session,
    temp_upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = _CapturingLogger()
    monkeypatch.setattr("app.services.ingestion.upload.logger", logger)

    ingest_upload(
        db_session,
        UploadFile(
            filename=FICTIONAL_FILENAME,
            file=BytesIO(make_fictional_pdf_bytes(text=SECRET_MARKER)),
            headers=Headers({"content-type": "application/pdf"}),
        ),
        root=temp_upload_dir,
    )

    blob = repr(logger.events)
    assert "CaseyOkafor" not in blob
    assert FICTIONAL_FILENAME not in blob
    assert SECRET_MARKER not in blob
    assert str(temp_upload_dir) not in blob
    assert any(event == "document_upload_success" for event, _ in logger.events)


def test_failed_upload_logs_exclude_filename_and_contents(
    db_session: Session,
    temp_upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload_logger = _CapturingLogger()
    pdf_logger = _CapturingLogger()
    monkeypatch.setattr("app.services.ingestion.upload.logger", upload_logger)
    monkeypatch.setattr("app.services.ingestion.pdf_validation.logger", pdf_logger)

    with pytest.raises(AppError) as exc:
        ingest_upload(
            db_session,
            UploadFile(
                filename=FICTIONAL_FILENAME,
                file=BytesIO(b"%PDF-1.4\nbogus-body-SECRET"),
                headers=Headers({"content-type": "application/pdf"}),
            ),
            root=temp_upload_dir,
        )
    assert exc.value.code == "CORRUPT_PDF"

    blob = repr(upload_logger.events) + repr(pdf_logger.events)
    assert FICTIONAL_FILENAME not in blob
    assert "CaseyOkafor" not in blob
    assert "bogus-body-SECRET" not in blob
