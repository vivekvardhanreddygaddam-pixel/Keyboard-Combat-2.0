"""TypeVector Arena — Events Domain Service."""

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from typevector.domains.audit.models import AuditEvent
from typevector.domains.events.lifecycle import (
    FROZEN_EVENT_STATES,
    MAX_PAUSE_DURATION_SECONDS,
    TERMINAL_EVENT_STATES,
    EventStatus,
    find_transition_rule,
)
from typevector.domains.events.models import Event, EventRuleset
from typevector.domains.events.schemas import EventStatusRead
from typevector.domains.notifications.models import TransactionalOutbox
from typevector.domains.ranked_input.models import RankedAttempt
from typevector.domains.registrations.models import EventRegistration
from typevector.domains.rounds.models import ChallengePrompt, Round
from typevector.errors import (
    ConflictError,
    EntityNotFoundError,
    ForbiddenError,
    InvariantViolationError,
)


class EventService:
    """Domain service managing competition event lifecycles, rulesets, and fair pauses."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, event_id: uuid.UUID) -> Event:
        """Fetch event by UUID."""
        event = await self.session.get(Event, event_id)
        if not event:
            raise EntityNotFoundError(entity="Event", identifier=event_id)
        return event

    async def create_event(
        self,
        organization_id: uuid.UUID,
        slug: str,
        title: str,
        description: str | None = None,
        capacity: int = 100,
        is_prize_event: bool = False,
        min_accuracy_pct: float = 90.0,
        duration_seconds: int = 60,
        scoring_formula: str = "arena-score-v1",
        actor_id: uuid.UUID | None = None,
    ) -> Event:
        """Create a new competition event in DRAFT status with initial ruleset."""
        # Check slug uniqueness within organization
        slug_stmt = select(Event).where(
            Event.organization_id == organization_id,
            Event.slug == slug,
        )
        existing = (await self.session.execute(slug_stmt)).scalar_one_or_none()
        if existing:
            raise ConflictError(f"Event with slug '{slug}' already exists in this organization.")

        event = Event(
            id=uuid.uuid4(),
            organization_id=organization_id,
            slug=slug,
            title=title,
            description=description,
            status=EventStatus.DRAFT,
            capacity=capacity,
            version=1,
            is_prize_event=is_prize_event,
            ruleset_approval_status="draft_awaiting_approval",
        )
        self.session.add(event)
        await self.session.flush()

        ruleset = EventRuleset(
            id=uuid.uuid4(),
            event_id=event.id,
            version_number=1,
            ruleset_json={
                "profile": "default",
                "canonicalization": "unicode-paragraph-v1",
                "penalties": {"excess_keystroke": 1, "missed_unit": 1},
            },
            min_accuracy_pct=min_accuracy_pct,
            duration_seconds=duration_seconds,
            scoring_formula=scoring_formula,
        )
        self.session.add(ruleset)

        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=organization_id,
            actor_user_id=actor_id,
            event_type="events.created",
            target_type="event",
            target_id=str(event.id),
            payload_json={
                "slug": slug,
                "title": title,
                "capacity": capacity,
                "is_prize_event": is_prize_event,
            },
        )
        self.session.add(audit)
        return event

    async def update_draft_event(
        self,
        event_id: uuid.UUID,
        actor_id: uuid.UUID,
        title: str | None = None,
        description: str | None = None,
        capacity: int | None = None,
        is_prize_event: bool | None = None,
    ) -> Event:
        """Update an event in DRAFT status. Mutating after publication is strictly rejected."""
        event = await self.get_by_id(event_id)
        if event.status != EventStatus.DRAFT:
            raise InvariantViolationError(
                f"Cannot modify event '{event.slug}' in status '{event.status}'. "
                "Event rules are permanently immutable once published."
            )

        changes: dict[str, Any] = {}
        if title is not None and title != event.title:
            changes["title"] = {"from": event.title, "to": title}
            event.title = title
        if description is not None and description != event.description:
            changes["description"] = {"from": event.description, "to": description}
            event.description = description
        if capacity is not None and capacity != event.capacity:
            changes["capacity"] = {"from": event.capacity, "to": capacity}
            event.capacity = capacity
        if is_prize_event is not None and is_prize_event != event.is_prize_event:
            changes["is_prize_event"] = {"from": event.is_prize_event, "to": is_prize_event}
            event.is_prize_event = is_prize_event

        event.version = (event.version or 1) + 1

        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=event.organization_id,
            actor_user_id=actor_id,
            event_type="events.updated",
            target_type="event",
            target_id=str(event.id),
            payload_json={"changes": changes, "version": event.version},
        )
        self.session.add(audit)
        return event

    async def list_for_organization(
        self,
        organization_id: uuid.UUID,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Event]:
        """List all events (draft, published, live, completed) for an organization."""
        stmt = select(Event).where(Event.organization_id == organization_id)
        if status:
            stmt = stmt.where(Event.status == status)
        stmt = stmt.order_by(Event.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_published(self, limit: int = 20, offset: int = 0) -> list[Event]:
        """List published events visible to the public."""
        stmt = (
            select(Event)
            .where(
                Event.status.in_(
                    [
                        EventStatus.PUBLISHED,
                        EventStatus.REGISTRATION_OPEN,
                        EventStatus.CHECK_IN_OPEN,
                        EventStatus.READY,
                        EventStatus.LIVE,
                        EventStatus.PAUSED,
                        EventStatus.COMPLETED,
                        EventStatus.REVIEW,
                        EventStatus.RESULTS_PUBLISHED,
                        EventStatus.AMENDED,
                    ]
                )
            )
            .order_by(Event.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def is_ruleset_frozen(self, event: Event) -> bool:
        """Check whether rulesets and prompt configurations are immutable for this event."""
        return event.status in FROZEN_EVENT_STATES

    async def transition_event(
        self,
        event_id: uuid.UUID,
        target_status: EventStatus | str,
        actor_id: uuid.UUID,
        actor_roles: list[str],
        expected_version: int,
        reason: str | None = None,
    ) -> Event:
        """Execute an authoritative lifecycle transition with optimistic locking."""
        event = await self.get_by_id(event_id)
        old_status = event.status

        # 1. Optimistic Concurrency Check
        if event.version != expected_version:
            raise ConflictError(
                f"Concurrent modification detected on event {event_id}. Expected version {expected_version}, found {event.version}."
            )

        # 2. Terminal State Check
        if event.status in TERMINAL_EVENT_STATES and target_status != EventStatus.ARCHIVED:
            raise ConflictError(
                f"Cannot transition event in terminal state '{event.status}' to '{target_status}'."
            )
        if event.status == EventStatus.ARCHIVED:
            raise ConflictError("Archived events are immutable and cannot be transitioned.")

        # 3. Transition Rule Evaluation
        rule = find_transition_rule(event.status, target_status)
        if not rule:
            raise InvariantViolationError(
                f"Illegal lifecycle transition from '{event.status}' to '{target_status}'."
            )

        # 4. Role Authorization
        if not any(role in rule.allowed_roles for role in actor_roles):
            raise ForbiddenError(
                f"Actor lacks required role {rule.allowed_roles} for transition to '{target_status}'."
            )

        # 5. Reason Check
        if rule.requires_reason and (not reason or not reason.strip()):
            raise InvariantViolationError(
                f"Mandatory audited reason required when transitioning to '{target_status}'."
            )

        # 6. Specific Preconditions
        if target_status == EventStatus.PUBLISHED:
            # Must have at least 1 ruleset
            ruleset_stmt = select(EventRuleset).where(EventRuleset.event_id == event_id)
            rulesets = (await self.session.execute(ruleset_stmt)).scalars().all()
            if not rulesets:
                raise InvariantViolationError(
                    "Cannot publish event without at least one configured ruleset."
                )

            # Must have at least 1 round with an active prompt
            rounds_stmt = select(Round).where(Round.event_id == event_id)
            rounds = (await self.session.execute(rounds_stmt)).scalars().all()
            if not rounds:
                raise InvariantViolationError(
                    "Cannot publish event without at least one configured competition round."
                )

            prompts_stmt = select(ChallengePrompt).where(
                ChallengePrompt.event_id == event_id, ChallengePrompt.is_active.is_(True)
            )
            prompts = (await self.session.execute(prompts_stmt)).scalars().all()
            if not prompts:
                raise InvariantViolationError(
                    "Cannot publish event without at least one active challenge prompt."
                )

        if target_status == EventStatus.LIVE:
            # Automated no-show flagging for confirmed registrations without check-in
            no_show_stmt = (
                update(EventRegistration)
                .where(
                    EventRegistration.event_id == event_id,
                    EventRegistration.status == "confirmed",
                    EventRegistration.checked_in_at.is_(None),
                )
                .values(status="no_show")
            )
            await self.session.execute(no_show_stmt)

        # 7. Apply State Mutation
        event.status = str(target_status)
        if reason:
            event.incident_reason = reason
        event.version += 1

        # 8. Append Audit Event
        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=event.organization_id,
            actor_user_id=actor_id,
            event_type="event.lifecycle_transition",
            target_type="event",
            target_id=str(event.id),
            payload_json={
                "from_status": old_status,
                "to_status": str(target_status),
                "version": event.version,
                "reason": reason,
            },
        )
        self.session.add(audit)

        # 9. Transactional Outbox for Realtime Fanout
        outbox = TransactionalOutbox(
            id=uuid.uuid4(),
            event_type="arena:events:lifecycle",
            payload_json={
                "event_id": str(event.id),
                "from_status": old_status,
                "to_status": str(target_status),
                "version": event.version,
                "reason": reason,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            status="pending",
        )
        self.session.add(outbox)
        await self.session.flush()

        return event

    async def pause_event(
        self,
        event_id: uuid.UUID,
        actor_id: uuid.UUID,
        actor_roles: list[str],
        expected_version: int,
        reason: str,
    ) -> Event:
        """Pause a live competition event and uniformly freeze all active rounds."""
        event = await self.get_by_id(event_id)
        if event.status != EventStatus.LIVE:
            raise ConflictError(
                f"Cannot pause event in state '{event.status}'. Event must be LIVE."
            )

        if event.version != expected_version:
            raise ConflictError(
                f"Concurrent modification on event {event_id}. Expected version {expected_version}, found {event.version}."
            )

        if not any(r in ("org_admin", "platform_admin") for r in actor_roles):
            raise ForbiddenError("Actor lacks required role to pause competition event.")

        now = datetime.now(UTC)
        old_status = event.status
        event.status = EventStatus.PAUSED
        event.pause_started_at = now
        event.incident_reason = reason
        event.version += 1

        # Pause all active rounds uniformly
        active_rounds_stmt = select(Round).where(
            Round.event_id == event_id,
            Round.status.in_(["active", "in_progress"]),
        )
        res = await self.session.execute(active_rounds_stmt)
        for rnd in res.scalars().all():
            rnd.status = "paused"
            rnd.pause_started_at = now
            rnd.version += 1

        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=event.organization_id,
            actor_user_id=actor_id,
            event_type="event.paused",
            target_type="event",
            target_id=str(event.id),
            payload_json={
                "reason": reason,
                "version": event.version,
                "pause_started_at": now.isoformat(),
            },
        )
        self.session.add(audit)

        outbox = TransactionalOutbox(
            id=uuid.uuid4(),
            event_type="arena:events:lifecycle",
            payload_json={
                "event_id": str(event.id),
                "from_status": old_status,
                "to_status": EventStatus.PAUSED,
                "version": event.version,
                "reason": reason,
                "pause_started_at": now.isoformat(),
                "timestamp": now.isoformat(),
            },
            status="pending",
        )
        self.session.add(outbox)
        await self.session.flush()

        return event

    async def resume_event(
        self,
        event_id: uuid.UUID,
        actor_id: uuid.UUID,
        actor_roles: list[str],
        expected_version: int,
        reason: str,
    ) -> Event:
        """Resume a paused competition event, applying uniform deadline adjustments to all active rounds and attempts."""
        event = await self.get_by_id(event_id)
        if event.status != EventStatus.PAUSED:
            raise ConflictError(
                f"Cannot resume event in state '{event.status}'. Event must be PAUSED."
            )

        if event.version != expected_version:
            raise ConflictError(
                f"Concurrent modification on event {event_id}. Expected version {expected_version}, found {event.version}."
            )

        if not any(r in ("org_admin", "platform_admin") for r in actor_roles):
            raise ForbiddenError("Actor lacks required role to resume competition event.")

        now = datetime.now(UTC)
        if not event.pause_started_at:
            delta_seconds = 0
        else:
            delta_seconds = max(0, int((now - event.pause_started_at).total_seconds()))

        # Check maximum pause fairness threshold
        new_total_pause = (event.total_pause_duration_seconds or 0) + delta_seconds
        if new_total_pause > MAX_PAUSE_DURATION_SECONDS:
            raise InvariantViolationError(
                f"Total pause duration ({new_total_pause}s) exceeds tournament maximum limit of {MAX_PAUSE_DURATION_SECONDS}s. Event must be cancelled or voided under published fairness policy."
            )

        event.total_pause_duration_seconds = new_total_pause
        event.pause_started_at = None
        event.status = EventStatus.LIVE
        event.incident_reason = reason
        event.version += 1

        # 1. Uniformly extend paused rounds
        paused_rounds_stmt = select(Round).where(
            Round.event_id == event_id,
            Round.status == "paused",
        )
        rounds_res = await self.session.execute(paused_rounds_stmt)
        for rnd in rounds_res.scalars().all():
            rnd.total_pause_duration_seconds = (
                rnd.total_pause_duration_seconds or 0
            ) + delta_seconds
            if rnd.deadline_at:
                rnd.deadline_at = rnd.deadline_at + timedelta(seconds=delta_seconds)
            rnd.pause_started_at = None
            rnd.status = "active"
            rnd.version += 1

        # 2. Uniformly extend active participant attempts
        attempts_stmt = select(RankedAttempt).where(
            RankedAttempt.event_id == event_id,
            RankedAttempt.status == "in_progress",
        )
        attempts_res = await self.session.execute(attempts_stmt)
        for att in attempts_res.scalars().all():
            if att.deadline_at:
                att.deadline_at = att.deadline_at + timedelta(seconds=delta_seconds)

        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=event.organization_id,
            actor_user_id=actor_id,
            event_type="event.resumed",
            target_type="event",
            target_id=str(event.id),
            payload_json={
                "reason": reason,
                "delta_seconds": delta_seconds,
                "total_pause_duration_seconds": new_total_pause,
                "version": event.version,
            },
        )
        self.session.add(audit)

        outbox = TransactionalOutbox(
            id=uuid.uuid4(),
            event_type="arena:events:lifecycle",
            payload_json={
                "event_id": str(event.id),
                "from_status": EventStatus.PAUSED,
                "to_status": EventStatus.LIVE,
                "version": event.version,
                "reason": reason,
                "delta_seconds": delta_seconds,
                "total_pause_duration_seconds": new_total_pause,
                "timestamp": now.isoformat(),
            },
            status="pending",
        )
        self.session.add(outbox)
        await self.session.flush()

        return event

    async def check_in_participant(
        self,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> EventRegistration:
        """Check in a confirmed participant during the authorized check-in window."""
        event = await self.get_by_id(event_id)
        if event.status not in (EventStatus.CHECK_IN_OPEN, EventStatus.READY):
            raise ConflictError(
                f"Check-in is not permitted when event is in state '{event.status}'."
            )

        stmt = select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == user_id,
        )
        res = await self.session.execute(stmt)
        reg = res.scalar_one_or_none()
        if not reg:
            raise EntityNotFoundError(
                entity="Registration", identifier=f"event={event_id}, user={user_id}"
            )

        if reg.status not in ("confirmed", "checked_in"):
            raise ConflictError(
                f"Cannot check in participant with registration status '{reg.status}'."
            )

        if not reg.checked_in_at:
            reg.checked_in_at = datetime.now(UTC)
            reg.status = "checked_in"

            audit = AuditEvent(
                id=uuid.uuid4(),
                organization_id=event.organization_id,
                actor_user_id=user_id,
                event_type="participant.checked_in",
                target_type="event_registration",
                target_id=str(reg.id),
                payload_json={"event_id": str(event_id), "user_id": str(user_id)},
            )
            self.session.add(audit)
            await self.session.flush()

        return reg

    async def mark_participant_ready(
        self,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> EventRegistration:
        """Signal participant readiness for the upcoming competition round."""
        event = await self.get_by_id(event_id)
        if event.status not in (EventStatus.CHECK_IN_OPEN, EventStatus.READY):
            raise ConflictError(
                f"Readiness signal is not permitted when event is in state '{event.status}'."
            )

        stmt = select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == user_id,
        )
        res = await self.session.execute(stmt)
        reg = res.scalar_one_or_none()
        if not reg:
            raise EntityNotFoundError(
                entity="Registration", identifier=f"event={event_id}, user={user_id}"
            )

        if not reg.checked_in_at:
            raise ConflictError("Participant must complete check-in before signaling readiness.")

        if not reg.is_ready:
            reg.is_ready = True
            reg.ready_at = datetime.now(UTC)

            audit = AuditEvent(
                id=uuid.uuid4(),
                organization_id=event.organization_id,
                actor_user_id=user_id,
                event_type="participant.ready",
                target_type="event_registration",
                target_id=str(reg.id),
                payload_json={"event_id": str(event_id), "user_id": str(user_id)},
            )
            self.session.add(audit)
            await self.session.flush()

        return reg

    async def get_event_status_read(self, event_id: uuid.UUID) -> EventStatusRead:
        """Get live status snapshot with server timestamp and active round details."""
        event = await self.get_by_id(event_id)

        # Find active round if any
        stmt = (
            select(Round)
            .where(
                Round.event_id == event_id,
                Round.status.in_(["active", "in_progress", "paused"]),
            )
            .order_by(Round.sequence_number.asc())
            .limit(1)
        )
        active_round = (await self.session.execute(stmt)).scalar_one_or_none()

        return EventStatusRead(
            event_id=event.id,
            status=event.status,
            version=event.version,
            is_paused=event.status == EventStatus.PAUSED,
            pause_started_at=event.pause_started_at,
            total_pause_duration_seconds=event.total_pause_duration_seconds,
            incident_reason=event.incident_reason,
            active_round_id=active_round.id if active_round else None,
            round_deadline_at=active_round.deadline_at if active_round else None,
            server_time_ms=int(time.time() * 1000),
        )
