"""Phase 5 — 003_phase5_entities_artifacts

Revision ID: 003_phase5_entities_artifacts
Revises: 002_processing_jobs
Create Date: 2026-08-03

JobStatus remains a string column (native_enum=False); new status values need no DDL.

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003_phase5_entities_artifacts"
down_revision: str | None = "002_processing_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "detected_entities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("processing_job_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("detection_source", sa.String(length=64), nullable=False),
        sa.Column("recognizer_name", sa.String(length=128), nullable=False),
        sa.Column("checksum_valid", sa.Boolean(), nullable=True),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("rectangles_json", sa.Text(), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("anonymization_method", sa.String(length=32), nullable=False),
        sa.Column("manually_added", sa.Boolean(), nullable=False),
        sa.Column("edited", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["processing_job_id"], ["processing_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_detected_entities_processing_job_id",
        "detected_entities",
        ["processing_job_id"],
    )

    op.create_table(
        "generated_artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("processing_job_id", sa.UUID(), nullable=False),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("validated_extension", sa.String(length=16), nullable=False),
        sa.Column("validated_mime_type", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["processing_job_id"], ["processing_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_generated_artifacts_processing_job_id",
        "generated_artifacts",
        ["processing_job_id"],
    )
    op.create_index(
        "ix_generated_artifacts_expires_at",
        "generated_artifacts",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_generated_artifacts_expires_at", table_name="generated_artifacts")
    op.drop_index("ix_generated_artifacts_processing_job_id", table_name="generated_artifacts")
    op.drop_table("generated_artifacts")
    op.drop_index("ix_detected_entities_processing_job_id", table_name="detected_entities")
    op.drop_table("detected_entities")
