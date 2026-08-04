from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://pii:change_me_in_production@localhost:5432/pii_anonymizer"
    )
    api_host: str = "0.0.0.0"  # nosec B104 — container bind; Compose publishes 127.0.0.1 only
    api_port: int = 8000
    environment: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    allowed_hosts: str = "localhost,127.0.0.1,api,testserver"
    max_text_length: int = Field(default=50_000, ge=1, le=200_000)
    spacy_model: str = "en_core_web_sm"
    enable_hsts: bool = False
    debug: bool = False

    # Phase 4 — secure uploads
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    max_pdf_pages: int = Field(default=50, ge=1)
    max_image_pixels: int = Field(default=40_000_000, ge=1)
    upload_ttl_minutes: int = Field(default=60, ge=1)
    upload_cleanup_interval_seconds: int = Field(default=300, ge=0)
    upload_stream_chunk_bytes: int = Field(default=1024 * 1024, ge=1024)
    temp_upload_dir: str = "/tmp/pii-uploads"  # nosec B108 — overridden via TEMP_UPLOAD_DIR; Docker uses /var/pii-uploads
    upload_cleanup_enabled: bool = True

    # Phase 5 — text-based PDF processing
    min_pdf_text_chars: int = Field(default=20, ge=0)
    redaction_padding_pts: float = Field(default=1.0, ge=0.0)

    # Phase 6 — OCR and image processing
    ocr_enabled: bool = True
    ocr_language: str = "eng"
    ocr_timeout_seconds: int = Field(default=60, ge=1)
    ocr_render_dpi: int = Field(default=200, ge=72, le=300)
    ocr_min_word_confidence: int = Field(default=35, ge=0, le=100)
    ocr_low_confidence_threshold: int = Field(default=60, ge=0, le=100)
    ocr_max_pages: int = Field(default=20, ge=1)
    ocr_preprocessing_enabled: bool = True
    ocr_deskew_enabled: bool = True
    ocr_temp_dir: str = "/tmp/pii-uploads/ocr-work"  # nosec B108 — must resolve under TEMP_UPLOAD_DIR
    ocr_executable: str = "tesseract"

    # Phase 8 — API and resource limits (conservative MVP defaults)
    max_entities_per_job: int = Field(default=500, ge=1, le=5_000)
    max_rectangles_per_entity: int = Field(default=32, ge=1, le=256)
    max_manual_rectangles: int = Field(default=100, ge=1, le=1_000)
    max_custom_recognizers: int = Field(default=10, ge=0, le=50)
    max_regex_pattern_length: int = Field(default=200, ge=1, le=2_000)
    max_audit_warnings: int = Field(default=50, ge=1, le=500)
    max_concurrent_ocr_jobs: int = Field(default=2, ge=1, le=32)
    max_concurrent_document_jobs: int = Field(default=4, ge=1, le=64)
    max_concurrent_uploads: int = Field(default=4, ge=1, le=64)
    max_concurrent_redactions: int = Field(default=2, ge=1, le=32)
    custom_regex_timeout_seconds: float = Field(default=0.25, ge=0.05, le=5.0)
    max_request_id_length: int = Field(default=64, ge=8, le=128)
    concurrency_retry_after_seconds: int = Field(default=5, ge=1, le=120)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_host_list(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @property
    def temp_upload_path(self) -> Path:
        return Path(self.temp_upload_dir).resolve()

    @property
    def ocr_temp_path(self) -> Path:
        return Path(self.ocr_temp_dir).resolve()

    @property
    def effective_ocr_max_pages(self) -> int:
        return min(self.ocr_max_pages, self.max_pdf_pages)

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("CORS_ORIGINS must list at least one explicit origin.")
        if "*" in cleaned:
            raise ValueError("CORS_ORIGINS must not use wildcard origins.")
        origins = [origin.strip() for origin in cleaned.split(",") if origin.strip()]
        for origin in origins:
            if origin != "null" and not (
                origin.startswith("http://") or origin.startswith("https://")
            ):
                raise ValueError(f"CORS origin must be an absolute URL: {origin}")
        return cleaned

    @field_validator("allowed_hosts")
    @classmethod
    def validate_allowed_hosts(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("ALLOWED_HOSTS must list at least one host.")
        if "*" in cleaned:
            raise ValueError("ALLOWED_HOSTS must not use wildcard hosts for the MVP.")
        return cleaned

    @field_validator("temp_upload_dir")
    @classmethod
    def validate_temp_upload_dir(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("TEMP_UPLOAD_DIR must be a non-empty path.")
        return cleaned

    @field_validator("ocr_temp_dir")
    @classmethod
    def validate_ocr_temp_dir(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("OCR_TEMP_DIR must be a non-empty path.")
        if ".." in Path(cleaned).parts:
            raise ValueError("OCR_TEMP_DIR must not contain parent-directory segments.")
        return cleaned

    @field_validator("ocr_language")
    @classmethod
    def validate_ocr_language(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned != "eng":
            raise ValueError("OCR_LANGUAGE must be 'eng' for the MVP.")
        return cleaned

    @field_validator("ocr_executable")
    @classmethod
    def validate_ocr_executable(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("OCR_EXECUTABLE must be a non-empty path or command name.")
        if any(ch in cleaned for ch in ["|", ";", "&", "$", "`", "\n", "\r"]):
            raise ValueError("OCR_EXECUTABLE contains unsafe characters.")
        return cleaned

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        cleaned = value.strip().lower()
        allowed = {"development", "test", "production"}
        if cleaned not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of: {', '.join(sorted(allowed))}.")
        return cleaned

    @model_validator(mode="after")
    def validate_upload_limits(self) -> "Settings":
        if self.max_upload_bytes > 100 * 1024 * 1024:
            raise ValueError("MAX_UPLOAD_BYTES must not exceed 100 MiB for the MVP.")
        if self.upload_stream_chunk_bytes > self.max_upload_bytes:
            raise ValueError("UPLOAD_STREAM_CHUNK_BYTES must not exceed MAX_UPLOAD_BYTES.")
        if self.ocr_min_word_confidence > self.ocr_low_confidence_threshold:
            raise ValueError(
                "OCR_MIN_WORD_CONFIDENCE must not exceed OCR_LOW_CONFIDENCE_THRESHOLD."
            )
        if self.debug and self.is_production:
            raise ValueError("DEBUG must be disabled in production.")
        if self.enable_hsts and not self.is_production:
            # Allow configuration, but document that HSTS headers are only emitted in production.
            pass
        upload_root = self.temp_upload_path
        ocr_root = self.ocr_temp_path
        try:
            ocr_root.relative_to(upload_root)
        except ValueError as exc:
            raise ValueError("OCR_TEMP_DIR must resolve under TEMP_UPLOAD_DIR.") from exc
        if ocr_root == upload_root:
            raise ValueError("OCR_TEMP_DIR must be a subdirectory of TEMP_UPLOAD_DIR.")
        return self


settings = Settings()
