"""TypeVector Arena — Broadcast API and WebSocket Spectator Router."""

import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from typevector.common.schemas import MessageResponse
from typevector.config import settings
from typevector.domains.broadcast.spectator_manager import spectator_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/broadcast", tags=["Broadcast"])


@router.get("/channels/{event_id}", response_model=MessageResponse)
async def get_channel_info(event_id: uuid.UUID) -> MessageResponse:
    """Return active spectator broadcast channel info for an event."""
    return MessageResponse(
        message=f"Spectator broadcast channels available for event {event_id} at /api/v1/broadcast/events/{event_id}/spectate"
    )


@router.websocket("/events/{event_id}/spectate")
async def websocket_spectate_event(
    websocket: WebSocket,
    event_id: uuid.UUID,
) -> None:
    """Spectator & lobby WebSocket stream delivering lifecycle, round, and throttled leaderboard updates."""
    # Origin verification in production
    origin = websocket.headers.get("origin")
    if origin and settings.app_env == "production":
        allowed = settings.cors_origins_list
        if origin not in allowed:
            logger.warning(f"Spectator socket rejected due to untrusted origin: {origin}")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Untrusted origin")
            return

    await spectator_manager.connect(event_id, websocket)

    # Initial welcome payload
    await websocket.send_json(
        {
            "version": "arena-ws-v1",
            "type": "SPECTATOR_CONNECTED",
            "event_id": str(event_id),
            "message": "Connected to real-time event spectator stream.",
        }
    )

    try:
        while True:
            # Spectators can send ping / client status; keep stream alive
            data = await websocket.receive_text()
            if len(data.encode("utf-8")) > 1024:
                await websocket.close(code=status.WS_1009_MESSAGE_TOO_BIG)
                return
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        spectator_manager.disconnect(event_id, websocket)
    except Exception as exc:
        logger.warning("Spectator socket unexpected error: %s", exc)
        spectator_manager.disconnect(event_id, websocket)
