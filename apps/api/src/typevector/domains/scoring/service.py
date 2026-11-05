"""TypeVector Arena — Scoring Domain Service with Reconciliation and Integrity Audit."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from typevector.domains.audit.models import AuditEvent
from typevector.domains.events.models import Event, EventRuleset
from typevector.domains.integrity_review.models import IntegrityCase
from typevector.domains.notifications.models import TransactionalOutbox
from typevector.domains.ranked_input.models import RankedAttempt
from typevector.domains.rounds.models import ChallengePrompt, Round
from typevector.domains.scoring.canonicalization import CanonicalizationMode
from typevector.domains.scoring.engine import (
    SCORING_POLICY_STATUS,
    compute_official_score,
)
from typevector.domains.scoring.models import ParticipantScore
from typevector.domains.scoring.schemas import MetricGlossaryItem, ReconciliationReport
from typevector.errors import EntityNotFoundError, InvariantViolationError

METRIC_GLOSSARY: dict[str, dict[str, str]] = {
    "Local": {
        "definition": "Client-buffered keystrokes and uncommitted edits on the user's active device.",
        "source": "In-browser DOM event listener",
        "denominator": "Local high-resolution performance timer",
        "rounding": "Visual UI approximation",
        "limitations": "Not authoritative; subject to browser thread suspension, tab throttling, and lost socket transmission.",
    },
    "Pending": {
        "definition": "In-flight batch transmissions queued in WebSocket pipeline awaiting server processing.",
        "source": "Client WebSocket batch queue",
        "denominator": "Elapsed round duration",
        "rounding": "None",
        "limitations": "Volatile; can be lost if browser terminates prior to server-side database commit and ACK.",
    },
    "Saved": {
        "definition": "Materialized projection persisted and durably committed to PostgreSQL.",
        "source": "ranked_input_batches table (monotonically sequenced)",
        "denominator": "Committed batch sequence number",
        "rounding": "None",
        "limitations": "Reflects admitted keystrokes only; does not yet represent an official scoring decision.",
    },
    "Provisional": {
        "definition": "Server-calculated score and metrics generated upon round completion prior to integrity audit.",
        "source": "participant_scores table computed via arena-score-v1",
        "denominator": "Authoritative server round duration (milliseconds)",
        "rounding": "Gross/Net WPM to 2 decimals, Accuracy to 2 decimals, Integer Arena Score",
        "limitations": "Subject to post-round integrity review flags, dual-approval, and participant appeal windows.",
    },
    "Official": {
        "definition": "Verified, immutable tournament standing sealed into published event results.",
        "source": "published_results and published_rank_rows tables",
        "denominator": "Multi-round weighted integer denominator",
        "rounding": "Deterministic integer rounding",
        "limitations": "Immutable; can only be superseded by a formal versioned amendment following an upheld appeal.",
    },
    "Unavailable": {
        "definition": "Score cannot be calculated or published due to disqualification, participant no-show, or voided round.",
        "source": "Tournament integrity rule enforcement",
        "denominator": "Excluded or zeroed according to published fairness policy",
        "rounding": "None",
        "limitations": "Permanent for disqualified attempts.",
    },
}


class ScoringService:
    """Domain service managing score calculation, verification, and canonicalization."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_attempt(self, attempt_id: uuid.UUID) -> ParticipantScore:
        """Fetch score record for an attempt."""
        stmt = select(ParticipantScore).where(ParticipantScore.attempt_id == attempt_id)
        result = await self.session.execute(stmt)
        score = result.scalar_one_or_none()
        if not score:
            raise EntityNotFoundError(entity="Score", identifier=attempt_id)
        return score

    def get_metrics_glossary(self) -> dict[str, MetricGlossaryItem]:
        """Return the authoritative dictionary of user metric definitions."""
        return {k: MetricGlossaryItem(label=k, **v) for k, v in METRIC_GLOSSARY.items()}

    async def calculate_and_persist_attempt_score(
        self,
        attempt_id: uuid.UUID,
    ) -> ParticipantScore:
        """Compute and persist authoritative tournament score from server-admitted evidence."""
        attempt = await self.session.get(RankedAttempt, attempt_id)
        if not attempt:
            raise EntityNotFoundError(entity="RankedAttempt", identifier=attempt_id)

        round_obj = await self.session.get(Round, attempt.round_id)
        if not round_obj:
            raise EntityNotFoundError(entity="Round", identifier=attempt.round_id)

        event = await self.session.get(Event, attempt.event_id)
        if not event:
            raise EntityNotFoundError(entity="Event", identifier=attempt.event_id)

        # Retrieve active challenge prompt
        prompt_stmt = (
            select(ChallengePrompt)
            .where(
                ChallengePrompt.round_id == attempt.round_id,
                ChallengePrompt.is_active.is_(True),
            )
            .order_by(ChallengePrompt.version_number.desc())
            .limit(1)
        )
        prompt_res = await self.session.execute(prompt_stmt)
        prompt = prompt_res.scalar_one_or_none()
        if not prompt:
            raise InvariantViolationError(
                f"No active challenge prompt found for round {attempt.round_id}"
            )

        # Retrieve ruleset configuration
        ruleset_stmt = (
            select(EventRuleset)
            .where(EventRuleset.event_id == attempt.event_id)
            .order_by(EventRuleset.version_number.desc())
            .limit(1)
        )
        ruleset_res = await self.session.execute(ruleset_stmt)
        ruleset = ruleset_res.scalar_one_or_none()
        ruleset_dict: dict[str, Any] = ruleset.ruleset_json if ruleset else {}

        # Determine mode
        is_code = ruleset_dict.get("content_type") == "code" or "def " in prompt.content
        mode = (
            CanonicalizationMode.CODE_SCALAR_V1
            if is_code
            else CanonicalizationMode.PARAGRAPH_GRAPHEME_V1
        )

        # Calculate authoritative active elapsed duration
        now = datetime.now(UTC)
        end_time = attempt.completed_at or attempt.deadline_at or now
        raw_elapsed = (end_time - attempt.started_at).total_seconds()
        # Subtract event/round pause duration
        pause_seconds = round_obj.total_pause_duration_seconds or 0
        active_elapsed_seconds = max(0.1, raw_elapsed - pause_seconds)
        active_elapsed_ms = int(active_elapsed_seconds * 1000)

        # Compute deterministic score
        metrics = compute_official_score(
            challenge_text=prompt.content,
            committed_text=attempt.current_text_projection,
            active_elapsed_ms=active_elapsed_ms,
            mode=mode,
            configuration_metadata=ruleset_dict,
        )

        # Check existing score record
        existing_stmt = select(ParticipantScore).where(ParticipantScore.attempt_id == attempt_id)
        existing = (await self.session.execute(existing_stmt)).scalar_one_or_none()

        if existing:
            score_obj = existing
            score_obj.gross_wpm = metrics.gross_wpm
            score_obj.net_wpm = metrics.net_wpm
            score_obj.accuracy_pct = metrics.accuracy_pct
            score_obj.arena_score = metrics.arena_score
            score_obj.is_complete = metrics.is_complete
            score_obj.completion_ratio = metrics.completion_ratio
            score_obj.canonical_hash = metrics.canonical_hash
            score_obj.replay_manifest_json = metrics.replay_manifest
        else:
            score_obj = ParticipantScore(
                id=uuid.uuid4(),
                attempt_id=attempt.id,
                event_id=attempt.event_id,
                round_id=attempt.round_id,
                user_id=attempt.user_id,
                gross_wpm=metrics.gross_wpm,
                net_wpm=metrics.net_wpm,
                accuracy_pct=metrics.accuracy_pct,
                arena_score=metrics.arena_score,
                is_complete=metrics.is_complete,
                completion_ratio=metrics.completion_ratio,
                canonical_hash=metrics.canonical_hash,
                score_status="provisional",
                replay_manifest_json=metrics.replay_manifest,
            )
            self.session.add(score_obj)

        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=event.organization_id,
            actor_user_id=attempt.user_id,
            event_type="scoring.attempt_calculated",
            target_type="participant_score",
            target_id=str(score_obj.id),
            payload_json={
                "attempt_id": str(attempt.id),
                "arena_score": metrics.arena_score,
                "net_wpm": metrics.net_wpm,
                "is_complete": metrics.is_complete,
                "policy_status": SCORING_POLICY_STATUS,
            },
        )
        self.session.add(audit)

        outbox = TransactionalOutbox(
            id=uuid.uuid4(),
            event_type="arena:events:scores",
            payload_json={
                "event_id": str(attempt.event_id),
                "round_id": str(attempt.round_id),
                "user_id": str(attempt.user_id),
                "attempt_id": str(attempt.id),
                "arena_score": metrics.arena_score,
                "net_wpm": metrics.net_wpm,
                "is_complete": metrics.is_complete,
            },
            status="pending",
        )
        self.session.add(outbox)
        await self.session.flush()

        return score_obj

    async def reconcile_attempt_score(
        self,
        attempt_id: uuid.UUID,
    ) -> ReconciliationReport:
        """Audit and reconcile stored score against recomputed input evidence.

        INVARIANT: If an inconsistency is detected, DO NOT silently rewrite or mutate
        the official record. Emit an audit event and flag an integrity case.
        """
        score = await self.get_by_attempt(attempt_id)
        manifest = score.replay_manifest_json

        attempt = await self.session.get(RankedAttempt, attempt_id)
        if not attempt:
            raise EntityNotFoundError(entity="RankedAttempt", identifier=attempt_id)

        prompt_stmt = (
            select(ChallengePrompt)
            .where(
                ChallengePrompt.round_id == attempt.round_id,
                ChallengePrompt.is_active.is_(True),
            )
            .order_by(ChallengePrompt.version_number.desc())
            .limit(1)
        )
        prompt = (await self.session.execute(prompt_stmt)).scalar_one_or_none()
        if not prompt:
            raise InvariantViolationError(f"No challenge prompt for round {attempt.round_id}")

        mode = manifest.get("canonicalization_mode", CanonicalizationMode.PARAGRAPH_GRAPHEME_V1)
        active_elapsed_ms = manifest.get("active_elapsed_ms", 60000)

        # Deterministic re-computation
        recomputed = compute_official_score(
            challenge_text=prompt.content,
            committed_text=attempt.current_text_projection,
            active_elapsed_ms=active_elapsed_ms,
            mode=mode,
        )

        is_consistent = (
            recomputed.arena_score == score.arena_score
            and recomputed.canonical_hash == score.canonical_hash
            and recomputed.is_complete == score.is_complete
        )

        discrepancy: str | None = None
        if not is_consistent:
            discrepancy = (
                f"Discrepancy detected: Stored score {score.arena_score} (hash: {score.canonical_hash}) "
                f"!= Recomputed score {recomputed.arena_score} (hash: {recomputed.canonical_hash})."
            )

            # Create integrity case flag without silently altering the official record
            case = IntegrityCase(
                id=uuid.uuid4(),
                event_id=score.event_id,
                round_id=score.round_id,
                attempt_id=score.attempt_id,
                user_id=score.user_id,
                status="flagged",
                flag_reasons_json={
                    "type": "scoring_projection_inconsistency",
                    "details": discrepancy,
                },
                evidence_references_json={
                    "stored_manifest": manifest,
                    "recomputed_manifest": recomputed.replay_manifest,
                },
            )
            self.session.add(case)

            event = await self.session.get(Event, score.event_id)
            audit = AuditEvent(
                id=uuid.uuid4(),
                organization_id=event.organization_id if event else None,
                actor_user_id=None,
                event_type="audit.scoring_inconsistency_detected",
                target_type="participant_score",
                target_id=str(score.id),
                payload_json={"attempt_id": str(attempt_id), "details": discrepancy},
            )
            self.session.add(audit)
            await self.session.flush()

        return ReconciliationReport(
            attempt_id=attempt_id,
            is_consistent=is_consistent,
            stored_score=score.arena_score,
            recomputed_score=recomputed.arena_score,
            stored_hash=score.canonical_hash,
            recomputed_hash=recomputed.canonical_hash,
            discrepancy_details=discrepancy,
        )
