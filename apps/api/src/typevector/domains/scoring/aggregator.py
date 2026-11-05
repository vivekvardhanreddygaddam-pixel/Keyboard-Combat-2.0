"""TypeVector Arena — Mandatory-Round Result Aggregation and Weighting."""

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RoundScoreItem:
    """Score evidence for a participant in a single competition round."""

    round_id: uuid.UUID
    sequence_number: int
    weight: int  # Frozen integer round weight >= 1
    is_round_voided: bool
    participant_status: str  # completed, timed_out, no_show, invalidated, disqualified
    arena_score: int
    net_wpm: float
    accuracy_pct: float


@dataclass(frozen=True)
class AggregatedScoreResult:
    """Final multi-round aggregated standing and eligibility calculation."""

    user_id: uuid.UUID
    aggregate_score: int
    weighted_net_wpm: float
    weighted_accuracy_pct: float
    is_eligible: bool
    ineligibility_reason: str | None
    total_rounds_considered: int
    voided_rounds_count: int
    round_details: list[dict[str, Any]]


def aggregate_participant_rounds(
    user_id: uuid.UUID,
    round_items: list[RoundScoreItem],
) -> AggregatedScoreResult:
    """Aggregate multi-round scores adhering to published tournament fairness policy.

    POLICY INVARIANTS:
    1. Voided Round Denominator Behavior:
       A voided round is excluded from both the numerator and denominator of the aggregate score.
    2. Disqualification:
       A disqualified attempt strips podium/ranking eligibility (`is_eligible = False`) and zeroes the score.
    3. No-Show:
       Contributes score 0.0 with full round weight in denominator.
    4. Timeout:
       Contributes the incomplete attempt score (<= 699) with full round weight in denominator.
    5. Invalidation:
       Contributes score 0.0 with full round weight in denominator.
    """
    if not round_items:
        return AggregatedScoreResult(
            user_id=user_id,
            aggregate_score=0,
            weighted_net_wpm=0.0,
            weighted_accuracy_pct=0.0,
            is_eligible=False,
            ineligibility_reason="no_rounds_recorded",
            total_rounds_considered=0,
            voided_rounds_count=0,
            round_details=[],
        )

    # Check disqualification
    for item in round_items:
        if item.participant_status == "disqualified":
            return AggregatedScoreResult(
                user_id=user_id,
                aggregate_score=0,
                weighted_net_wpm=0.0,
                weighted_accuracy_pct=0.0,
                is_eligible=False,
                ineligibility_reason=f"disqualified_in_round_{item.sequence_number}",
                total_rounds_considered=len(round_items),
                voided_rounds_count=sum(1 for r in round_items if r.is_round_voided),
                round_details=[
                    {
                        "round_id": str(r.round_id),
                        "sequence_number": r.sequence_number,
                        "status": r.participant_status,
                        "arena_score": r.arena_score,
                    }
                    for r in round_items
                ],
            )

    numerator_score = 0
    numerator_wpm = 0.0
    numerator_acc = 0.0
    total_active_weight = 0
    voided_count = 0
    round_details: list[dict[str, Any]] = []

    for item in round_items:
        if item.is_round_voided:
            voided_count += 1
            round_details.append(
                {
                    "round_id": str(item.round_id),
                    "sequence_number": item.sequence_number,
                    "status": "round_voided",
                    "weight": 0,
                    "arena_score": 0,
                }
            )
            continue  # Excluded from both numerator and denominator!

        w = max(1, item.weight)
        effective_score = item.arena_score
        if item.participant_status in ("no_show", "invalidated"):
            effective_score = 0

        numerator_score += w * effective_score
        numerator_wpm += w * item.net_wpm
        numerator_acc += w * item.accuracy_pct
        total_active_weight += w

        round_details.append(
            {
                "round_id": str(item.round_id),
                "sequence_number": item.sequence_number,
                "status": item.participant_status,
                "weight": w,
                "arena_score": effective_score,
                "net_wpm": item.net_wpm,
                "accuracy_pct": item.accuracy_pct,
            }
        )

    if total_active_weight == 0:
        return AggregatedScoreResult(
            user_id=user_id,
            aggregate_score=0,
            weighted_net_wpm=0.0,
            weighted_accuracy_pct=0.0,
            is_eligible=False,
            ineligibility_reason="all_rounds_voided",
            total_rounds_considered=len(round_items),
            voided_rounds_count=voided_count,
            round_details=round_details,
        )

    aggregate_score = int(round(numerator_score / total_active_weight))
    weighted_wpm = round(numerator_wpm / total_active_weight, 2)
    weighted_acc = round(numerator_acc / total_active_weight, 2)

    return AggregatedScoreResult(
        user_id=user_id,
        aggregate_score=aggregate_score,
        weighted_net_wpm=weighted_wpm,
        weighted_accuracy_pct=weighted_acc,
        is_eligible=True,
        ineligibility_reason=None,
        total_rounds_considered=len(round_items) - voided_count,
        voided_rounds_count=voided_count,
        round_details=round_details,
    )
