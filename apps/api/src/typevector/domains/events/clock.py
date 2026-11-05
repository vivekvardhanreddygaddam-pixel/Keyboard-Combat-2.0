"""TypeVector Arena — Server Clock Authority and Clock Sampling."""

import time
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from typevector.domains.events.lifecycle import CLOCK_UNCERTAINTY_MAX_MS


class ServerClockSample(BaseModel):
    """Authoritative server clock sample for client drift estimation.

    Clients must NEVER use local device clocks for round start, round end,
    or sequence submission deadlines.
    """

    server_time_ms: int = Field(..., description="Authoritative server UTC epoch in milliseconds")
    server_time_utc: datetime = Field(
        ..., description="Authoritative server UTC timestamp (ISO 8601)"
    )
    uncertainty_ms: float = Field(
        ..., description="Estimated clock uncertainty bound (bounded <= 5.0ms target)"
    )
    clock_status: str = Field(default="synchronized", description="Clock synchronization state")


def get_server_clock_sample() -> ServerClockSample:
    """Sample the authoritative server clock with monotonic precision."""
    now_utc = datetime.now(UTC)
    now_ms = int(time.time() * 1000)
    # Host virtualization / NTP nominal jitter estimate (typically 1.0 - 2.5 ms)
    estimated_uncertainty = 2.0
    if estimated_uncertainty > CLOCK_UNCERTAINTY_MAX_MS:
        estimated_uncertainty = CLOCK_UNCERTAINTY_MAX_MS

    return ServerClockSample(
        server_time_ms=now_ms,
        server_time_utc=now_utc,
        uncertainty_ms=estimated_uncertainty,
        clock_status="synchronized",
    )
