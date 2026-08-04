import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    unhandled_error_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestIdMiddleware, SecurityHeadersMiddleware

configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    from app.core.config import settings as app_settings
    from app.recognizers.presidio_adapter import get_nlp_bundle
    from app.services.ingestion.cleanup import cleanup_loop, startup_reconciliation
    from app.services.ingestion.storage import ensure_upload_directory

    ensure_upload_directory()
    try:
        from app.processing.ocr.workfiles import ensure_ocr_work_directory

        ensure_ocr_work_directory()
    except Exception:
        logger.error("ocr_workdir_init_failure", error_code="TEMPORARY_WORK_FILE_FAILURE")

    if app_settings.ocr_enabled:
        try:
            from app.processing.ocr.adapter import ensure_tesseract_available

            ensure_tesseract_available()
        except Exception:
            logger.error("ocr_engine_unavailable", error_code="OCR_ENGINE_UNAVAILABLE")
            if app_settings.environment != "development":
                raise

    try:
        startup_reconciliation()
    except Exception:
        logger.error("startup_reconciliation_failure", error_code="STORAGE_FAILURE")

    get_nlp_bundle()
    logger.info(
        "api_started",
        environment=settings.environment,
        spacy_model=settings.spacy_model,
        max_upload_bytes=settings.max_upload_bytes,
        upload_ttl_minutes=settings.upload_ttl_minutes,
        ocr_enabled=settings.ocr_enabled,
        ocr_max_pages=settings.effective_ocr_max_pages,
        max_concurrent_ocr_jobs=settings.max_concurrent_ocr_jobs,
        max_concurrent_document_jobs=settings.max_concurrent_document_jobs,
        cors_origin_count=len(settings.cors_origin_list),
    )

    stop_event = asyncio.Event()
    cleanup_task = asyncio.create_task(cleanup_loop(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        logger.info("api_stopped")


app = FastAPI(
    title="Intelligent PII Anonymization Platform API",
    version="0.1.0",
    docs_url="/docs" if settings.environment == "development" else None,
    redoc_url=None,
    lifespan=lifespan,
)

# Last added = outermost. TrustedHost should reject bad Host early.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID", "Accept"],
    expose_headers=["X-Request-ID", "Retry-After"],
    max_age=600,
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_host_list,
)

app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unhandled_error_handler)

app.include_router(api_v1_router, prefix="/api/v1")
