"""TypeVector Arena — Data Retention and Compliance Purge Engine.

Enforces strict, auditable data lifecycle management:
1. Retention rules must be explicit and reviewed; arbitrary deletions are strictly prohibited.
2. Identity (User), competition evidence (RankedAttempt, ParticipantScore, ChallengePrompt),
   published results, and audit trails are PERMANENT and CANNOT be purged by automated retention.
3. Every sweep supports dry-run estimation and records an authoritative RetentionJob record.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from typevector.domains.audit.models import AuditEvent
from typevector.domains.identity.models import IdentityClaim, UserSession
from typevector.domains.operations.models import RetentionJob
from typevector.errors import InvariantViolationError

logger = logging.getLogger(__name__)

# Non-negotiable permanent records that must NEVER be deleted by retention jobs
PROTECTED_ENTITIES: Final[frozenset[str]] = frozenset(
    {
        "User",
        "UserCredential",
        "ParticipantScore",
        "RankedAttempt",
        "RankedInputBatch",
        "ChallengePrompt",
        "PublishedResult",
        "PublishedRankRow",
        "AuditEvent",
    }
)

VALID_JOB_TYPES: Final[frozenset[str]] = frozenset(
    {
        "purge_expired_sessions",
        "prune_unverified_claims",
        "purge_expired_exports",
    }
)


class RetentionEngine:
    """Executes reviewed retention policies with explicit guards and dry-run capabilities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def execute_retention_sweep(
        self,
        job_type: str,
        dry_run: bool = False,
        actor_id: uuid.UUID | None = None,
    ) -> RetentionJob:
        """Execute a configured retention job or dry-run assessment."""
        if job_type not in VALID_JOB_TYPES:
            raise InvariantViolationError(
                f"Invalid or unreviewed retention job_type '{job_type}'. "
                f"Allowed job types: {sorted(VALID_JOB_TYPES)}"
            )

        # Enforce that no protected entity is targeted
        for protected in PROTECTED_ENTITIES:
            if protected.lower() in job_type.lower():
                raise InvariantViolationError(
                    f"Retention policy violation: '{protected}' is a protected permanent "
                    "competition/audit class and cannot be targeted for automated deletion."
                )

        started_at = datetime.now(UTC)
        records_affected = 0

        if job_type == "purge_expired_sessions":
            records_affected = await self._handle_expired_sessions(dry_run=dry_run)
        elif job_type == "prune_unverified_claims":
            records_affected = await self._handle_unverified_claims(dry_run=dry_run)
        elif job_type == "purge_expired_exports":
            records_affected = await self._handle_expired_exports(dry_run=dry_run)

        job_status = "dry_run" if dry_run else "completed"
        completed_at = datetime.now(UTC)

        retention_job = RetentionJob(
            id=uuid.uuid4(),
            job_type=f"{job_type}:dry_run" if dry_run else job_type,
            records_affected=records_affected,
            status=job_status,
            started_at=started_at,
            completed_at=completed_at,
        )
        self.session.add(retention_job)

        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=None,
            actor_user_id=actor_id,
            event_type="retention.sweep_executed",
            target_type="retention_job",
            target_id=str(retention_job.id),
            payload_json={
                "job_type": job_type,
                "dry_run": dry_run,
                "records_affected": records_affected,
            },
        )
        self.session.add(audit)
        await self.session.flush()

        logger.info(
            "Retention sweep '%s' completed [dry_run=%s] records_affected=%d",
            job_type,
            dry_run,
            records_affected,
        )
        return retention_job

    async def _handle_expired_sessions(self, dry_run: bool) -> int:
        """Purge UserSession records whose TTL has elapsed."""
        now = datetime.now(UTC)
        count_stmt = select(func.count(UserSession.id)).where(UserSession.expires_at < now)
        count_res = await self.session.execute(count_stmt)
        count = count_res.scalar_one() or 0

        if not dry_run and count > 0:
            del_stmt = delete(UserSession).where(UserSession.expires_at < now)
            await self.session.execute(del_stmt)

        return count

    async def _handle_unverified_claims(self, dry_run: bool) -> int:
        """Prune unverified IdentityClaim records older than 90 days."""
        threshold = datetime.now(UTC) - timedelta(days=90)
        count_stmt = select(func.count(IdentityClaim.id)).where(
            IdentityClaim.status == "pending",
            IdentityClaim.created_at < threshold,
        )
        count_res = await self.session.execute(count_stmt)
        count = count_res.scalar_one() or 0

        if not dry_run and count > 0:
            del_stmt = delete(IdentityClaim).where(
                IdentityClaim.status == "pending",
                IdentityClaim.created_at < threshold,
            )
            await self.session.execute(del_stmt)

        return count

    async def _handle_expired_exports(self, dry_run: bool) -> int:
        """Prune physical export files older than 7 days."""
        from typevector.domains.exports.service import ExportService

        export_svc = ExportService(self.session)
        if dry_run:
            from typevector.domains.exports.models import ExportJob

            threshold = datetime.now(UTC) - timedelta(days=7)
            stmt = select(func.count(ExportJob.id)).where(
                ExportJob.status.in_(["ready", "completed"]),
                ExportJob.completed_at < threshold,
            )
            res = await self.session.execute(stmt)
            return res.scalar_one() or 0

        return await export_svc.purge_expired_exports(retention_days=7)
