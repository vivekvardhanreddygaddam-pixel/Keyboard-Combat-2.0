"""TypeVector Arena — Celery Beat Single-Scheduler Safeguard.

Prevents duplicate task scheduling across multi-container or clustered deployments.
Acquires a renewable Redis distributed lock so only ONE scheduler instance fires tasks.
"""

import logging
import os
import socket
import time
from typing import Final

from celery.beat import Scheduler
from redis import Redis

from typevector.config import settings

logger = logging.getLogger(__name__)

LOCK_KEY: Final[str] = "tv:beat:active_scheduler_lock"
LOCK_TTL_SECONDS: Final[int] = 30


class SingleInstanceBeatScheduler(Scheduler):
    """Custom Celery Beat scheduler that enforces single-instance execution via Redis distributed locking."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.instance_id = f"{socket.gethostname()}:{os.getpid()}:{time.time()}"
        self.redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        self._has_lock = False
        super().__init__(*args, **kwargs)

    def acquire_lock(self) -> bool:
        """Attempt to acquire the distributed scheduler lock."""
        acquired = self.redis_client.set(
            LOCK_KEY,
            self.instance_id,
            nx=True,
            ex=LOCK_TTL_SECONDS,
        )
        if acquired:
            self._has_lock = True
            logger.info("Acquired Celery Beat scheduler lock for instance: %s", self.instance_id)
            return True

        current_holder = self.redis_client.get(LOCK_KEY)
        if current_holder == self.instance_id:
            # Re-extend own lock
            self.redis_client.expire(LOCK_KEY, LOCK_TTL_SECONDS)
            self._has_lock = True
            return True

        self._has_lock = False
        logger.warning(
            "Another scheduler instance holds the active lock (%s); skipping beat tick.",
            current_holder,
        )
        return False

    def release_lock(self) -> None:
        """Release the distributed scheduler lock on shutdown if owned."""
        if self._has_lock:
            current_holder = self.redis_client.get(LOCK_KEY)
            if current_holder == self.instance_id:
                self.redis_client.delete(LOCK_KEY)
                logger.info(
                    "Released Celery Beat scheduler lock for instance: %s", self.instance_id
                )
            self._has_lock = False

    def tick(self) -> float:
        """Execute scheduler tick only if holding the active distributed lock."""
        try:
            if not self.acquire_lock():
                # Sleep and yield tick if another scheduler is active
                return 5.0
            return float(super().tick())
        except Exception as exc:
            logger.error("Error in SingleInstanceBeatScheduler tick: %s", exc)
            return 5.0

    def close(self) -> None:
        """Ensure lock release on scheduler termination."""
        self.release_lock()
        super().close()
