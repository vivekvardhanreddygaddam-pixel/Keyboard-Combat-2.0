"""TypeVector Arena — Exports API Router."""

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select

from typevector.auth import AuthenticatedUser, enforce_csrf
from typevector.dependencies import DbSession
from typevector.domains.exports.schemas import ExportJobCreateRequest, ExportJobRead
from typevector.domains.exports.service import ExportService
from typevector.domains.organizations.models import OrganizationMember
from typevector.errors import ForbiddenError

router = APIRouter(prefix="/exports", tags=["Exports"])


@router.post(
    "/jobs",
    response_model=ExportJobRead,
    dependencies=[Depends(enforce_csrf)],
)
async def create_export_job(
    payload: ExportJobCreateRequest,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> ExportJobRead:
    """Create a new data export job (requires organizer or admin)."""
    stmt = select(OrganizationMember).where(
        OrganizationMember.organization_id == payload.organization_id,
        OrganizationMember.user_id == current_user.id,
    )
    membership = (await session.execute(stmt)).scalar_one_or_none()
    is_admin = getattr(current_user, "role", None) == "platform_admin" or (
        membership is not None and membership.role in ("owner", "organizer", "admin")
    )
    if not is_admin:
        raise ForbiddenError("Actor is not authorized to request exports for this organization.")

    service = ExportService(session)
    job = await service.create_export_job(
        organization_id=payload.organization_id,
        requested_by_user_id=current_user.id,
        export_type=payload.export_type,
        event_id=payload.event_id,
    )
    await session.commit()
    return ExportJobRead.model_validate(job)


@router.get("/jobs/{job_id}", response_model=ExportJobRead)
async def get_export_job(
    job_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> ExportJobRead:
    """Fetch status and completion of a data export job (restricted to tenant member or admin)."""
    service = ExportService(session)
    job = await service.get_job(job_id)
    if getattr(current_user, "role", None) != "platform_admin":
        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == job.organization_id,
            OrganizationMember.user_id == current_user.id,
        )
        membership = (await session.execute(stmt)).scalar_one_or_none()
        if not membership or membership.role not in ("owner", "organizer", "admin"):
            raise ForbiddenError(
                "Actor is not authorized to inspect export jobs for this organization."
            )
    return ExportJobRead.model_validate(job)


@router.get("/organization/{organization_id}/jobs", response_model=list[ExportJobRead])
async def list_organization_export_jobs(
    organization_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> list[ExportJobRead]:
    """List data export jobs for an organization."""
    stmt = select(OrganizationMember).where(
        OrganizationMember.organization_id == organization_id,
        OrganizationMember.user_id == current_user.id,
    )
    membership = (await session.execute(stmt)).scalar_one_or_none()
    is_admin = getattr(current_user, "role", None) == "platform_admin" or (
        membership is not None and membership.role in ("owner", "organizer", "admin")
    )
    if not is_admin:
        raise ForbiddenError("Actor is not authorized to list exports for this organization.")

    service = ExportService(session)
    jobs = await service.list_org_jobs(organization_id)
    return [ExportJobRead.model_validate(j) for j in jobs]


@router.get("/jobs/{job_id}/download")
async def download_export(
    job_id: uuid.UUID,
    current_user: AuthenticatedUser,
    session: DbSession,
) -> Response:
    """Download sanitized CSV file with formula injection protections."""
    service = ExportService(session)
    filename, content = await service.download_export_content(
        job_id=job_id,
        requesting_user_id=current_user.id,
        user_role=getattr(current_user, "role", "participant"),
    )
    await session.commit()

    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
