"""Scoring evidence, deterministic replay manifests, result amendments, and dual-approval integrity.

Revision ID: 0006_scoring_and_results
Revises: 0005_event_lifecycle_and_rounds
Create Date: 2026-11-04 17:50:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006_scoring_and_results"
down_revision: str | None = "0005_event_lifecycle_and_rounds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Events: prize flag and ruleset approval status
    op.add_column(
        "events",
        sa.Column(
            "is_prize_event",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "events",
        sa.Column(
            "ruleset_approval_status",
            sa.String(50),
            server_default="draft_awaiting_approval",
            nullable=False,
        ),
    )

    # 2. ParticipantScores: completion ratio and replay manifest
    op.add_column(
        "participant_scores",
        sa.Column(
            "completion_ratio",
            sa.Numeric(6, 4),
            server_default="0.0000",
            nullable=False,
        ),
    )
    op.add_column(
        "participant_scores",
        sa.Column(
            "replay_manifest_json",
            postgresql.JSONB(),
            server_default="{}",
            nullable=False,
        ),
    )

    # 3. PublishedResults: amendment lineage and approval status
    op.add_column(
        "published_results",
        sa.Column(
            "previous_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_published_results_previous_version",
        "published_results",
        "published_results",
        ["previous_version_id"],
        ["id"],
    )
    op.add_column(
        "published_results",
        sa.Column("amendment_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "published_results",
        sa.Column(
            "ruleset_approval_status",
            sa.String(50),
            server_default="draft_awaiting_approval",
            nullable=False,
        ),
    )

    # 4. IntegrityCases: dual-approval fields and evidence references
    op.add_column(
        "integrity_cases",
        sa.Column(
            "second_reviewer_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_integrity_cases_second_reviewer",
        "integrity_cases",
        "users",
        ["second_reviewer_id"],
        ["id"],
    )
    op.add_column(
        "integrity_cases",
        sa.Column("second_approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "integrity_cases",
        sa.Column("second_approval_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "integrity_cases",
        sa.Column(
            "evidence_references_json",
            postgresql.JSONB(),
            server_default="{}",
            nullable=False,
        ),
    )


def downgrade() -> None:
    # 4. IntegrityCases
    op.drop_column("integrity_cases", "evidence_references_json")
    op.drop_column("integrity_cases", "second_approval_notes")
    op.drop_column("integrity_cases", "second_approved_at")
    op.drop_constraint("fk_integrity_cases_second_reviewer", "integrity_cases", type_="foreignkey")
    op.drop_column("integrity_cases", "second_reviewer_id")

    # 3. PublishedResults
    op.drop_column("published_results", "ruleset_approval_status")
    op.drop_column("published_results", "amendment_reason")
    op.drop_constraint("fk_published_results_previous_version", "published_results", type_="foreignkey")
    op.drop_column("published_results", "previous_version_id")

    # 2. ParticipantScores
    op.drop_column("participant_scores", "replay_manifest_json")
    op.drop_column("participant_scores", "completion_ratio")

    # 1. Events
    op.drop_column("events", "ruleset_approval_status")
    op.drop_column("events", "is_prize_event")

