"""Event lifecycle, check-in, pause tracking, and round deadline synchronization.

Revision ID: 0005_event_lifecycle_and_rounds
Revises: 0004_ranked_input_fencing
Create Date: 2026-11-04 17:30:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005_event_lifecycle_and_rounds"
down_revision: str | None = "0004_ranked_input_fencing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Events: pause and incident tracking
    op.add_column(
        "events",
        sa.Column("pause_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "events",
        sa.Column(
            "total_pause_duration_seconds",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "events",
        sa.Column("incident_reason", sa.String(255), nullable=True),
    )

    # 2. Rounds: deadline, pause tracking, and optimistic locking version
    op.add_column(
        "rounds",
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "rounds",
        sa.Column("pause_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "rounds",
        sa.Column(
            "total_pause_duration_seconds",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "rounds",
        sa.Column(
            "version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )

    # 3. EventRegistrations: check-in and readiness states
    op.add_column(
        "event_registrations",
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "event_registrations",
        sa.Column(
            "is_ready",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "event_registrations",
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # 3. EventRegistrations
    op.drop_column("event_registrations", "ready_at")
    op.drop_column("event_registrations", "is_ready")
    op.drop_column("event_registrations", "checked_in_at")

    # 2. Rounds
    op.drop_column("rounds", "version")
    op.drop_column("rounds", "total_pause_duration_seconds")
    op.drop_column("rounds", "pause_started_at")
    op.drop_column("rounds", "deadline_at")

    # 1. Events
    op.drop_column("events", "incident_reason")
    op.drop_column("events", "total_pause_duration_seconds")
    op.drop_column("events", "pause_started_at")

