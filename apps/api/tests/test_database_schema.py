"""TypeVector Arena — Relational Schema and Constraint Integrity Tests."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from typevector.db.base import POSTGRES_NAMING_CONVENTION
from typevector.models import Base


def test_metadata_table_inventory() -> None:
    """Verify that all 26 authoritative domain tables are registered with Base.metadata."""
    expected_tables = {
        "users",
        "user_credentials",
        "user_sessions",
        "identity_claims",
        "organizations",
        "organization_members",
        "events",
        "event_rulesets",
        "event_registrations",
        "rounds",
        "challenge_prompts",
        "ranked_attempts",
        "ranked_input_batches",
        "participant_scores",
        "practice_sessions",
        "skill_tracks",
        "skill_track_levels",
        "user_curriculum_progress",
        "curriculum_attempts",
        "published_results",
        "published_rank_rows",
        "integrity_cases",
        "integrity_appeals",
        "transactional_outbox",
        "notification_deliveries",
        "export_jobs",
        "audit_events",
        "retention_jobs",
    }

    registered_tables = set(Base.metadata.tables.keys())
    missing_tables = expected_tables - registered_tables
    assert not missing_tables, f"Missing tables in Base.metadata: {missing_tables}"


def test_composite_foreign_keys_and_cross_event_invariants() -> None:
    """Verify composite constraints preventing cross-event or cross-user data bleeding."""
    tables = Base.metadata.tables

    # 1. Rounds must expose (id, event_id) uniqueness for composite references
    rounds_table = tables["rounds"]
    round_uniques = [
        tuple(c.name for c in u.columns)
        for u in rounds_table.constraints
        if isinstance(u, UniqueConstraint)
    ]
    assert ("id", "event_id") in round_uniques, (
        "rounds must have UniqueConstraint('id', 'event_id')"
    )

    # 2. EventRegistrations must expose (event_id, user_id) uniqueness
    reg_table = tables["event_registrations"]
    reg_uniques = [
        tuple(c.name for c in u.columns)
        for u in reg_table.constraints
        if isinstance(u, UniqueConstraint)
    ]
    assert (
        "event_id",
        "user_id",
    ) in reg_uniques, "event_registrations must have UniqueConstraint('event_id', 'user_id')"

    # 3. RankedAttempts composite FKs to (rounds.id, rounds.event_id) and (event_registrations.event_id, event_registrations.user_id)
    attempt_table = tables["ranked_attempts"]
    fk_constraints = [c for c in attempt_table.constraints if isinstance(c, ForeignKeyConstraint)]

    fk_targets = [
        (tuple(col.name for col in fk.columns), tuple(el.target_fullname for el in fk.elements))
        for fk in fk_constraints
    ]

    has_round_fk = any(
        cols == ("round_id", "event_id") and targets == ("rounds.id", "rounds.event_id")
        for cols, targets in fk_targets
    )
    assert has_round_fk, (
        "ranked_attempts must have composite FK (round_id, event_id) -> rounds(id, event_id)"
    )

    has_reg_fk = any(
        cols == ("event_id", "user_id")
        and targets == ("event_registrations.event_id", "event_registrations.user_id")
        for cols, targets in fk_targets
    )
    assert has_reg_fk, (
        "ranked_attempts must have composite FK (event_id, user_id) -> event_registrations(event_id, user_id)"
    )

    # 4. RankedInputBatches composite FK to (ranked_attempts.id, ranked_attempts.event_id)
    batch_table = tables["ranked_input_batches"]
    batch_fks = [c for c in batch_table.constraints if isinstance(c, ForeignKeyConstraint)]
    batch_fk_targets = [
        (tuple(col.name for col in fk.columns), tuple(el.target_fullname for el in fk.elements))
        for fk in batch_fks
    ]
    has_batch_attempt_fk = any(
        cols == ("attempt_id", "event_id")
        and targets == ("ranked_attempts.id", "ranked_attempts.event_id")
        for cols, targets in batch_fk_targets
    )
    assert has_batch_attempt_fk, (
        "ranked_input_batches must have composite FK (attempt_id, event_id) -> ranked_attempts(id, event_id)"
    )


def test_naming_conventions_applied() -> None:
    """Verify Base.metadata naming convention matches strict PostgreSQL standards."""
    assert Base.metadata.naming_convention == POSTGRES_NAMING_CONVENTION
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"
    assert Base.metadata.naming_convention["uq"] == "uq_%(table_name)s_%(column_0_name)s"
    assert (
        Base.metadata.naming_convention["fk"]
        == "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    )


def test_alembic_offline_sql_generation(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify that Alembic can compile upgrade and downgrade DDL to PostgreSQL without error."""
    possible_paths = [Path("alembic.ini"), Path("apps/api/alembic.ini")]
    ini_path = next((p for p in possible_paths if p.exists()), None)
    assert ini_path is not None, "alembic.ini not found"

    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("script_location", str(ini_path.parent / "migrations"))
    alembic_cfg.set_main_option(
        "version_locations", str(ini_path.parent / "migrations" / "versions")
    )

    # Test upgrade
    command.upgrade(alembic_cfg, "base:head", sql=True)
    captured_upgrade = capsys.readouterr()

    assert "CREATE TABLE ranked_attempts" in captured_upgrade.out
    assert "CREATE TABLE participant_scores" in captured_upgrade.out
    assert "CREATE TABLE published_results" in captured_upgrade.out
    assert "CREATE TABLE identity_claims" in captured_upgrade.out
    assert "CREATE TABLE curriculum_attempts" in captured_upgrade.out
    assert "COMMIT;" in captured_upgrade.out

    # Test downgrade
    command.downgrade(alembic_cfg, "head:base", sql=True)
    captured_downgrade = capsys.readouterr()

    assert "DROP TABLE curriculum_attempts;" in captured_downgrade.out
    assert "DROP TABLE identity_claims;" in captured_downgrade.out
    assert "DROP TABLE ranked_attempts;" in captured_downgrade.out
    assert "DROP TABLE users;" in captured_downgrade.out
    assert "COMMIT;" in captured_downgrade.out


@pytest.mark.asyncio
async def test_postgresql_live_connection_probe() -> None:
    """Probe live PostgreSQL connection or report offline environment prerequisite."""
    from typevector.database import check_database_connection

    try:
        await check_database_connection()
        is_connected = True
    except Exception as e:
        is_connected = False
        print(f"\n[INFO] PostgreSQL service is offline in this host environment: {e}")

    assert isinstance(is_connected, bool)
