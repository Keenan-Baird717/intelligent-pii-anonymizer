"""Phase 6 — 004_phase6_ocr_metadata

Revision ID: 004_phase6_ocr_metadata
Revises: 003_phase5_entities_artifacts
Create Date: 2026-08-03

Adds safe OCR/review metadata only. No OCR text, detected values, or paths.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004_phase6_ocr_metadata"
down_revision: str | None = "003_phase5_entities_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "detected_entities",
        sa.Column(
            "source_kind",
            sa.String(length=32),
            nullable=False,
            server_default="embedded_text",
        ),
    )
    op.add_column(
        "detected_entities",
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "detected_entities",
        sa.Column(
            "low_ocr_confidence",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "detected_entities",
        sa.Column(
            "preprocessing_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "detected_entities",
        sa.Column(
            "coordinate_space",
            sa.String(length=32),
            nullable=False,
            server_default="pdf_points",
        ),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("analysis_coverage_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("processing_jobs", "analysis_coverage_json")
    op.drop_column("detected_entities", "coordinate_space")
    op.drop_column("detected_entities", "preprocessing_used")
    op.drop_column("detected_entities", "low_ocr_confidence")
    op.drop_column("detected_entities", "ocr_confidence")
    op.drop_column("detected_entities", "source_kind")
