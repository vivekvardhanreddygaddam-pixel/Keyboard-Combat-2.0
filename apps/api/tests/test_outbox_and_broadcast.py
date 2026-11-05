"""TypeVector Arena — Outbox Dispatcher, Redis Resiliency, and Spectator Broadcast Tests."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import typevector.models  # noqa: F401
from typevector.domains.broadcast.spectator_manager import SpectatorConnectionManager
from typevector.domains.notifications.models import TransactionalOutbox
from typevector.domains.notifications.outbox_dispatcher import OutboxDispatcher


class MockOutboxSession:
    """Mock async SQLAlchemy session tracking outbox events."""

    def __init__(self, events: list[TransactionalOutbox]) -> None:
        self.events = events

    async def execute(self, stmt: object) -> MagicMock:
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            e for e in self.events if e.status == "pending"
        ]
        return mock_result

    async def flush(self) -> None:
        pass


@pytest.mark.asyncio
async def test_outbox_dispatch_success() -> None:
    """Verify pending outbox events are published to Redis and marked dispatched."""
    event_id = uuid.uuid4()
    outbox_item = TransactionalOutbox(
        id=uuid.uuid4(),
        event_type="arena:events:lifecycle",
        payload_json={"event_id": str(event_id), "status": "live"},
        status="pending",
        retry_count=0,
    )

    session = MockOutboxSession([outbox_item])
    dispatcher = OutboxDispatcher(session)

    mock_redis = AsyncMock()
    mock_redis.publish.return_value = 1

    with patch(
        "typevector.domains.notifications.outbox_dispatcher.get_redis_client",
        return_value=mock_redis,
    ):
        dispatched = await dispatcher.dispatch_pending(batch_size=10)

    assert dispatched == 1
    assert outbox_item.status == "dispatched"
    assert outbox_item.dispatched_at is not None
    mock_redis.publish.assert_called_once()


@pytest.mark.asyncio
async def test_outbox_dispatch_redis_failure_resilience() -> None:
    """Verify that Redis connection or pub/sub failures do not crash execution or corrupt state."""
    event_id = uuid.uuid4()
    outbox_item = TransactionalOutbox(
        id=uuid.uuid4(),
        event_type="arena:events:rounds",
        payload_json={"event_id": str(event_id), "action": "round.started"},
        status="pending",
        retry_count=0,
    )

    session = MockOutboxSession([outbox_item])
    dispatcher = OutboxDispatcher(session)

    mock_redis = AsyncMock()
    mock_redis.publish.side_effect = ConnectionError("Redis cluster offline")

    with patch(
        "typevector.domains.notifications.outbox_dispatcher.get_redis_client",
        return_value=mock_redis,
    ):
        dispatched = await dispatcher.dispatch_pending(batch_size=10)

    # Dispatched count is 0; retry_count incremented; status remains pending
    assert dispatched == 0
    assert outbox_item.status == "pending"
    assert outbox_item.retry_count == 1
    assert outbox_item.dispatched_at is None


@pytest.mark.asyncio
async def test_spectator_connection_manager_broadcast() -> None:
    """Verify spectator manager manages connections and broadcasts envelopes to subscribers."""
    manager = SpectatorConnectionManager()
    event_id = uuid.uuid4()

    ws1 = AsyncMock()
    ws2 = AsyncMock()

    await manager.connect(event_id, ws1)
    await manager.connect(event_id, ws2)

    sent = await manager.broadcast_event_message(
        event_id=event_id,
        message_type="ROUND_STATE",
        payload={"round_status": "active"},
    )

    assert sent == 2
    ws1.send_text.assert_called_once()
    ws2.send_text.assert_called_once()

    manager.disconnect(event_id, ws1)
    manager.disconnect(event_id, ws2)


@pytest.mark.asyncio
async def test_leaderboard_1hz_throttling() -> None:
    """Verify leaderboard updates are throttled to 1 Hz max to protect input ACK prioritization."""
    manager = SpectatorConnectionManager()
    event_id = uuid.uuid4()

    ws = AsyncMock()
    await manager.connect(event_id, ws)

    rankings = [{"rank": 1, "user_id": str(uuid.uuid4()), "wpm": 125.0}]

    # First update succeeds
    first_result = await manager.broadcast_leaderboard_throttled(event_id, rankings)
    assert first_result is True

    # Immediate second update within 1.0 second is throttled
    second_result = await manager.broadcast_leaderboard_throttled(event_id, rankings)
    assert second_result is False

    # Simulate 1.1 seconds elapsed
    manager._last_leaderboard_broadcast[event_id] = 0.0
    third_result = await manager.broadcast_leaderboard_throttled(event_id, rankings)
    assert third_result is True

    manager.disconnect(event_id, ws)
