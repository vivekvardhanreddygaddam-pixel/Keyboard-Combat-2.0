"""Initial authoritative database schema.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-11-04 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), server_default="active", nullable=False),
        sa.Column("role", sa.String(30), server_default="participant", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # 2. user_credentials
    op.create_table(
        "user_credentials",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("algorithm", sa.String(50), server_default="argon2id", nullable=False),
        sa.Column("password_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_user_credentials_user_id_users"),
    )

    # 3. user_sessions
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_token_hash", sa.String(128), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_user_sessions_user_id_users"),
    )
    op.create_index("ix_user_sessions_session_token_hash", "user_sessions", ["session_token_hash"], unique=True)
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])

    # 4. organizations
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    # 5. organization_members
    op.create_table(
        "organization_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_org_members_org_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_org_members_user_id"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
    )
    op.create_index("ix_organization_members_organization_id", "organization_members", ["organization_id"])
    op.create_index("ix_organization_members_user_id", "organization_members", ["user_id"])

    # 6. events
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), server_default="draft", nullable=False),
        sa.Column("capacity", sa.Integer(), server_default="100", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_events_org_id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_events_org_slug"),
        sa.UniqueConstraint("id", "organization_id", name="uq_events_id_org"),
    )
    op.create_index("ix_events_organization_id", "events", ["organization_id"])
    op.create_index("ix_events_slug", "events", ["slug"])

    # 7. event_rulesets
    op.create_table(
        "event_rulesets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("ruleset_json", postgresql.JSONB(), nullable=False),
        sa.Column("min_accuracy_pct", sa.Numeric(5, 2), server_default="90.0", nullable=False),
        sa.Column("duration_seconds", sa.Integer(), server_default="60", nullable=False),
        sa.Column("scoring_formula", sa.String(100), server_default="arena-score-v1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE", name="fk_event_rulesets_event_id"),
        sa.UniqueConstraint("event_id", "version_number", name="uq_event_rulesets_version"),
    )
    op.create_index("ix_event_rulesets_event_id", "event_rulesets", ["event_id"])

    # 8. event_registrations
    op.create_table(
        "event_registrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(50), server_default="pending", nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE", name="fk_event_registrations_event_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_event_registrations_user_id"),
        sa.UniqueConstraint("event_id", "user_id", name="uq_event_registrations_user"),
        sa.UniqueConstraint("id", "event_id", name="uq_event_registrations_id_event"),
    )
    op.create_index("ix_event_registrations_event_id", "event_registrations", ["event_id"])
    op.create_index("ix_event_registrations_user_id", "event_registrations", ["user_id"])

    # 9. rounds
    op.create_table(
        "rounds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), server_default="scheduled", nullable=False),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE", name="fk_rounds_event_id"),
        sa.UniqueConstraint("event_id", "sequence_number", name="uq_rounds_event_seq"),
        sa.UniqueConstraint("id", "event_id", name="uq_rounds_id_event"),
    )
    op.create_index("ix_rounds_event_id", "rounds", ["event_id"])

    # 10. challenge_prompts
    op.create_table(
        "challenge_prompts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("round_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["round_id", "event_id"],
            ["rounds.id", "rounds.event_id"],
            ondelete="CASCADE",
            name="fk_prompts_round_event",
        ),
        sa.UniqueConstraint("round_id", "version_number", name="uq_prompts_round_version"),
    )
    op.create_index("ix_challenge_prompts_round_id", "challenge_prompts", ["round_id"])
    op.create_index("ix_challenge_prompts_event_id", "challenge_prompts", ["event_id"])

    # 11. ranked_attempts
    op.create_table(
        "ranked_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("registration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(50), server_default="in_progress", nullable=False),
        sa.Column("socket_writer_generation", sa.Integer(), server_default="1", nullable=False),
        sa.Column("client_session_id", sa.String(128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["round_id", "event_id"],
            ["rounds.id", "rounds.event_id"],
            ondelete="CASCADE",
            name="fk_attempts_round_event",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "user_id"],
            ["event_registrations.event_id", "event_registrations.user_id"],
            ondelete="CASCADE",
            name="fk_attempts_reg_event_user",
        ),
        sa.UniqueConstraint("round_id", "user_id", "attempt_number", name="uq_attempts_round_user_att"),
        sa.UniqueConstraint("id", "event_id", name="uq_attempts_id_event"),
    )
    op.create_index("ix_ranked_attempts_event_id", "ranked_attempts", ["event_id"])
    op.create_index("ix_ranked_attempts_round_id", "ranked_attempts", ["round_id"])
    op.create_index("ix_ranked_attempts_user_id", "ranked_attempts", ["user_id"])

    # 12. ranked_input_batches
    op.create_table(
        "ranked_input_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_sequence_number", sa.Integer(), nullable=False),
        sa.Column("writer_generation", sa.Integer(), nullable=False),
        sa.Column("raw_events_json", postgresql.JSONB(), nullable=False),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id", "event_id"],
            ["ranked_attempts.id", "ranked_attempts.event_id"],
            ondelete="CASCADE",
            name="fk_batches_attempt_event",
        ),
        sa.UniqueConstraint("attempt_id", "batch_sequence_number", name="uq_batches_attempt_seq"),
    )
    op.create_index("ix_ranked_input_batches_attempt_id", "ranked_input_batches", ["attempt_id"])
    op.create_index("ix_ranked_input_batches_event_id", "ranked_input_batches", ["event_id"])

    # 13. participant_scores
    op.create_table(
        "participant_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gross_wpm", sa.Numeric(6, 2), nullable=False),
        sa.Column("net_wpm", sa.Numeric(6, 2), nullable=False),
        sa.Column("accuracy_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("arena_score", sa.BigInteger(), nullable=False),
        sa.Column("is_complete", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("canonical_hash", sa.String(64), nullable=False),
        sa.Column("score_status", sa.String(50), server_default="provisional", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id", "event_id"],
            ["ranked_attempts.id", "ranked_attempts.event_id"],
            ondelete="CASCADE",
            name="fk_scores_attempt_event",
        ),
        sa.UniqueConstraint("attempt_id", name="uq_scores_attempt"),
    )
    op.create_index("ix_participant_scores_attempt_id", "participant_scores", ["attempt_id"])
    op.create_index("ix_participant_scores_event_id", "participant_scores", ["event_id"])
    op.create_index("ix_participant_scores_round_id", "participant_scores", ["round_id"])
    op.create_index("ix_participant_scores_user_id", "participant_scores", ["user_id"])

    # 14. practice_sessions
    op.create_table(
        "practice_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mode", sa.String(50), nullable=False),
        sa.Column("language", sa.String(50), server_default="en", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gross_wpm", sa.Numeric(6, 2), nullable=True),
        sa.Column("net_wpm", sa.Numeric(6, 2), nullable=True),
        sa.Column("accuracy_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("error_diff_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_practice_user_id"),
    )
    op.create_index("ix_practice_sessions_user_id", "practice_sessions", ["user_id"])

    # 15. skill_tracks
    op.create_table(
        "skill_tracks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_skill_tracks_slug", "skill_tracks", ["slug"], unique=True)

    # 16. skill_track_levels
    op.create_table(
        "skill_track_levels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("skill_track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("level_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("min_wpm", sa.Numeric(6, 2), nullable=False),
        sa.Column("min_accuracy_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("pass_attempts_required", sa.Integer(), server_default="3", nullable=False),
        sa.Column("prompt_content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["skill_track_id"], ["skill_tracks.id"], ondelete="CASCADE", name="fk_track_levels_track_id"),
        sa.UniqueConstraint("skill_track_id", "level_number", name="uq_track_levels_number"),
    )
    op.create_index("ix_skill_track_levels_skill_track_id", "skill_track_levels", ["skill_track_id"])

    # 17. user_curriculum_progress
    op.create_table(
        "user_curriculum_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("current_level_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("total_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("passed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_curriculum_user_id"),
        sa.ForeignKeyConstraint(["skill_track_id"], ["skill_tracks.id"], ondelete="CASCADE", name="fk_curriculum_track_id"),
        sa.UniqueConstraint("user_id", "skill_track_id", name="uq_curriculum_user_track"),
    )
    op.create_index("ix_user_curriculum_progress_user_id", "user_curriculum_progress", ["user_id"])
    op.create_index("ix_user_curriculum_progress_skill_track_id", "user_curriculum_progress", ["skill_track_id"])

    # 18. published_results
    op.create_table(
        "published_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("published_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signed_hash", sa.String(64), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE", name="fk_published_results_event_id"),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["users.id"], name="fk_published_results_user_id"),
        sa.UniqueConstraint("event_id", "version_number", name="uq_results_event_version"),
    )
    op.create_index("ix_published_results_event_id", "published_results", ["event_id"])

    # 19. published_rank_rows
    op.create_table(
        "published_rank_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("published_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rank_order", sa.Integer(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gross_wpm", sa.Numeric(6, 2), nullable=False),
        sa.Column("net_wpm", sa.Numeric(6, 2), nullable=False),
        sa.Column("accuracy_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("arena_score", sa.BigInteger(), nullable=False),
        sa.Column("tier", sa.String(50), server_default="standard", nullable=False),
        sa.ForeignKeyConstraint(["published_result_id"], ["published_results.id"], ondelete="CASCADE", name="fk_rank_rows_result_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_rank_rows_user_id"),
        sa.ForeignKeyConstraint(["score_id"], ["participant_scores.id"], name="fk_rank_rows_score_id"),
        sa.UniqueConstraint("published_result_id", "rank_order", name="uq_published_ranks_order"),
    )
    op.create_index("ix_published_rank_rows_published_result_id", "published_rank_rows", ["published_result_id"])
    op.create_index("ix_published_rank_rows_user_id", "published_rank_rows", ["user_id"])

    # 20. integrity_cases
    op.create_table(
        "integrity_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(50), server_default="flagged", nullable=False),
        sa.Column("flag_reasons_json", postgresql.JSONB(), nullable=False),
        sa.Column("assigned_reviewer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE", name="fk_integrity_cases_event_id"),
        sa.ForeignKeyConstraint(["round_id"], ["rounds.id"], name="fk_integrity_cases_round_id"),
        sa.ForeignKeyConstraint(["attempt_id"], ["ranked_attempts.id"], name="fk_integrity_cases_attempt_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_integrity_cases_user_id"),
        sa.ForeignKeyConstraint(["assigned_reviewer_id"], ["users.id"], name="fk_integrity_cases_reviewer_id"),
    )
    op.create_index("ix_integrity_cases_event_id", "integrity_cases", ["event_id"])
    op.create_index("ix_integrity_cases_attempt_id", "integrity_cases", ["attempt_id"])
    op.create_index("ix_integrity_cases_user_id", "integrity_cases", ["user_id"])

    # 21. integrity_appeals
    op.create_table(
        "integrity_appeals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("integrity_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appeal_statement", sa.Text(), nullable=False),
        sa.Column("status", sa.String(50), server_default="pending", nullable=False),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["integrity_case_id"], ["integrity_cases.id"], ondelete="CASCADE", name="fk_appeals_case_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_appeals_user_id"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], name="fk_appeals_reviewer_id"),
    )
    op.create_index("ix_integrity_appeals_integrity_case_id", "integrity_appeals", ["integrity_case_id"])

    # 22. transactional_outbox
    op.create_table(
        "transactional_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(50), server_default="pending", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_transactional_outbox_event_type", "transactional_outbox", ["event_type"])
    op.create_index("ix_transactional_outbox_status", "transactional_outbox", ["status"])

    # 23. notification_deliveries
    op.create_table(
        "notification_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type", sa.String(100), nullable=False),
        sa.Column("recipient", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), server_default="queued", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_notifications_user_id"),
    )
    op.create_index("ix_notification_deliveries_user_id", "notification_deliveries", ["user_id"])

    # 24. export_jobs
    op.create_table(
        "export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), server_default="queued", nullable=False),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_export_jobs_org_id"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], name="fk_export_jobs_user_id"),
    )
    op.create_index("ix_export_jobs_organization_id", "export_jobs", ["organization_id"])

    # 25. audit_events
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(100), nullable=False),
        sa.Column("target_id", sa.String(100), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_events_organization_id", "audit_events", ["organization_id"])
    op.create_index("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])

    # 26. retention_jobs
    op.create_table(
        "retention_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("records_affected", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(50), server_default="running", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # Drop tables in reverse topological order
    op.drop_table("retention_jobs")
    op.drop_table("audit_events")
    op.drop_table("export_jobs")
    op.drop_table("notification_deliveries")
    op.drop_table("transactional_outbox")
    op.drop_table("integrity_appeals")
    op.drop_table("integrity_cases")
    op.drop_table("published_rank_rows")
    op.drop_table("published_results")
    op.drop_table("user_curriculum_progress")
    op.drop_table("skill_track_levels")
    op.drop_table("skill_tracks")
    op.drop_table("practice_sessions")
    op.drop_table("participant_scores")
    op.drop_table("ranked_input_batches")
    op.drop_table("ranked_attempts")
    op.drop_table("challenge_prompts")
    op.drop_table("rounds")
    op.drop_table("event_registrations")
    op.drop_table("event_rulesets")
    op.drop_table("events")
    op.drop_table("organization_members")
    op.drop_table("organizations")
    op.drop_table("user_sessions")
    op.drop_table("user_credentials")
    op.drop_table("users")

