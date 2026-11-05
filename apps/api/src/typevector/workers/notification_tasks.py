"""TypeVector Arena — Celery Background Notification Tasks.

Handles asynchronous transactional email and notification delivery.
Guarantees bounded retries with exponential backoff and structured error recording.
"""

import asyncio
import logging
import uuid
from typing import Any

from celery import shared_task

from typevector.database import async_session_factory
from typevector.domains.notifications.service import NotificationService
from typevector.workers.logging_context import task_logging_wrapper

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="typevector.workers.notification_tasks.send_notification_delivery",
    max_retries=3,
    default_retry_delay=30,
)
@task_logging_wrapper("send_notification_delivery")
def send_notification_delivery(
    self: Any,
    delivery_id_str: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Execute asynchronous notification delivery with bounded retries."""
    delivery_id = uuid.UUID(delivery_id_str)

    async def _async_deliver() -> dict[str, Any]:
        async with async_session_factory() as session:
            service = NotificationService(session)
            delivery = await service.deliver_notification(
                delivery_id=delivery_id,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
            )
            await session.commit()
            return {
                "delivery_id": str(delivery.id),
                "status": delivery.status,
                "sent_at": delivery.sent_at.isoformat() if delivery.sent_at else None,
                "error": delivery.error_message,
            }

    try:
        return asyncio.run(_async_deliver())
    except Exception as exc:
        logger.warning(
            "Notification delivery %s failed: %s (attempt %d/3)",
            delivery_id_str,
            exc,
            self.request.retries + 1,
        )
        raise self.retry(exc=exc, countdown=min(60 * (2**self.request.retries), 300)) from exc
