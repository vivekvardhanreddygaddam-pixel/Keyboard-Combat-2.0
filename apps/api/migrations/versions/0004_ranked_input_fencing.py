"""Ranked input projection, sequence watermark, and fencing fields.

Revision ID: 0004_ranked_input_fencing
Revises: 0003_curriculum_attempts
Create Date: 2026-11-04 01:15:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_ranked_input_fencing"
down_revision: str | None = "0003_curriculum_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMPTY_TEXT_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def upgrade() -> None:
    # 1. Add projection and watermark columns to ranked_attempts
    op.add_column(
        "ranked_attempts",
        sa.Column(
            "last_committed_sequence",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "ranked_attempts",
        sa.Column(
            "current_text_projection",
            sa.Text(),
            server_default="",
            nullable=False,
        ),
    )
    op.add_column(
        "ranked_attempts",
        sa.Column(
            "projection_digest_sha256",
            sa.String(64),
            server_default=EMPTY_TEXT_SHA256,
            nullable=False,
        ),
    )
    op.add_column(
        "ranked_attempts",
        sa.Column(
            "keystroke_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "ranked_attempts",
        sa.Column(
            "backspace_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "ranked_attempts",
        sa.Column(
            "deadline_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "ranked_attempts",
        sa.Column(
            "canonical_version",
            sa.String(50),
            server_default="v1_standard",
            nullable=False,
        ),
    )

    # 2. Add verification, digest, and admission columns to ranked_input_batches
    op.add_column(
        "ranked_input_batches",
        sa.Column(
            "payload_digest_sha256",
            sa.String(64),
            server_default="",
            nullable=False,
        ),
    )
    op.add_column(
        "ranked_input_batches",
        sa.Column(
            "resulting_text_length",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "ranked_input_batches",
        sa.Column(
            "resulting_projection_digest",
            sa.String(64),
            server_default=EMPTY_TEXT_SHA256,
            nullable=False,
        ),
    )
    op.add_column(
        "ranked_input_batches",
        sa.Column(
            "server_admitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    # 1. Drop ranked_input_batches columns
    op.drop_column("ranked_input_batches", "server_admitted_at")
    op.drop_column("ranked_input_batches", "resulting_projection_digest")
    op.drop_column("ranked_input_batches", "resulting_text_length")
    op.drop_column("ranked_input_batches", "payload_digest_sha256")

    # 2. Drop ranked_attempts columns
    op.drop_column("ranked_attempts", "canonical_version")
    op.drop_column("ranked_attempts", "deadline_at")
    op.drop_column("ranked_attempts", "backspace_count")
    op.drop_column("ranked_attempts", "keystroke_count")
    op.drop_column("ranked_attempts", "projection_digest_sha256")
    op.drop_column("ranked_attempts", "current_text_projection")
    op.drop_column("ranked_attempts", "last_committed_sequence")

