"""TypeVector Arena — Deterministic Replay and Reconciliation Audit Tests."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

import typevector.models  # noqa: F401
from typevector.domains.events.models import Event
from typevector.domains.integrity_review.models import IntegrityCase
from typevector.domains.ranked_input.models import RankedAttempt
from typevector.domains.rounds.models import ChallengePrompt, Round
from typevector.domains.scoring.canonicalization import CanonicalizationMode
from typevector.domains.scoring.engine import (
    compute_official_score,
    verify_score_replay,
)
from typevector.domains.scoring.models import ParticipantScore
from typevector.domains.scoring.service import ScoringService


class MockScoringSession:
    """Mock async SQLAlchemy session for scoring and reconciliation unit tests."""

    def __init__(self) -> None:
        self.attempts: dict[uuid.UUID, RankedAttempt] = {}
        self.scores: dict[uuid.UUID, ParticipantScore] = {}
        self.rounds: dict[uuid.UUID, Round] = {}
        self.events: dict[uuid.UUID, Event] = {}
        self.prompts: dict[uuid.UUID, ChallengePrompt] = {}
        self.added: list[object] = []

    async def get(self, model: type, identifier: uuid.UUID) -> object | None:
        if model is RankedAttempt:
            return self.attempts.get(identifier)
        if model is ParticipantScore:
            return self.scores.get(identifier)
        if model is Round:
            return self.rounds.get(identifier)
        if model is Event:
            return self.events.get(identifier)
        return None

    async def execute(self, stmt: object) -> MagicMock:
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()

        if "participant_scores" in stmt_str:

            def score_scalar() -> object | None:
                if self.scores:
                    return next(iter(self.scores.values()))
                return None

            mock_result.scalar_one_or_none = score_scalar
            return mock_result

        if "challenge_prompts" in stmt_str:

            def prompt_scalar() -> object | None:
                if self.prompts:
                    return next(iter(self.prompts.values()))
                return None

            mock_result.scalar_one_or_none = prompt_scalar
            return mock_result

        if "event_rulesets" in stmt_str:
            mock_result.scalar_one_or_none.return_value = None
            return mock_result

        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        return mock_result

    def add(self, instance: object) -> None:
        self.added.append(instance)
        if isinstance(instance, RankedAttempt):
            self.attempts[instance.id] = instance
        elif isinstance(instance, ParticipantScore):
            self.scores[instance.attempt_id] = instance
        elif isinstance(instance, Round):
            self.rounds[instance.id] = instance
        elif isinstance(instance, Event):
            self.events[instance.id] = instance
        elif isinstance(instance, ChallengePrompt):
            self.prompts[instance.round_id] = instance

    async def flush(self) -> None:
        pass


def test_deterministic_score_replay_matches_manifest() -> None:
    """Verify that stored manifest can be re-evaluated bit-for-bit to identical scores."""
    prompt = "The integrity of competition rests upon reproducible evidence."
    typed = "The integrity of competition rests upon reproducible evidence."
    elapsed_ms = 45000

    metrics = compute_official_score(
        challenge_text=prompt,
        committed_text=typed,
        active_elapsed_ms=elapsed_ms,
        mode=CanonicalizationMode.PARAGRAPH_GRAPHEME_V1,
    )

    manifest = metrics.replay_manifest

    # Replay against original evidence
    assert (
        verify_score_replay(
            challenge_text=prompt,
            committed_text=typed,
            active_elapsed_ms=elapsed_ms,
            manifest=manifest,
        )
        is True
    )

    # Tampered target prompt fails replay
    assert (
        verify_score_replay(
            challenge_text="Tampered prompt text",
            committed_text=typed,
            active_elapsed_ms=elapsed_ms,
            manifest=manifest,
        )
        is False
    )

    # Tampered committed text fails replay
    assert (
        verify_score_replay(
            challenge_text=prompt,
            committed_text="Tampered input text",
            active_elapsed_ms=elapsed_ms,
            manifest=manifest,
        )
        is False
    )


@pytest.mark.asyncio
async def test_reconciliation_detects_score_discrepancy_without_silent_mutation() -> None:
    """Verify reconciliation detects tampered/inconsistent score, creates case, and does NOT silently mutate."""
    session = MockScoringSession()
    service = ScoringService(session)

    event_id = uuid.uuid4()
    round_id = uuid.uuid4()
    attempt_id = uuid.uuid4()
    user_id = uuid.uuid4()

    event = Event(
        id=event_id, organization_id=uuid.uuid4(), slug="recon-event", title="Recon Event"
    )
    session.add(event)

    round_obj = Round(id=round_id, event_id=event_id, sequence_number=1, status="completed")
    session.add(round_obj)

    prompt = ChallengePrompt(
        id=uuid.uuid4(),
        round_id=round_id,
        event_id=event_id,
        version_number=1,
        content="Target prompt string for reconciliation.",
        token_count=5,
        checksum_sha256="hash",
        is_active=True,
    )
    session.add(prompt)

    attempt = RankedAttempt(
        id=attempt_id,
        event_id=event_id,
        round_id=round_id,
        registration_id=uuid.uuid4(),
        user_id=user_id,
        status="completed",
        started_at=datetime.now(UTC),
        current_text_projection="Target prompt string for reconciliation.",
    )
    session.add(attempt)

    # Calculate authoritative score
    score = await service.calculate_and_persist_attempt_score(attempt_id)
    assert score.arena_score >= 700

    # 1. Consistent reconciliation test
    report_ok = await service.reconcile_attempt_score(attempt_id)
    assert report_ok.is_consistent is True
    assert report_ok.discrepancy_details is None

    # 2. Simulate malicious or corrupted score modification in DB
    score.arena_score = 9999  # Tampered score!

    report_tampered = await service.reconcile_attempt_score(attempt_id)
    assert report_tampered.is_consistent is False
    assert "Discrepancy detected" in str(report_tampered.discrepancy_details)
    assert report_tampered.stored_score == 9999

    # Verify that stored score was NOT silently overwritten
    assert score.arena_score == 9999

    # Verify that an IntegrityCase was created for human investigation
    case_created = any(isinstance(x, IntegrityCase) for x in session.added)
    assert case_created is True
