"""TypeVector Arena — Celery Application Configuration.

Configures Celery with Redis broker and result backend.
Enforces JSON-only serialization, late acknowledgments for worker crash resilience,
bounded timeouts, dedicated queue routing, and structured task discovery.
Pickle and untrusted serialization protocols are strictly prohibited.
"""

import logging
from typing import Final

from celery import Celery
from celery.signals import worker_ready, worker_shutdown

from typevector.config import settings

logger = logging.getLogger(__name__)

# Dedicated queue names for explicit priority and resource isolation
QUEUE_OUTBOX: Final[str] = "outbox"
QUEUE_NOTIFICATIONS: Final[str] = "notifications"
QUEUE_EXPORTS: Final[str] = "exports"
QUEUE_RETENTION: Final[str] = "retention"
QUEUE_DEFAULT: Final[str] = "default"

celery_app = Celery(
    "typevector",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "typevector.workers.outbox_tasks",
        "typevector.workers.notification_tasks",
        "typevector.workers.export_tasks",
        "typevector.workers.retention_tasks",
    ],
)

celery_app.conf.update(
    # Serialization & Security: JSON ONLY (CWE-502 Defense: Never permit pickle)
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    event_serializer="json",
    # Timezone & Timekeeping
    timezone="UTC",
    enable_utc=True,
    # Worker Crash Resilience & Idempotency Safeguards
    # acks_late=True ensures the message remains in broker until task completes.
    # If a worker crashes mid-task, the broker redelivers the message.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Fair dispatch: prefetch 1 task per worker concurrency slot
    worker_prefetch_multiplier=1,
    # Execution Time Limits (hard kill at 300s, soft warning at 240s)
    task_time_limit=300,
    task_soft_time_limit=240,
    # Result Storage TTL (1 hour)
    result_expires=3600,
    # Task Queue Routing
    task_routes={
        "typevector.workers.outbox_tasks.*": {"queue": QUEUE_OUTBOX},
        "typevector.workers.notification_tasks.*": {"queue": QUEUE_NOTIFICATIONS},
        "typevector.workers.export_tasks.*": {"queue": QUEUE_EXPORTS},
        "typevector.workers.retention_tasks.*": {"queue": QUEUE_RETENTION},
        "*": {"queue": QUEUE_DEFAULT},
    },
    # Celery Beat Scheduled Tasks
    beat_schedule={
        "outbox-dispatcher-sweep": {
            "task": "typevector.workers.outbox_tasks.sweep_pending_outbox",
            "schedule": 10.0,  # Run every 10 seconds
            "options": {"queue": QUEUE_OUTBOX},
        },
        "reconcile-stuck-outbox": {
            "task": "typevector.workers.outbox_tasks.reconcile_stuck_outbox",
            "schedule": 60.0,  # Run every 60 seconds
            "options": {"queue": QUEUE_OUTBOX},
        },
        "retention-daily-sweep": {
            "task": "typevector.workers.retention_tasks.run_daily_retention_sweep",
            "schedule": 86400.0,  # Run once every 24 hours
            "options": {"queue": QUEUE_RETENTION},
        },
        "purge-expired-exports": {
            "task": "typevector.workers.export_tasks.purge_expired_exports",
            "schedule": 3600.0,  # Run once an hour
            "options": {"queue": QUEUE_EXPORTS},
        },
    },
)


@worker_ready.connect
def on_worker_ready(sender: object, **kwargs: object) -> None:
    """Log worker readiness without exposing sensitive broker credentials."""
    logger.info("TypeVector Celery worker is ready and accepting tasks.")


@worker_shutdown.connect
def on_worker_shutdown(sender: object, **kwargs: object) -> None:
    """Log graceful worker shutdown."""
    logger.info("TypeVector Celery worker is shutting down gracefully.")
