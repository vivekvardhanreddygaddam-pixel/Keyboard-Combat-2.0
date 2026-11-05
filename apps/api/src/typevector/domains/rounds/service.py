"""TypeVector Arena — Rounds Domain Service."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from typevector.domains.audit.models import AuditEvent
from typevector.domains.events.lifecycle import EventStatus
from typevector.domains.events.models import Event, EventRuleset
from typevector.domains.notifications.models import TransactionalOutbox
from typevector.domains.ranked_input.models import RankedAttempt
from typevector.domains.rounds.models import ChallengePrompt, Round
from typevector.errors import (
    ConflictError,
    EntityNotFoundError,
    ForbiddenError,
    InvariantViolationError,
)


class RoundService:
    """Domain service managing competition rounds, schedule progression, and prompt pinning."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_round(self, round_id: uuid.UUID) -> Round:
        """Fetch round by UUID."""
        round_obj = await self.session.get(Round, round_id)
        if not round_obj:
            raise EntityNotFoundError(entity="Round", identifier=round_id)
        return round_obj

    async def list_by_event(self, event_id: uuid.UUID) -> list[Round]:
        """List rounds configured for an event."""
        stmt = select(Round).where(Round.event_id == event_id).order_by(Round.sequence_number.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_round(
        self,
        event_id: uuid.UUID,
        sequence_number: int,
        prompt_content: str | None = None,
        scheduled_start_at: datetime | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> Round:
        """Create a competition round for an event while in DRAFT status."""
        event = await self.session.get(Event, event_id)
        if not event:
            raise EntityNotFoundError(entity="Event", identifier=event_id)
        if event.status != EventStatus.DRAFT:
            raise InvariantViolationError(
                f"Cannot add rounds to event in status '{event.status}'. Rules and rounds are immutable once published."
            )

        seq_stmt = select(Round).where(
            Round.event_id == event_id,
            Round.sequence_number == sequence_number,
        )
        existing = (await self.session.execute(seq_stmt)).scalar_one_or_none()
        if existing:
            raise ConflictError(f"Round {sequence_number} already exists for this event.")

        round_obj = Round(
            id=uuid.uuid4(),
            event_id=event_id,
            sequence_number=sequence_number,
            status="scheduled",
            version=1,
            scheduled_start_at=scheduled_start_at,
        )
        self.session.add(round_obj)
        await self.session.flush()

        if prompt_content:
            token_count = len(prompt_content.split())
            await self.pin_challenge_prompt(
                round_id=round_obj.id,
                content=prompt_content,
                token_count=token_count,
            )

        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=event.organization_id,
            actor_user_id=actor_id,
            event_type="rounds.created",
            target_type="round",
            target_id=str(round_obj.id),
            payload_json={"event_id": str(event_id), "sequence_number": sequence_number},
        )
        self.session.add(audit)
        return round_obj

    async def update_round(
        self,
        round_id: uuid.UUID,
        sequence_number: int | None = None,
        scheduled_start_at: datetime | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> Round:
        """Update a round while event is in DRAFT status."""
        round_obj = await self.get_round(round_id)
        event = await self.session.get(Event, round_obj.event_id)
        if not event or event.status != EventStatus.DRAFT:
            raise InvariantViolationError("Cannot modify round once event leaves DRAFT status.")

        if sequence_number is not None and sequence_number != round_obj.sequence_number:
            seq_stmt = select(Round).where(
                Round.event_id == round_obj.event_id,
                Round.sequence_number == sequence_number,
                Round.id != round_id,
            )
            existing = (await self.session.execute(seq_stmt)).scalar_one_or_none()
            if existing:
                raise ConflictError(f"Round {sequence_number} already exists for this event.")
            round_obj.sequence_number = sequence_number

        if scheduled_start_at is not None:
            round_obj.scheduled_start_at = scheduled_start_at

        round_obj.version = (round_obj.version or 1) + 1

        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=event.organization_id,
            actor_user_id=actor_id,
            event_type="rounds.updated",
            target_type="round",
            target_id=str(round_obj.id),
            payload_json={"round_id": str(round_id), "version": round_obj.version},
        )
        self.session.add(audit)
        return round_obj

    async def list_prompts_for_round(self, round_id: uuid.UUID) -> list[ChallengePrompt]:
        """List all challenge prompts pinned to a round."""
        stmt = (
            select(ChallengePrompt)
            .where(ChallengePrompt.round_id == round_id)
            .order_by(ChallengePrompt.version_number.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_active_prompt(
        self, round_id: uuid.UUID, allow_unstarted_content: bool = False
    ) -> tuple[ChallengePrompt, str | None]:
        """Fetch the active ChallengePrompt for a round.

        A challenge prompt text cannot be exposed before authorized round start.
        If round is not active/in_progress, return (prompt, None).
        """
        round_obj = await self.get_round(round_id)
        stmt = (
            select(ChallengePrompt)
            .where(
                ChallengePrompt.round_id == round_id,
                ChallengePrompt.is_active.is_(True),
            )
            .order_by(ChallengePrompt.version_number.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        prompt = res.scalar_one_or_none()
        if not prompt:
            raise EntityNotFoundError(entity="ChallengePrompt", identifier=round_id)

        is_round_active = round_obj.status in ("active", "in_progress")
        if is_round_active or allow_unstarted_content:
            return prompt, prompt.content
        return prompt, None

    async def pin_challenge_prompt(
        self,
        round_id: uuid.UUID,
        content: str,
        token_count: int,
    ) -> ChallengePrompt:
        """Create or update a versioned challenge prompt for a round.

        Prompt cannot be modified after round or event leaves DRAFT/SCHEDULED.
        """
        round_obj = await self.get_round(round_id)
        if round_obj.status in ("active", "in_progress", "paused", "closed", "completed", "voided"):
            raise ConflictError(
                f"Cannot modify challenge prompt after round has opened or started (current status: {round_obj.status})"
            )

        event = await self.session.get(Event, round_obj.event_id)
        if event and event.status not in (EventStatus.DRAFT,):
            raise ConflictError(
                f"Cannot modify challenge prompt when event is '{event.status}'. Rulesets are frozen."
            )

        # Determine next version number
        stmt = (
            select(ChallengePrompt.version_number)
            .where(ChallengePrompt.round_id == round_id)
            .order_by(ChallengePrompt.version_number.desc())
            .limit(1)
        )
        current_max_ver = (await self.session.execute(stmt)).scalar_one_or_none() or 0
        new_version = current_max_ver + 1

        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()

        prompt = ChallengePrompt(
            id=uuid.uuid4(),
            round_id=round_id,
            event_id=round_obj.event_id,
            version_number=new_version,
            content=content,
            token_count=token_count,
            checksum_sha256=checksum,
            is_active=True,
        )
        self.session.add(prompt)
        await self.session.flush()
        return prompt

    async def start_round(
        self,
        round_id: uuid.UUID,
        actor_id: uuid.UUID,
        actor_roles: list[str],
        expected_version: int,
    ) -> Round:
        """Start a scheduled competition round with server-authoritative deadline."""
        round_obj = await self.get_round(round_id)

        # 1. Optimistic lock check
        if round_obj.version != expected_version:
            raise ConflictError(
                f"Concurrent modification on round {round_id}. Expected version {expected_version}, found {round_obj.version}."
            )

        # 2. Role authorization
        if not any(r in ("org_admin", "platform_admin") for r in actor_roles):
            raise ForbiddenError("Actor lacks required role to start competition round.")

        # 3. Round state
        if round_obj.status != "scheduled":
            raise ConflictError(
                f"Cannot start round in state '{round_obj.status}'. Round must be 'scheduled'."
            )

        # 4. Event state check: event must be LIVE
        event = await self.session.get(Event, round_obj.event_id)
        if not event or event.status != EventStatus.LIVE:
            raise ConflictError(
                f"Cannot start round when parent event is not LIVE (current event status: {event.status if event else 'unknown'})."
            )

        # 5. Determine round duration from ruleset
        ruleset_stmt = (
            select(EventRuleset)
            .where(EventRuleset.event_id == round_obj.event_id)
            .order_by(EventRuleset.version_number.desc())
            .limit(1)
        )
        ruleset = (await self.session.execute(ruleset_stmt)).scalar_one_or_none()
        duration_seconds = ruleset.duration_seconds if ruleset else 60

        now = datetime.now(UTC)
        round_obj.started_at = now
        round_obj.deadline_at = now + timedelta(seconds=duration_seconds)
        round_obj.status = "active"
        round_obj.version += 1

        # Audit event
        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=event.organization_id if event else None,
            actor_user_id=actor_id,
            event_type="round.started",
            target_type="round",
            target_id=str(round_obj.id),
            payload_json={
                "event_id": str(round_obj.event_id),
                "sequence_number": round_obj.sequence_number,
                "deadline_at": round_obj.deadline_at.isoformat(),
                "duration_seconds": duration_seconds,
                "version": round_obj.version,
            },
        )
        self.session.add(audit)

        # Transactional outbox
        outbox = TransactionalOutbox(
            id=uuid.uuid4(),
            event_type="arena:events:rounds",
            payload_json={
                "event_id": str(round_obj.event_id),
                "round_id": str(round_obj.id),
                "action": "round.started",
                "sequence_number": round_obj.sequence_number,
                "started_at": now.isoformat(),
                "deadline_at": round_obj.deadline_at.isoformat(),
                "version": round_obj.version,
            },
            status="pending",
        )
        self.session.add(outbox)
        await self.session.flush()

        return round_obj

    async def close_round(
        self,
        round_id: uuid.UUID,
        actor_id: uuid.UUID,
        actor_roles: list[str],
        expected_version: int,
    ) -> Round:
        """Close an active or paused round, preventing further ranked input admission."""
        round_obj = await self.get_round(round_id)

        if round_obj.version != expected_version:
            raise ConflictError(
                f"Concurrent modification on round {round_id}. Expected version {expected_version}, found {round_obj.version}."
            )

        if not any(r in ("org_admin", "platform_admin") for r in actor_roles):
            raise ForbiddenError("Actor lacks required role to close competition round.")

        if round_obj.status not in ("active", "in_progress", "paused"):
            raise ConflictError(
                f"Cannot close round in state '{round_obj.status}'. Round must be active or paused."
            )

        event = await self.session.get(Event, round_obj.event_id)
        now = datetime.now(UTC)
        round_obj.ended_at = now
        round_obj.status = "completed"
        round_obj.version += 1

        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=event.organization_id if event else None,
            actor_user_id=actor_id,
            event_type="round.closed",
            target_type="round",
            target_id=str(round_obj.id),
            payload_json={
                "event_id": str(round_obj.event_id),
                "sequence_number": round_obj.sequence_number,
                "ended_at": now.isoformat(),
                "version": round_obj.version,
            },
        )
        self.session.add(audit)

        outbox = TransactionalOutbox(
            id=uuid.uuid4(),
            event_type="arena:events:rounds",
            payload_json={
                "event_id": str(round_obj.event_id),
                "round_id": str(round_obj.id),
                "action": "round.closed",
                "sequence_number": round_obj.sequence_number,
                "ended_at": now.isoformat(),
                "version": round_obj.version,
            },
            status="pending",
        )
        self.session.add(outbox)
        await self.session.flush()

        return round_obj

    async def void_round(
        self,
        round_id: uuid.UUID,
        actor_id: uuid.UUID,
        actor_roles: list[str],
        expected_version: int,
        reason: str,
    ) -> Round:
        """Void a round under material compromise policy, disqualifying associated attempts."""
        round_obj = await self.get_round(round_id)

        if round_obj.version != expected_version:
            raise ConflictError(
                f"Concurrent modification on round {round_id}. Expected version {expected_version}, found {round_obj.version}."
            )

        if "platform_admin" not in actor_roles:
            raise ForbiddenError("Platform admin role is required to void a competition round.")

        if not reason or not reason.strip():
            raise InvariantViolationError("Audited reason is required to void a competition round.")

        event = await self.session.get(Event, round_obj.event_id)
        now = datetime.now(UTC)
        round_obj.ended_at = now
        round_obj.status = "voided"
        round_obj.version += 1

        # Mark in_progress attempts as voided
        void_attempts_stmt = (
            update(RankedAttempt)
            .where(
                RankedAttempt.round_id == round_id,
                RankedAttempt.status == "in_progress",
            )
            .values(status="voided")
        )
        await self.session.execute(void_attempts_stmt)

        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=event.organization_id if event else None,
            actor_user_id=actor_id,
            event_type="round.voided",
            target_type="round",
            target_id=str(round_obj.id),
            payload_json={
                "event_id": str(round_obj.event_id),
                "sequence_number": round_obj.sequence_number,
                "reason": reason,
                "version": round_obj.version,
            },
        )
        self.session.add(audit)

        outbox = TransactionalOutbox(
            id=uuid.uuid4(),
            event_type="arena:events:rounds",
            payload_json={
                "event_id": str(round_obj.event_id),
                "round_id": str(round_obj.id),
                "action": "round.voided",
                "sequence_number": round_obj.sequence_number,
                "reason": reason,
                "version": round_obj.version,
            },
            status="pending",
        )
        self.session.add(outbox)
        await self.session.flush()

        return round_obj
