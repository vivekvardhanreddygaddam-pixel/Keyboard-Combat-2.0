"""TypeVector Arena — Exports Domain Service."""

import csv
import io
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from typevector.domains.audit.models import AuditEvent
from typevector.domains.events.models import Event
from typevector.domains.exports.models import ExportJob
from typevector.domains.identity.models import User
from typevector.domains.registrations.models import EventRegistration
from typevector.domains.results.models import PublishedResult
from typevector.errors import EntityNotFoundError, ForbiddenError, InvariantViolationError

logger = logging.getLogger(__name__)


def sanitize_csv_value(val: object) -> str:
    """Sanitize CSV cells against spreadsheet formula injection (CWE-1236).

    Prefixes '=', '+', '-', '@', '\t', '\r' with a single quote to prevent
    automatic formula execution in spreadsheet software.
    """
    if val is None:
        return ""
    s = str(val).strip()
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


class ExportService:
    """Domain service managing asynchronous data export requests, CSV sanitization, and lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.export_dir = Path("data/exports")
        self.export_dir.mkdir(parents=True, exist_ok=True)

    async def get_job(self, job_id: uuid.UUID) -> ExportJob:
        """Fetch export job status."""
        job = await self.session.get(ExportJob, job_id)
        if not job:
            raise EntityNotFoundError(entity="ExportJob", identifier=job_id)
        return job

    async def list_org_jobs(self, org_id: uuid.UUID) -> list[ExportJob]:
        """List exports requested by an organization."""
        stmt = (
            select(ExportJob)
            .where(ExportJob.organization_id == org_id)
            .order_by(ExportJob.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def queue_export_job(
        self,
        organization_id: uuid.UUID,
        requested_by_user_id: uuid.UUID,
        export_type: str,
        event_id: uuid.UUID | None = None,
    ) -> ExportJob:
        """Create a queued ExportJob and enqueue the background worker task."""
        job_id = uuid.uuid4()
        job = ExportJob(
            id=job_id,
            organization_id=organization_id,
            requested_by_user_id=requested_by_user_id,
            export_type=export_type,
            status="queued",
            row_count=0,
            created_at=datetime.now(UTC),
        )
        self.session.add(job)
        await self.session.flush()

        # Enqueue background Celery task
        try:
            from typevector.workers.export_tasks import generate_export_job_task

            generate_export_job_task.delay(str(job_id), str(event_id) if event_id else None)
        except Exception as exc:
            logger.warning(
                "Celery task enqueue failed for export %s; worker will poll or fallback: %s",
                job_id,
                exc,
            )

        return job

    async def create_export_job(
        self,
        organization_id: uuid.UUID,
        requested_by_user_id: uuid.UUID,
        export_type: str,
        event_id: uuid.UUID | None = None,
    ) -> ExportJob:
        """Create and generate an export job directly (used synchronously or by workers)."""
        job_id = uuid.uuid4()
        return await self.generate_export_file(
            job_id=job_id,
            organization_id=organization_id,
            requested_by_user_id=requested_by_user_id,
            export_type=export_type,
            event_id=event_id,
        )

    async def generate_export_file(
        self,
        job_id: uuid.UUID,
        organization_id: uuid.UUID,
        requested_by_user_id: uuid.UUID,
        export_type: str,
        event_id: uuid.UUID | None = None,
    ) -> ExportJob:
        """Execute CSV generation with formula injection sanitization and atomic persistence."""
        file_path = str(self.export_dir / f"{job_id}.csv")
        row_count = 0
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer, quoting=csv.QUOTE_MINIMAL)

        if export_type == "roster":
            if not event_id:
                raise InvariantViolationError("event_id is required for roster export.")
            event = await self.session.get(Event, event_id)
            if not event:
                raise EntityNotFoundError(entity="Event", identifier=event_id)

            roster_stmt = (
                select(EventRegistration, User)
                .join(User, EventRegistration.user_id == User.id)
                .where(EventRegistration.event_id == event_id)
                .order_by(EventRegistration.registered_at.asc())
            )
            roster_res = await self.session.execute(roster_stmt)
            writer.writerow(
                ["User_ID", "Display_Name", "Email", "Status", "Registered_At", "Checked_In_At"]
            )
            for reg, user in roster_res.all():
                writer.writerow(
                    [
                        sanitize_csv_value(str(user.id)),
                        sanitize_csv_value(user.display_name),
                        sanitize_csv_value(user.email),
                        sanitize_csv_value(reg.status),
                        sanitize_csv_value(
                            reg.registered_at.isoformat() if reg.registered_at else ""
                        ),
                        sanitize_csv_value(
                            reg.checked_in_at.isoformat() if reg.checked_in_at else ""
                        ),
                    ]
                )
                row_count += 1

        elif export_type == "standings":
            if not event_id:
                raise InvariantViolationError("event_id is required for standings export.")
            pub_stmt = (
                select(PublishedResult)
                .options(selectinload(PublishedResult.rows))
                .where(PublishedResult.event_id == event_id, PublishedResult.is_current.is_(True))
            )
            pub_res = (await self.session.execute(pub_stmt)).scalar_one_or_none()
            if not pub_res:
                raise EntityNotFoundError(entity="PublishedResult", identifier=event_id)

            writer.writerow(
                [
                    "Rank",
                    "Participant_ID",
                    "Handle",
                    "Gross_WPM",
                    "Net_WPM",
                    "Accuracy_Pct",
                    "Score",
                    "Tier",
                ]
            )
            for r in pub_res.rows:
                writer.writerow(
                    [
                        sanitize_csv_value(r.rank_order),
                        sanitize_csv_value(str(r.user_id)),
                        sanitize_csv_value(str(r.score_id)),
                        sanitize_csv_value(f"{r.gross_wpm:.1f}"),
                        sanitize_csv_value(f"{r.net_wpm:.1f}"),
                        sanitize_csv_value(f"{r.accuracy_pct:.2f}"),
                        sanitize_csv_value(r.arena_score),
                        sanitize_csv_value(r.tier),
                    ]
                )
                row_count += 1

        elif export_type == "audit_log":
            audit_stmt = (
                select(AuditEvent)
                .where(AuditEvent.organization_id == organization_id)
                .order_by(AuditEvent.created_at.desc())
                .limit(2000)
            )
            audit_res = await self.session.execute(audit_stmt)
            writer.writerow(
                ["ID", "Timestamp", "Actor_ID", "Event_Type", "Target_Type", "Target_ID"]
            )
            for e in audit_res.scalars().all():
                writer.writerow(
                    [
                        sanitize_csv_value(str(e.id)),
                        sanitize_csv_value(e.created_at.isoformat()),
                        sanitize_csv_value(str(e.actor_user_id) if e.actor_user_id else ""),
                        sanitize_csv_value(e.event_type),
                        sanitize_csv_value(e.target_type),
                        sanitize_csv_value(e.target_id),
                    ]
                )
                row_count += 1
        else:
            raise InvariantViolationError(f"Unsupported export_type '{export_type}'.")

        # Write safely to disk
        with open(file_path, "w", encoding="utf-8", newline="") as f:
            f.write(csv_buffer.getvalue())

        job = await self.session.get(ExportJob, job_id)
        if not job:
            job = ExportJob(
                id=job_id,
                organization_id=organization_id,
                requested_by_user_id=requested_by_user_id,
                export_type=export_type,
                status="ready",
                file_path=file_path,
                row_count=row_count,
                completed_at=datetime.now(UTC),
            )
            self.session.add(job)
        else:
            job.status = "ready"
            job.file_path = file_path
            job.row_count = row_count
            job.completed_at = datetime.now(UTC)

        audit_entry = AuditEvent(
            id=uuid.uuid4(),
            organization_id=organization_id,
            actor_user_id=requested_by_user_id,
            event_type="exports.created",
            target_type="export_job",
            target_id=str(job_id),
            payload_json={
                "export_type": export_type,
                "event_id": str(event_id) if event_id else None,
                "row_count": row_count,
            },
        )
        self.session.add(audit_entry)
        return job

    async def download_export_content(
        self,
        job_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
        user_role: str,
    ) -> tuple[str, str]:
        """Fetch sanitized CSV export file content with tenant boundary enforcement."""
        job = await self.get_job(job_id)

        # Scoped access check: User must be platform admin or belong to organization
        if user_role != "platform_admin":
            from typevector.domains.organizations.models import OrganizationMember

            stmt = select(OrganizationMember).where(
                OrganizationMember.organization_id == job.organization_id,
                OrganizationMember.user_id == requesting_user_id,
            )
            membership = (await self.session.execute(stmt)).scalar_one_or_none()
            if not membership or membership.role not in ("owner", "organizer", "admin"):
                raise ForbiddenError("Actor is not authorized to download this export.")

        if job.status == "expired":
            raise EntityNotFoundError(
                entity="ExportFile",
                identifier=job_id,
                detail=f"ExportFile '{job_id}' has expired and been purged per retention policy.",
            )

        if not job.file_path or not os.path.exists(job.file_path):
            raise EntityNotFoundError(entity="ExportFile", identifier=job_id)

        with open(job.file_path, encoding="utf-8") as f:
            content = f.read()

        audit = AuditEvent(
            id=uuid.uuid4(),
            organization_id=job.organization_id,
            actor_user_id=requesting_user_id,
            event_type="exports.downloaded",
            target_type="export_job",
            target_id=str(job_id),
            payload_json={"export_type": job.export_type},
        )
        self.session.add(audit)

        filename = f"typevector-{job.export_type}-{job_id}.csv"
        return filename, content

    async def purge_expired_exports(self, retention_days: int = 7) -> int:
        """Physical deletion lifecycle: purge files older than retention_days from disk."""
        threshold = datetime.now(UTC) - timedelta(days=retention_days)
        stmt = select(ExportJob).where(
            ExportJob.status.in_(["ready", "completed"]),
            ExportJob.completed_at < threshold,
        )
        res = await self.session.execute(stmt)
        expired_jobs = list(res.scalars().all())

        purged_count = 0
        for job in expired_jobs:
            if job.file_path and os.path.exists(job.file_path):
                try:
                    os.remove(job.file_path)
                except OSError as err:
                    logger.warning(
                        "Could not delete expired export file %s: %s", job.file_path, err
                    )
            job.status = "expired"
            purged_count += 1

        if purged_count > 0:
            await self.session.flush()
        return purged_count
