"""TypeVector Arena — Audit Domain Service."""

import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from typevector.domains.audit.models import AuditEvent

SENSITIVE_AUDIT_KEYS = {
    "password",
    "secret",
    "token",
    "hash",
    "session_token",
    "private_key",
    "cookie",
    "credential",
}


def redact_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Recursively scrub sensitive credential and auth token keys from audit payloads."""
    if not payload or not isinstance(payload, dict):
        return {}
    redacted: dict[str, Any] = {}
    for k, v in payload.items():
        if any(sensitive in k.lower() for sensitive in SENSITIVE_AUDIT_KEYS):
            redacted[k] = "[REDACTED]"
        elif isinstance(v, dict):
            redacted[k] = redact_payload(v)
        else:
            redacted[k] = v
    return redacted


class AuditService:
    """Domain service managing the append-only security and operational audit trail."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_event(
        self,
        event_type: str,
        target_type: str,
        target_id: str,
        payload: dict[str, Any],
        actor_user_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        ip_address: str | None = None,
    ) -> AuditEvent:
        """Append an unmodifiable audit event."""
        event = AuditEvent(
            event_type=event_type,
            target_type=target_type,
            target_id=target_id,
            payload_json=payload,
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            ip_address=ip_address,
        )
        self.session.add(event)
        return event

    async def list_recent(self, limit: int = 50) -> list[AuditEvent]:
        """Fetch most recent audit records with redacted payloads."""
        stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        events = list(result.scalars().all())
        for e in events:
            e.payload_json = redact_payload(e.payload_json)
        return events

    async def search_events(
        self,
        organization_id: uuid.UUID | None = None,
        event_type: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        actor_user_id: uuid.UUID | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditEvent]:
        """Filter audit trail with redactions and scoping."""
        stmt = select(AuditEvent)
        if organization_id:
            stmt = stmt.where(AuditEvent.organization_id == organization_id)
        if event_type:
            stmt = stmt.where(AuditEvent.event_type == event_type)
        if target_type:
            stmt = stmt.where(AuditEvent.target_type == target_type)
        if target_id:
            stmt = stmt.where(AuditEvent.target_id == target_id)
        if actor_user_id:
            stmt = stmt.where(AuditEvent.actor_user_id == actor_user_id)
        if query:
            stmt = stmt.where(
                or_(
                    AuditEvent.event_type.ilike(f"%{query}%"),
                    AuditEvent.target_id.ilike(f"%{query}%"),
                    AuditEvent.target_type.ilike(f"%{query}%"),
                )
            )

        stmt = stmt.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        events = list(result.scalars().all())
        for e in events:
            e.payload_json = redact_payload(e.payload_json)
        return events
