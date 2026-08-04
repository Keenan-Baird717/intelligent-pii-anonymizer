from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure upload settings are safe before app modules are imported in fixtures.
os.environ.setdefault("UPLOAD_CLEANUP_ENABLED", "false")
os.environ.setdefault("UPLOAD_CLEANUP_INTERVAL_SECONDS", "0")


@pytest.fixture
def temp_upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    upload_root = tmp_path / "pii-uploads"
    upload_root.mkdir(parents=True, exist_ok=True)
    from app.core.config import settings

    monkeypatch.setattr(settings, "temp_upload_dir", str(upload_root))
    monkeypatch.setattr(settings, "ocr_temp_dir", str(upload_root / "ocr-work"))
    monkeypatch.setattr(settings, "upload_cleanup_enabled", False)
    monkeypatch.setattr(settings, "upload_cleanup_interval_seconds", 0)
    return upload_root


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.db.base import Base
    from app.models import (  # noqa: F401 — register metadata
        detected_entity,
        generated_artifact,
        processing_job,
    )

    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch, temp_upload_dir: Path
) -> Generator[TestClient, None, None]:
    from app.recognizers import presidio_adapter

    class _FakeBundle:
        analyzer = None
        spacy_available = False

    monkeypatch.setattr(presidio_adapter, "get_nlp_bundle", lambda: _FakeBundle())
    monkeypatch.setattr(
        "app.processing.detection.pipeline.run_presidio_and_spacy",
        lambda text, language="en": [],
    )

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def api_client(
    monkeypatch: pytest.MonkeyPatch,
    temp_upload_dir: Path,
    db_session: Session,
) -> Generator[TestClient, None, None]:
    """TestClient with Presidio mocks, temp upload dir, and SQLite get_db override."""
    from app.recognizers import presidio_adapter

    class _FakeBundle:
        analyzer = None
        spacy_available = False

    monkeypatch.setattr(presidio_adapter, "get_nlp_bundle", lambda: _FakeBundle())
    monkeypatch.setattr(
        "app.processing.detection.pipeline.run_presidio_and_spacy",
        lambda text, language="en": [],
    )

    from app.db.session import get_db
    from app.main import app

    def _override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
