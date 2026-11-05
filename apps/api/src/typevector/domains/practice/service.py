"""TypeVector Arena — Practice Domain Service.

Coordinates practice prompts, deterministic evaluation, metrics, and persistence.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from typevector.domains.audit.models import AuditEvent
from typevector.domains.practice.canonicalization import (
    CanonicalizationVersion,
    canonicalize_text,
)
from typevector.domains.practice.diff_engine import compute_deterministic_diff
from typevector.domains.practice.metrics import calculate_practice_metrics
from typevector.domains.practice.models import PracticeSession
from typevector.domains.practice.prompts import (
    get_all_prompts,
    get_prompt_by_id,
    get_prompts_by_mode,
)
from typevector.domains.practice.schemas import PracticeSessionSubmit

PRACTICE_MODES: list[dict[str, Any]] = [
    {
        "mode": "common_words",
        "title": "Common & Difficult Words",
        "description": "High-frequency vocabulary and common adjacent-key obstacles.",
        "is_timed": False,
        "duration_seconds": None,
        "target_accuracy_min": 95.0,
    },
    {
        "mode": "sentences",
        "title": "Sentences & Punctuation",
        "description": "Natural sentences focusing on commas, periods, quotes, and capitalization.",
        "is_timed": False,
        "duration_seconds": None,
        "target_accuracy_min": 96.0,
    },
    {
        "mode": "paragraphs",
        "title": "Short & Long Paragraphs",
        "description": "Structured multi-line prose testing sustained typing cadence.",
        "is_timed": False,
        "duration_seconds": None,
        "target_accuracy_min": 96.0,
    },
    {
        "mode": "precision",
        "title": "Numbers & Symbol Precision",
        "description": "Top-row digits, currencies, percentages, and math symbols.",
        "is_timed": False,
        "duration_seconds": None,
        "target_accuracy_min": 97.0,
    },
    {
        "mode": "code",
        "title": "Code Snippets",
        "description": "Programming syntax with visible whitespace, brackets, and indentation.",
        "is_timed": False,
        "duration_seconds": None,
        "target_accuracy_min": 98.0,
    },
    {
        "mode": "speed_sprint",
        "title": "Speed Sprint (60s)",
        "description": "One-minute countdown sprint testing burst speed and rhythm.",
        "is_timed": True,
        "duration_seconds": 60,
        "target_accuracy_min": 93.0,
    },
    {
        "mode": "accuracy_challenge",
        "title": "Accuracy Challenge",
        "description": "Zero-tolerance drill requiring 98%+ precision under pressure.",
        "is_timed": False,
        "duration_seconds": None,
        "target_accuracy_min": 98.0,
    },
    {
        "mode": "endurance",
        "title": "Consistency & Endurance",
        "description": "Extended multi-paragraph stamina test to maintain pace without fatigue.",
        "is_timed": False,
        "duration_seconds": None,
        "target_accuracy_min": 95.0,
    },
    {
        "mode": "diagnostic",
        "title": "Diagnostic Practice",
        "description": "Evidence-backed calibration passage diagnosing specific finger weaknesses.",
        "is_timed": False,
        "duration_seconds": None,
        "target_accuracy_min": 95.0,
    },
]


class PracticeService:
    """Domain service managing practice sessions, canonicalization, and evaluations."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    def list_modes(self) -> list[dict[str, Any]]:
        """Return the catalog of supported practice modes."""
        return PRACTICE_MODES

    def list_prompts(self, mode: str | None = None) -> list[dict[str, Any]]:
        """Return practice prompts, optionally filtered by mode."""
        if mode:
            return get_prompts_by_mode(mode)
        return get_all_prompts()

    def get_prompt(self, prompt_id: str) -> dict[str, Any] | None:
        """Fetch a practice prompt by ID."""
        return get_prompt_by_id(prompt_id)

    async def evaluate_and_record_session(
        self,
        submission: PracticeSessionSubmit,
        user_id: uuid.UUID | None = None,
    ) -> tuple[PracticeSession, bool]:
        """Evaluate a practice typing attempt authoritatively and persist it if database is reachable."""
        # 1. Canonicalize text
        canon_version = (
            CanonicalizationVersion.V1_CODE
            if submission.mode == "code"
            else CanonicalizationVersion.V1_STANDARD
        )
        target_canon = canonicalize_text(submission.target_text, version=canon_version)
        input_canon = canonicalize_text(submission.input_text, version=canon_version)

        # 2. Timing calculation
        duration_seconds = max(
            0.5,
            (submission.completed_at - submission.started_at).total_seconds(),
        )

        # 3. Deterministic sequence alignment
        diff_result = compute_deterministic_diff(target_canon, input_canon)

        # 4. Authoritative metrics calculation
        metrics = calculate_practice_metrics(diff_result, duration_seconds)

        # 5. Build rich JSON evidence
        error_diff_json = {
            "prompt_id": submission.prompt_id,
            "mode": submission.mode,
            "target_text": target_canon,
            "input_text": input_canon,
            "metrics": metrics,
            "segments": diff_result["segments"],
            "error_breakdown": diff_result["error_counts"],
            "suggestions": metrics["suggestions"],
            "evaluated_at": datetime.now(UTC).isoformat(),
        }

        # 6. Create practice session record
        practice_session = PracticeSession(
            id=uuid.uuid4(),
            user_id=user_id,
            mode=submission.mode,
            language=submission.language,
            started_at=submission.started_at,
            completed_at=submission.completed_at,
            gross_wpm=metrics["gross_wpm"],
            net_wpm=metrics["net_wpm"],
            accuracy_pct=metrics["accuracy_pct"],
            error_diff_json=error_diff_json,
        )

        is_saved = False
        if self.session is not None:
            try:
                self.session.add(practice_session)
                await self.session.flush()
                is_saved = True

                # 7. Audit log if authenticated
                if user_id:
                    audit = AuditEvent(
                        actor_user_id=user_id,
                        event_type="practice.session_completed",
                        target_type="practice_session",
                        target_id=str(practice_session.id),
                        payload_json={
                            "mode": submission.mode,
                            "net_wpm": metrics["net_wpm"],
                            "accuracy_pct": metrics["accuracy_pct"],
                        },
                    )
                    self.session.add(audit)
            except Exception:
                is_saved = False

        return practice_session, is_saved

    async def get_session_by_id(self, session_id: uuid.UUID) -> PracticeSession | None:
        """Fetch a specific practice session by primary key."""
        if self.session is None:
            return None
        stmt = select(PracticeSession).where(PracticeSession.id == session_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_user_history(
        self, user_id: uuid.UUID, limit: int = 20, offset: int = 0
    ) -> list[PracticeSession]:
        """Fetch practice session history for a user, ordered by most recent."""
        if self.session is None:
            return []
        stmt = (
            select(PracticeSession)
            .where(PracticeSession.user_id == user_id)
            .order_by(PracticeSession.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
