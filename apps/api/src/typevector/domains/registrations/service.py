"""TypeVector Arena — Registrations Domain Service."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from typevector.domains.audit.models import AuditEvent
from typevector.domains.events.models import Event
from typevector.domains.identity.models import IdentityClaim, User
from typevector.domains.notifications.models import TransactionalOutbox
from typevector.domains.organizations.models import OrganizationMember
from typevector.domains.registrations.models import EventRegistration
from typevector.domains.registrations.schemas import EventCapacityStatus
from typevector.errors import (
    ConflictError,
    EntityNotFoundError,
    ForbiddenError,
    InvariantViolationError,
)


class RegistrationService:
    """Domain service managing race-safe event admissions, capacity locking, and cancellations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_registration(self, event_id: uuid.UUID, user_id: uuid.UUID) -> EventRegistration:
        """Fetch registration for user in event."""
        stmt = select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        reg = result.scalar_one_or_none()
        if not reg:
            raise EntityNotFoundError(
                entity="Registration",
                identifier=f"event={event_id}, user={user_id}",
            )
        return reg

    async def get_capacity_status(self, event_id: uuid.UUID) -> EventCapacityStatus:
        """Compute live confirmed count and capacity status for an event."""
        event = await self.session.get(Event, event_id)
        if not event:
            raise EntityNotFoundError(entity="Event", identifier=event_id)

        count_stmt = (
            select(func.count())
            .select_from(EventRegistration)
            .where(
                EventRegistration.event_id == event_id,
                EventRegistration.status == "confirmed",
            )
        )
        count_res = await self.session.execute(count_stmt)
        confirmed_count = count_res.scalar() or 0

        return EventCapacityStatus(
            event_id=event.id,
            capacity=event.capacity,
            confirmed_count=confirmed_count,
            is_full=confirmed_count >= event.capacity,
            status=event.status,
        )

    async def register_for_event(
        self,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> tuple[EventRegistration, bool]:
        """Atomically register a participant for an event with capacity locking.

        Enforces:
        1. Natural Idempotency: If already confirmed, returns existing record (created=False).
        2. Lifecycle Gate: Event must be in 'registration_open' status.
        3. Race-Safe Atomic Capacity: SELECT ... FOR UPDATE locks the event record.
        4. Overbooking Prevention: Rejects with 409 Conflict if confirmed count >= capacity.
        """
        # 1. Natural Idempotency check
        existing_stmt = select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == user_id,
        )
        existing_res = await self.session.execute(existing_stmt)
        existing = existing_res.scalar_one_or_none()

        if existing and existing.status == "confirmed":
            return existing, False

        # 2. Atomic Event Lock (SELECT ... FOR UPDATE)
        event_stmt = select(Event).where(Event.id == event_id).with_for_update()
        event_res = await self.session.execute(event_stmt)
        event = event_res.scalar_one_or_none()

        if not event:
            raise EntityNotFoundError(entity="Event", identifier=event_id)

        if event.status != "registration_open":
            raise InvariantViolationError(
                f"Registration is not open for this event (current status: '{event.status}').",
                code="REGISTRATION_CLOSED",
            )

        # 3. Check live capacity
        count_stmt = (
            select(func.count())
            .select_from(EventRegistration)
            .where(
                EventRegistration.event_id == event_id,
                EventRegistration.status == "confirmed",
            )
        )
        count_res = await self.session.execute(count_stmt)
        confirmed_count = count_res.scalar() or 0

        if confirmed_count >= event.capacity:
            raise ConflictError(
                f"Event capacity limit of {event.capacity} participants has been reached.",
                code="CAPACITY_EXCEEDED",
            )

        now = datetime.now(UTC)

        # 4. Create or Reactivate registration
        if existing:
            existing.status = "confirmed"
            existing.confirmed_at = now
            existing.cancelled_at = None
            registration = existing
            created = False
        else:
            registration = EventRegistration(
                event_id=event.id,
                user_id=user_id,
                status="confirmed",
                registered_at=now,
                confirmed_at=now,
            )
            self.session.add(registration)
            created = True

        await self.session.flush()

        # 5. Outbox Event & Audit Trail
        outbox = TransactionalOutbox(
            event_type="event_registration.confirmed",
            payload_json={
                "registration_id": str(registration.id),
                "event_id": str(event.id),
                "user_id": str(user_id),
                "confirmed_at": now.isoformat(),
            },
        )
        self.session.add(outbox)

        audit = AuditEvent(
            actor_user_id=user_id,
            organization_id=event.organization_id,
            event_type="event_registration.confirmed",
            target_type="EventRegistration",
            target_id=str(registration.id),
            payload_json={
                "event_id": str(event.id),
                "user_id": str(user_id),
                "capacity": event.capacity,
                "slot_number": confirmed_count + 1,
            },
        )
        self.session.add(audit)

        return registration, created

    async def cancel_registration(
        self,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
        actor_id: uuid.UUID,
        is_platform_admin: bool = False,
    ) -> EventRegistration:
        """Cancel an event registration and release reserved capacity."""
        registration = await self.get_registration(event_id, user_id)

        if registration.status == "cancelled":
            return registration

        # IDOR Authorization Guard: Only the participant or an organization manager can cancel
        if actor_id != user_id and not is_platform_admin:
            event = await self.session.get(Event, event_id)
            if not event:
                raise EntityNotFoundError(entity="Event", identifier=event_id)

            member_stmt = select(OrganizationMember).where(
                OrganizationMember.organization_id == event.organization_id,
                OrganizationMember.user_id == actor_id,
                OrganizationMember.role.in_(["owner", "organizer"]),
            )
            member_res = await self.session.execute(member_stmt)
            if not member_res.scalar_one_or_none():
                raise ForbiddenError("You are not authorized to cancel this registration.")

        now = datetime.now(UTC)
        registration.status = "cancelled"
        registration.cancelled_at = now

        # Outbox & Audit
        outbox = TransactionalOutbox(
            event_type="event_registration.cancelled",
            payload_json={
                "registration_id": str(registration.id),
                "event_id": str(event_id),
                "user_id": str(user_id),
                "cancelled_at": now.isoformat(),
            },
        )
        self.session.add(outbox)

        audit = AuditEvent(
            actor_user_id=actor_id,
            event_type="event_registration.cancelled",
            target_type="EventRegistration",
            target_id=str(registration.id),
            payload_json={"event_id": str(event_id), "user_id": str(user_id)},
        )
        self.session.add(audit)

        return registration

    async def list_user_registrations(self, user_id: uuid.UUID) -> list[EventRegistration]:
        """Fetch all event registrations for a user."""
        stmt = (
            select(EventRegistration)
            .where(EventRegistration.user_id == user_id)
            .order_by(EventRegistration.registered_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_roster_for_event(self, event_id: uuid.UUID) -> list[dict[str, object]]:
        """Fetch full participant roster for an event with identity claims and check-in status."""
        stmt = (
            select(EventRegistration, User, IdentityClaim)
            .join(User, EventRegistration.user_id == User.id)
            .outerjoin(IdentityClaim, User.id == IdentityClaim.user_id)
            .where(EventRegistration.event_id == event_id)
            .order_by(EventRegistration.registered_at.asc())
        )
        res = await self.session.execute(stmt)
        rows = res.all()

        roster: list[dict[str, object]] = []
        for reg, user, claim in rows:
            roster.append(
                {
                    "registration_id": reg.id,
                    "event_id": reg.event_id,
                    "user_id": reg.user_id,
                    "display_name": user.display_name,
                    "email": user.email,
                    "status": reg.status,
                    "registered_at": reg.registered_at,
                    "confirmed_at": reg.confirmed_at,
                    "cancelled_at": reg.cancelled_at,
                    "checked_in_at": reg.checked_in_at,
                    "is_ready": reg.is_ready,
                    "ready_at": reg.ready_at,
                    "is_verified": claim.status == "verified" if claim else False,
                    "institution_name": claim.claim_value if claim else None,
                }
            )
        return roster

    async def organizer_update_status(
        self,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
        target_status: str,
        actor_id: uuid.UUID,
        reason: str,
    ) -> EventRegistration:
        """Allow authorized organizer to perform manual status correction on a registration."""
        allowed_statuses = {"confirmed", "checked_in", "no_show", "cancelled"}
        if target_status not in allowed_statuses:
            raise InvariantViolationError(
                f"Invalid target status '{target_status}'. Must be one of {allowed_statuses}."
            )

        reg = await self.get_registration(event_id, user_id)
        old_status = reg.status
        now = datetime.now(UTC)

        reg.status = target_status
        if target_status == "confirmed" and not reg.confirmed_at:
            reg.confirmed_at = now
        elif target_status == "checked_in":
            reg.checked_in_at = now
        elif target_status == "cancelled":
            reg.cancelled_at = now

        audit = AuditEvent(
            actor_user_id=actor_id,
            event_type="roster.status_corrected",
            target_type="EventRegistration",
            target_id=str(reg.id),
            payload_json={
                "event_id": str(event_id),
                "user_id": str(user_id),
                "from_status": old_status,
                "to_status": target_status,
                "reason": reason,
            },
        )
        self.session.add(audit)
        return reg
