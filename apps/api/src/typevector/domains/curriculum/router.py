"""TypeVector Arena — Curriculum API Router."""

from typing import Annotated

from fastapi import APIRouter, Depends

from typevector.auth import get_current_user
from typevector.dependencies import DbSession
from typevector.domains.curriculum.schemas import (
    AdaptiveRecommendationRead,
    CurriculumAssessmentSubmit,
    CurriculumEvaluationResult,
    SkillTrackDetailRead,
    SkillTrackRead,
    UserTrackProgressRead,
)
from typevector.domains.curriculum.service import CurriculumService
from typevector.domains.identity.models import User
from typevector.errors import EntityNotFoundError

router = APIRouter(prefix="/curriculum", tags=["Curriculum"])


@router.get("/tracks", response_model=list[SkillTrackRead])
async def list_curriculum_tracks(session: DbSession) -> list[SkillTrackRead]:
    """List all available curriculum skill tracks."""
    service = CurriculumService(session)
    tracks = service.list_catalog_tracks()
    return [
        SkillTrackRead(
            id=t["slug"],
            slug=t["slug"],
            title=t["title"],
            description=t["description"],
            is_active=True,
        )
        for t in tracks
    ]


@router.get("/tracks/{slug}", response_model=SkillTrackDetailRead)
async def get_curriculum_track_detail(slug: str, session: DbSession) -> SkillTrackDetailRead:
    """Fetch track details, objectives, and all level criteria definitions."""
    service = CurriculumService(session)
    track = service.get_track_detail(slug)
    if not track:
        raise EntityNotFoundError(entity="SkillTrack", identifier=slug)

    return SkillTrackDetailRead.model_validate(track)


@router.get("/progress", response_model=list[UserTrackProgressRead])
async def get_my_curriculum_progress(
    session: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[UserTrackProgressRead]:
    """Fetch participant's independent qualification progress across all 7 tracks."""
    service = CurriculumService(session)
    progress_list = await service.get_user_progress_summary(current_user.id)
    return [UserTrackProgressRead.model_validate(p) for p in progress_list]


@router.post("/assessments", response_model=CurriculumEvaluationResult)
async def submit_curriculum_assessment(
    submission: CurriculumAssessmentSubmit,
    session: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> CurriculumEvaluationResult:
    """Evaluate a level assessment attempt authoritatively against versioned criteria.

    Multi-attempt qualification rule: A single lucky attempt cannot advance a user.
    """
    service = CurriculumService(session)
    result = await service.evaluate_assessment(
        user_id=current_user.id,
        submission=submission,
    )
    return CurriculumEvaluationResult.model_validate(result)


@router.get("/recommendations", response_model=AdaptiveRecommendationRead)
async def get_adaptive_recommendation(
    session: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> AdaptiveRecommendationRead:
    """Fetch explainable, evidence-backed adaptive recommendations based on observed weaknesses."""
    service = CurriculumService(session)
    recommendation = await service.get_adaptive_recommendation(current_user.id)
    return AdaptiveRecommendationRead.model_validate(recommendation)
