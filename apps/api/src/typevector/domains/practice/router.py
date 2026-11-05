"""TypeVector Arena — Practice API Router."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from typevector.auth import get_current_user, get_current_user_optional
from typevector.common.schemas import PaginationParams
from typevector.dependencies import DbSession, DbSessionOptional
from typevector.domains.identity.models import User
from typevector.domains.practice.schemas import (
    DiffSegment,
    PracticeEvaluationResponse,
    PracticeModeInfo,
    PracticePromptRead,
    PracticeSessionRead,
    PracticeSessionSubmit,
)
from typevector.domains.practice.service import PracticeService
from typevector.errors import EntityNotFoundError, ForbiddenError

router = APIRouter(prefix="/practice", tags=["Practice"])


@router.get("/modes", response_model=list[PracticeModeInfo])
async def list_practice_modes() -> list[PracticeModeInfo]:
    """List available practice modes and rules."""
    service = PracticeService()
    modes = service.list_modes()
    return [PracticeModeInfo.model_validate(m) for m in modes]


@router.get("/prompts", response_model=list[PracticePromptRead])
async def list_practice_prompts(
    mode: Annotated[str | None, Query(description="Filter by practice mode")] = None,
) -> list[PracticePromptRead]:
    """List curated practice prompts, optionally filtered by mode."""
    service = PracticeService()
    prompts = service.list_prompts(mode=mode)
    return [PracticePromptRead.model_validate(p) for p in prompts]


@router.get("/prompts/{prompt_id}", response_model=PracticePromptRead)
async def get_practice_prompt(
    prompt_id: str,
) -> PracticePromptRead:
    """Fetch a single practice prompt by its ID."""
    service = PracticeService()
    prompt = service.get_prompt(prompt_id)
    if not prompt:
        raise EntityNotFoundError(entity="PracticePrompt", identifier=prompt_id)
    return PracticePromptRead.model_validate(prompt)


@router.post("/sessions", response_model=PracticeEvaluationResponse)
async def submit_practice_session(
    submission: PracticeSessionSubmit,
    session: DbSessionOptional = None,
    current_user: Annotated[User | None, Depends(get_current_user_optional)] = None,
) -> PracticeEvaluationResponse:
    """Evaluate a practice typing attempt authoritatively and persist it.

    Supports authenticated participants, anonymous practice sessions, and standalone offline execution.
    """
    service = PracticeService(session)
    user_id = current_user.id if current_user else None

    practice_session, is_saved = await service.evaluate_and_record_session(
        submission=submission,
        user_id=user_id,
    )

    evidence = practice_session.error_diff_json or {}
    metrics = evidence.get("metrics", {})
    raw_segments = evidence.get("segments", [])
    segments = [DiffSegment.model_validate(s) for s in raw_segments]

    return PracticeEvaluationResponse(
        session_id=practice_session.id,
        user_id=practice_session.user_id,
        mode=practice_session.mode,
        language=practice_session.language,
        is_saved=is_saved,
        started_at=practice_session.started_at,
        completed_at=practice_session.completed_at or practice_session.started_at,
        metrics=metrics,
        segments=segments,
        error_breakdown=evidence.get("error_breakdown", {}),
        suggestions=evidence.get("suggestions", []),
    )


@router.get("/sessions/{session_id}", response_model=PracticeEvaluationResponse)
async def get_practice_session_details(
    session_id: uuid.UUID,
    session: DbSession,
    current_user: Annotated[User | None, Depends(get_current_user_optional)] = None,
) -> PracticeEvaluationResponse:
    """Fetch authoritative evaluation details for a saved practice session."""
    service = PracticeService(session)
    practice_session = await service.get_session_by_id(session_id)
    if not practice_session:
        raise EntityNotFoundError(entity="PracticeSession", identifier=session_id)

    if practice_session.user_id is not None and (
        not current_user
        or (
            current_user.id != practice_session.user_id
            and getattr(current_user, "role", None) != "platform_admin"
        )
    ):
        raise ForbiddenError(
            "Actor is not authorized to view another participant's saved practice session."
        )

    evidence = practice_session.error_diff_json or {}
    metrics = evidence.get("metrics", {})
    raw_segments = evidence.get("segments", [])
    segments = [DiffSegment.model_validate(s) for s in raw_segments]

    return PracticeEvaluationResponse(
        session_id=practice_session.id,
        user_id=practice_session.user_id,
        mode=practice_session.mode,
        language=practice_session.language,
        is_saved=True,
        started_at=practice_session.started_at,
        completed_at=practice_session.completed_at or practice_session.started_at,
        metrics=metrics,
        segments=segments,
        error_breakdown=evidence.get("error_breakdown", {}),
        suggestions=evidence.get("suggestions", []),
    )


@router.get("/history", response_model=list[PracticeSessionRead])
async def get_my_practice_history(
    session: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    pagination: Annotated[PaginationParams, Depends()],
) -> list[PracticeSessionRead]:
    """Fetch practice attempt history for the authenticated user."""
    service = PracticeService(session)
    sessions = await service.list_user_history(
        user_id=current_user.id,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return [PracticeSessionRead.model_validate(s) for s in sessions]
