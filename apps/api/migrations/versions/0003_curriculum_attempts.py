"""Curriculum attempts and multi-attempt progression tracking.

Revision ID: 0003_curriculum_attempts
Revises: 0002_identity_claims
Create Date: 2026-11-04 00:50:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_curriculum_attempts"
down_revision: str | None = "0002_identity_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add criteria_version to skill_track_levels
    op.add_column(
        "skill_track_levels",
        sa.Column(
            "criteria_version",
            sa.String(50),
            server_default="2026.1-draft",
            nullable=False,
        ),
    )

    # 2. Add qualifying_attempts_count and criteria_version to user_curriculum_progress
    op.add_column(
        "user_curriculum_progress",
        sa.Column(
            "qualifying_attempts_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "user_curriculum_progress",
        sa.Column(
            "criteria_version",
            sa.String(50),
            server_default="2026.1-draft",
            nullable=False,
        ),
    )

    # 3. Create curriculum_attempts table
    op.create_table(
        "curriculum_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("level_number", sa.Integer(), nullable=False),
        sa.Column("net_wpm", sa.Numeric(6, 2), nullable=False),
        sa.Column("accuracy_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("completion_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("is_qualifying", sa.Boolean(), nullable=False),
        sa.Column("criteria_version", sa.String(50), nullable=False),
        sa.Column("evaluation_details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_curriculum_attempts_user_id"),
        sa.ForeignKeyConstraint(["skill_track_id"], ["skill_tracks.id"], ondelete="CASCADE", name="fk_curriculum_attempts_track_id"),
    )
    op.create_index(
        "ix_curriculum_attempts_user_track_lvl",
        "curriculum_attempts",
        ["user_id", "skill_track_id", "level_number"],
    )


def downgrade() -> None:
    op.drop_table("curriculum_attempts")
    op.drop_column("user_curriculum_progress", "criteria_version")
    op.drop_column("user_curriculum_progress", "qualifying_attempts_count")
    op.drop_column("skill_track_levels", "criteria_version")

