"""TypeVector Arena — Notifications Domain Service."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from typevector.domains.notifications.models import NotificationDelivery, TransactionalOutbox
from typevector.domains.notifications.providers import (
    NotificationProvider,
    get_notification_provider,
)
from typevector.errors import EntityNotFoundError

logger = logging.getLogger(__name__)


class NotificationService:
    """Domain service managing transactional outbox records and notification delivery pipelines."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue_outbox_event(
        self, event_type: str, payload: dict[str, Any]
    ) -> TransactionalOutbox:
        """Enqueue an event to the PostgreSQL Transactional Outbox within the current transaction."""
        outbox = TransactionalOutbox(
            id=uuid.uuid4(),
            event_type=event_type,
            payload_json=payload,
            status="pending",
            retry_count=0,
            created_at=datetime.now(UTC),
        )
        self.session.add(outbox)
        return outbox

    async def create_notification_delivery(
        self,
        user_id: uuid.UUID,
        notification_type: str,
        recipient: str,
    ) -> NotificationDelivery:
        """Queue a notification delivery record for asynchronous worker dispatch."""
        delivery = NotificationDelivery(
            id=uuid.uuid4(),
            user_id=user_id,
            notification_type=notification_type,
            recipient=recipient,
            status="queued",
            created_at=datetime.now(UTC),
        )
        self.session.add(delivery)
        return delivery

    async def deliver_notification(
        self,
        delivery_id: uuid.UUID,
        subject: str,
        text_body: str,
        html_body: str | None = None,
        provider: NotificationProvider | None = None,
    ) -> NotificationDelivery:
        """Execute delivery of a queued notification through the configured provider."""
        stmt = select(NotificationDelivery).where(NotificationDelivery.id == delivery_id)
        res = await self.session.execute(stmt)
        delivery = res.scalar_one_or_none()
        if not delivery:
            raise EntityNotFoundError(entity="NotificationDelivery", identifier=delivery_id)

        active_provider = provider or get_notification_provider()

        result = await active_provider.send_email(
            to_email=delivery.recipient,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

        now = datetime.now(UTC)
        if result.success:
            delivery.status = "sent"
            delivery.sent_at = now
            delivery.error_message = None
        else:
            delivery.status = "failed"
            delivery.error_message = result.error_message or "Unknown provider delivery failure"

        await self.session.flush()
        return delivery

    async def list_user_deliveries(
        self, user_id: uuid.UUID, limit: int = 50
    ) -> list[NotificationDelivery]:
        """Fetch historical notification delivery records for a specific user."""
        stmt = (
            select(NotificationDelivery)
            .where(NotificationDelivery.user_id == user_id)
            .order_by(NotificationDelivery.created_at.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
