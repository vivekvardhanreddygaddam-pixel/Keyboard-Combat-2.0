"""TypeVector Arena — Celery Background Retention Tasks.

Executes scheduled data retention and compliance sweeps.
"""

import asyncio
import logging
from typing import Any

from celery import shared_task

from typevector.database import async_session_factory
from typevector.domains.operations.retention import RetentionEngine
from typevector.workers.logging_context import task_logging_wrapper

logger = logging.getLogger(__name__)


@shared_task(
    name="typevector.workers.retention_tasks.run_retention_sweep",
    max_retries=1,
)
@task_logging_wrapper("run_retention_sweep")
def run_retention_sweep(
    job_type: str,
    dry_run: bool = False,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Execute a single retention sweep policy."""

    async def _async_sweep() -> dict[str, Any]:
        async with async_session_factory() as session:
            engine = RetentionEngine(session)
            job = await engine.execute_retention_sweep(job_type=job_type, dry_run=dry_run)
            await session.commit()
            return {
                "job_id": str(job.id),
                "job_type": job.job_type,
                "records_affected": job.records_affected,
                "status": job.status,
            }

    return asyncio.run(_async_sweep())


@shared_task(
    name="typevector.workers.retention_tasks.run_daily_retention_sweep",
    max_retries=1,
)
@task_logging_wrapper("run_daily_retention_sweep")
def run_daily_retention_sweep(
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Execute standard daily retention maintenance across expired sessions and exports."""

    async def _async_daily() -> list[dict[str, Any]]:
        results = []
        async with async_session_factory() as session:
            engine = RetentionEngine(session)
            # 1. Purge expired sessions
            job1 = await engine.execute_retention_sweep("purge_expired_sessions", dry_run=False)
            results.append({"job_type": job1.job_type, "affected": job1.records_affected})
            # 2. Purge expired export files
            job2 = await engine.execute_retention_sweep("purge_expired_exports", dry_run=False)
            results.append({"job_type": job2.job_type, "affected": job2.records_affected})
            await session.commit()
        return results

    res = asyncio.run(_async_daily())
    return {"status": "completed", "results": res}
