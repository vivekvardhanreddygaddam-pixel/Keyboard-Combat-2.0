"""TypeVector Arena — Event Lifecycle State Machine and Fairness Policy."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

# ---------------------------------------------------------------------------
# Tournament Fairness Policy (Formal Specification)
# ---------------------------------------------------------------------------
FAIRNESS_POLICY_STATUS: Final[str] = "DRAFT_AWAITING_TOURNAMENT_APPROVAL"
MAX_PAUSES_PER_ROUND: Final[int] = 2
MAX_PAUSE_DURATION_SECONDS: Final[int] = 600  # 10 minutes maximum event-wide pause
CLOCK_UNCERTAINTY_MAX_MS: Final[float] = 5.0  # Max server clock uncertainty bound


class EventStatus(StrEnum):
    """Authoritative lifecycle states for competition events."""

    DRAFT = "draft"
    PUBLISHED = "published"
    REGISTRATION_OPEN = "registration_open"
    CHECK_IN_OPEN = "check_in_open"
    READY = "ready"
    LIVE = "live"
    PAUSED = "paused"
    COMPLETED = "completed"
    REVIEW = "review"
    RESULTS_PUBLISHED = "results_published"
    AMENDED = "amended"
    CANCELLED = "cancelled"
    VOIDED = "voided"
    ARCHIVED = "archived"


TERMINAL_EVENT_STATES: Final[set[EventStatus]] = {
    EventStatus.CANCELLED,
    EventStatus.VOIDED,
    EventStatus.ARCHIVED,
}

FROZEN_EVENT_STATES: Final[set[EventStatus]] = {
    EventStatus.PUBLISHED,
    EventStatus.REGISTRATION_OPEN,
    EventStatus.CHECK_IN_OPEN,
    EventStatus.READY,
    EventStatus.LIVE,
    EventStatus.PAUSED,
    EventStatus.COMPLETED,
    EventStatus.REVIEW,
    EventStatus.RESULTS_PUBLISHED,
    EventStatus.AMENDED,
    EventStatus.CANCELLED,
    EventStatus.VOIDED,
    EventStatus.ARCHIVED,
}


@dataclass(frozen=True)
class LifecycleTransitionRule:
    """Explicit transition definition governing event progression."""

    source_states: tuple[EventStatus, ...]
    target_state: EventStatus
    allowed_roles: tuple[str, ...]
    requires_reason: bool = False
    participant_visible: bool = True
    description: str = ""


# Transition Table (Strictly authoritative, non-bypassable)
LIFECYCLE_TRANSITION_TABLE: Final[list[LifecycleTransitionRule]] = [
    # 1. Draft to Published (Freezes rulesets and initial prompt structure)
    LifecycleTransitionRule(
        source_states=(EventStatus.DRAFT,),
        target_state=EventStatus.PUBLISHED,
        allowed_roles=("org_admin", "platform_admin"),
        requires_reason=False,
        description="Publish drafted event; freezes ruleset and round configurations",
    ),
    # 2. Open Registration
    LifecycleTransitionRule(
        source_states=(EventStatus.PUBLISHED,),
        target_state=EventStatus.REGISTRATION_OPEN,
        allowed_roles=("org_admin", "platform_admin"),
        requires_reason=False,
        description="Open participant registration",
    ),
    # 3. Open Check-in Window
    LifecycleTransitionRule(
        source_states=(EventStatus.REGISTRATION_OPEN,),
        target_state=EventStatus.CHECK_IN_OPEN,
        allowed_roles=("org_admin", "platform_admin"),
        requires_reason=False,
        description="Open participant check-in window prior to start",
    ),
    # 4. Ready to Start
    LifecycleTransitionRule(
        source_states=(EventStatus.CHECK_IN_OPEN,),
        target_state=EventStatus.READY,
        allowed_roles=("org_admin", "platform_admin"),
        requires_reason=False,
        description="Declare event ready for start; participant readiness verification",
    ),
    # 5. Start Event (Triggers automated no-show flagging for un-checked-in participants)
    LifecycleTransitionRule(
        source_states=(EventStatus.READY,),
        target_state=EventStatus.LIVE,
        allowed_roles=("org_admin", "platform_admin"),
        requires_reason=False,
        description="Commence live event; automated no-show flagging activated",
    ),
    # 6. Event-wide Pause (Emergency incident / pause policy)
    LifecycleTransitionRule(
        source_states=(EventStatus.LIVE,),
        target_state=EventStatus.PAUSED,
        allowed_roles=("org_admin", "platform_admin"),
        requires_reason=True,
        description="Pause live competition event under published fairness policy",
    ),
    # 7. Resume Paused Event (Uniform deadline adjustment across all active rounds and attempts)
    LifecycleTransitionRule(
        source_states=(EventStatus.PAUSED,),
        target_state=EventStatus.LIVE,
        allowed_roles=("org_admin", "platform_admin"),
        requires_reason=True,
        description="Resume competition event with uniform deadline extensions",
    ),
    # 8. Complete Competition
    LifecycleTransitionRule(
        source_states=(EventStatus.LIVE,),
        target_state=EventStatus.COMPLETED,
        allowed_roles=("org_admin", "platform_admin"),
        requires_reason=False,
        description="Conclude all rounds and end live competition",
    ),
    # 9. Enter Integrity Review
    LifecycleTransitionRule(
        source_states=(EventStatus.COMPLETED,),
        target_state=EventStatus.REVIEW,
        allowed_roles=("org_admin", "platform_admin"),
        requires_reason=False,
        description="Begin scoring verification, telemetry audit, and review",
    ),
    # 10. Publish Official Results
    LifecycleTransitionRule(
        source_states=(EventStatus.REVIEW,),
        target_state=EventStatus.RESULTS_PUBLISHED,
        allowed_roles=("org_admin", "platform_admin"),
        requires_reason=False,
        description="Publish official immutable results and final standings",
    ),
    # 11. Amend Results (Post-appeal amendment with mandatory auditable reason)
    LifecycleTransitionRule(
        source_states=(EventStatus.RESULTS_PUBLISHED,),
        target_state=EventStatus.AMENDED,
        allowed_roles=("org_admin", "platform_admin"),
        requires_reason=True,
        description="Re-open results for formal appeal amendment",
    ),
    # 12. Re-publish Amended Results
    LifecycleTransitionRule(
        source_states=(EventStatus.AMENDED,),
        target_state=EventStatus.RESULTS_PUBLISHED,
        allowed_roles=("org_admin", "platform_admin"),
        requires_reason=True,
        description="Re-publish official results following audited amendment",
    ),
    # 13. Cancellation (From pre-live states)
    LifecycleTransitionRule(
        source_states=(
            EventStatus.DRAFT,
            EventStatus.PUBLISHED,
            EventStatus.REGISTRATION_OPEN,
            EventStatus.CHECK_IN_OPEN,
            EventStatus.READY,
        ),
        target_state=EventStatus.CANCELLED,
        allowed_roles=("org_admin", "platform_admin"),
        requires_reason=True,
        description="Cancel unstarted competition",
    ),
    # 14. Voiding (From live, paused, review, or completed states upon material compromise)
    LifecycleTransitionRule(
        source_states=(
            EventStatus.LIVE,
            EventStatus.PAUSED,
            EventStatus.COMPLETED,
            EventStatus.REVIEW,
        ),
        target_state=EventStatus.VOIDED,
        allowed_roles=("platform_admin",),  # Voiding requires platform admin authorization
        requires_reason=True,
        description="Void compromised competition event under integrity policy",
    ),
    # 15. Archival (Terminal transition)
    LifecycleTransitionRule(
        source_states=(
            EventStatus.RESULTS_PUBLISHED,
            EventStatus.CANCELLED,
            EventStatus.VOIDED,
        ),
        target_state=EventStatus.ARCHIVED,
        allowed_roles=("org_admin", "platform_admin"),
        requires_reason=False,
        description="Archive finalized, cancelled, or voided event",
    ),
]


def find_transition_rule(
    current_status: EventStatus | str,
    target_status: EventStatus | str,
) -> LifecycleTransitionRule | None:
    """Find a matching transition rule from the authoritative transition table."""
    curr = EventStatus(current_status)
    target = EventStatus(target_status)
    for rule in LIFECYCLE_TRANSITION_TABLE:
        if curr in rule.source_states and rule.target_state == target:
            return rule
    return None
