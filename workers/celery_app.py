"""TypeVector Arena — Celery Worker Application Configuration."""

from celery import Celery

from typevector.config import settings

celery_app = Celery(
    "typevector",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Enforce secure configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes hard limit
    task_soft_time_limit=240,  # 4 minutes soft limit
    worker_prefetch_multiplier=1,  # Prevent task hoarding
    task_acks_late=True,  # Guarantee at-least-once delivery
    task_reject_on_worker_lost=True,
)

# Auto-discover tasks across domain modules
celery_app.autodiscover_tasks(["workers.tasks"])
