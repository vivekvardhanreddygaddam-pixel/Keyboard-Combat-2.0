"""TypeVector Arena — Notifications API Router."""

import uuid

from fastapi import APIRouter

from typevector.auth import AuthenticatedUser
from typevector.common.schemas import MessageResponse
from typevector.errors import ForbiddenError

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/user/{user_id}/summary", response_model=MessageResponse)
async def get_notification_summary(
    user_id: uuid.UUID,
    current_user: AuthenticatedUser,
) -> MessageResponse:
    """Return notification status for a user (restricted to self or platform admin)."""
    if current_user.id != user_id and getattr(current_user, "role", None) != "platform_admin":
        raise ForbiddenError("Actor is not authorized to inspect another user's notifications.")
    return MessageResponse(message=f"Notification deliveries active for user {user_id}")
