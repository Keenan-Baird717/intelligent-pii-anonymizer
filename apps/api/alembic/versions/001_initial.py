"""Initial schema placeholder.

Domain tables (ProcessingJob, DetectedEntity, etc.) are added in Phase 3.

Revision ID: 001_initial
Revises:
Create Date: 2026-08-03

"""

from collections.abc import Sequence

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
