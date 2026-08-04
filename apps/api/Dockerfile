# syntax=docker/dockerfile:1
FROM python:3.14-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    build-essential \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    gosu \
    && rm -rf /var/lib/apt/lists/* \
    && tesseract --version \
    && tesseract --list-langs | grep -q eng \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home /app --shell /usr/sbin/nologin app \
    && mkdir -p /var/pii-uploads /var/pii-uploads/ocr-work \
    && chown -R app:app /app /var/pii-uploads

COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install -e ".[dev]" \
    && python -m spacy download en_core_web_sm \
    && pip cache purge || true

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY tests ./tests
COPY docker-entrypoint.sh /docker-entrypoint.sh

RUN sed -i 's/\r$//' /docker-entrypoint.sh \
    && chmod +x /docker-entrypoint.sh \
    && chown -R app:app /app

# Entrypoint starts as root only long enough to fix upload volume ownership, then drops to app.
USER root
EXPOSE 8000
ENTRYPOINT ["/bin/sh", "/docker-entrypoint.sh"]
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

