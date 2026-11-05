"""TypeVector Arena — Celery Background Export Tasks.

Executes asynchronous data export generation with CSV formula sanitization,
and scheduled purging of expired export files per retention policy.
"""

import asyncio
import logging
import uuid
from typing import Any

from celery import shared_task

from typevector.database import async_session_factory
from typevector.domains.exports.service import ExportService
from typevector.workers.logging_context import task_logging_wrapper

logger = logging.getLogger(__name__)


@shared_task(
    name="typevector.workers.export_tasks.generate_export_job_task",
    max_retries=2,
    default_retry_delay=10,
)
@task_logging_wrapper("generate_export_job_task")
def generate_export_job_task(
    job_id_str: str,
    event_id_str: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Execute asynchronous generation of a queued export job."""
    job_id = uuid.UUID(job_id_str)
    event_id = uuid.UUID(event_id_str) if event_id_str else None

    async def _async_generate() -> dict[str, Any]:
        async with async_session_factory() as session:
            service = ExportService(session)
            job = await service.get_job(job_id)
            job.status = "processing"
            await session.flush()

            generated_job = await service.generate_export_file(
                job_id=job.id,
                organization_id=job.organization_id,
                requested_by_user_id=job.requested_by_user_id,
                export_type=job.export_type,
                event_id=event_id,
            )
            await session.commit()
            return {
                "job_id": str(generated_job.id),
                "status": generated_job.status,
                "row_count": generated_job.row_count,
                "file_path": generated_job.file_path,
            }

    return asyncio.run(_async_generate())


@shared_task(
    name="typevector.workers.export_tasks.purge_expired_exports",
    max_retries=1,
)
@task_logging_wrapper("purge_expired_exports")
def purge_expired_exports(
    retention_days: int = 7,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Periodically purge expired export files from disk."""

    async def _async_purge() -> int:
        async with async_session_factory() as session:
            service = ExportService(session)
            purged = await service.purge_expired_exports(retention_days=retention_days)
            await session.commit()
            return purged

    count = asyncio.run(_async_purge())
    return {"purged_count": count, "status": "completed"}
