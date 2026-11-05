"""TypeVector Arena — Round Aggregation, Weighting, and Void Denominator Policy Tests."""

import uuid

from typevector.domains.scoring.aggregator import (
    RoundScoreItem,
    aggregate_participant_rounds,
)


def test_round_aggregation_equal_weights() -> None:
    """Verify standard multi-round average with equal integer weights."""
    user_id = uuid.uuid4()
    rounds = [
        RoundScoreItem(
            round_id=uuid.uuid4(),
            sequence_number=1,
            weight=1,
            is_round_voided=False,
            participant_status="completed",
            arena_score=800,
            net_wpm=80.0,
            accuracy_pct=98.0,
        ),
        RoundScoreItem(
            round_id=uuid.uuid4(),
            sequence_number=2,
            weight=1,
            is_round_voided=False,
            participant_status="completed",
            arena_score=900,
            net_wpm=90.0,
            accuracy_pct=100.0,
        ),
    ]

    result = aggregate_participant_rounds(user_id, rounds)
    # (800 + 900) / 2 = 850
    assert result.aggregate_score == 850
    assert result.weighted_net_wpm == 85.0
    assert result.weighted_accuracy_pct == 99.0
    assert result.is_eligible is True
    assert result.total_rounds_considered == 2
    assert result.voided_rounds_count == 0


def test_round_aggregation_custom_frozen_weights() -> None:
    """Verify multi-round aggregation respects frozen round integer weights."""
    user_id = uuid.uuid4()
    rounds = [
        RoundScoreItem(
            round_id=uuid.uuid4(),
            sequence_number=1,
            weight=1,  # 25% weight
            is_round_voided=False,
            participant_status="completed",
            arena_score=600,
            net_wpm=60.0,
            accuracy_pct=90.0,
        ),
        RoundScoreItem(
            round_id=uuid.uuid4(),
            sequence_number=2,
            weight=3,  # 75% weight
            is_round_voided=False,
            participant_status="completed",
            arena_score=800,
            net_wpm=80.0,
            accuracy_pct=100.0,
        ),
    ]

    result = aggregate_participant_rounds(user_id, rounds)
    # (1 * 600 + 3 * 800) / 4 = (600 + 2400) / 4 = 3000 / 4 = 750
    assert result.aggregate_score == 750
    # (1 * 60 + 3 * 80) / 4 = 300 / 4 = 75.0
    assert result.weighted_net_wpm == 75.0
    assert result.is_eligible is True


def test_voided_round_denominator_exclusion_policy() -> None:
    """POLICY INVARIANT: Voided rounds must be excluded from both numerator AND denominator."""
    user_id = uuid.uuid4()
    rounds = [
        RoundScoreItem(
            round_id=uuid.uuid4(),
            sequence_number=1,
            weight=1,
            is_round_voided=False,
            participant_status="completed",
            arena_score=800,
            net_wpm=80.0,
            accuracy_pct=100.0,
        ),
        RoundScoreItem(
            round_id=uuid.uuid4(),
            sequence_number=2,
            weight=1,
            is_round_voided=True,  # VOIDED ROUND!
            participant_status="round_voided",
            arena_score=0,
            net_wpm=0.0,
            accuracy_pct=0.0,
        ),
        RoundScoreItem(
            round_id=uuid.uuid4(),
            sequence_number=3,
            weight=1,
            is_round_voided=False,
            participant_status="completed",
            arena_score=900,
            net_wpm=90.0,
            accuracy_pct=100.0,
        ),
    ]

    result = aggregate_participant_rounds(user_id, rounds)
    # Denominator must be 2 (NOT 3!): (800 + 900) / 2 = 850
    assert result.aggregate_score == 850
    assert result.weighted_net_wpm == 85.0
    assert result.voided_rounds_count == 1
    assert result.total_rounds_considered == 2
    assert result.is_eligible is True


def test_no_show_contributes_zero_with_full_denominator() -> None:
    """Verify that a no-show in a mandatory round contributes 0 points while retaining denominator weight."""
    user_id = uuid.uuid4()
    rounds = [
        RoundScoreItem(
            round_id=uuid.uuid4(),
            sequence_number=1,
            weight=1,
            is_round_voided=False,
            participant_status="completed",
            arena_score=800,
            net_wpm=80.0,
            accuracy_pct=100.0,
        ),
        RoundScoreItem(
            round_id=uuid.uuid4(),
            sequence_number=2,
            weight=1,
            is_round_voided=False,
            participant_status="no_show",  # Did not attend Round 2
            arena_score=0,
            net_wpm=0.0,
            accuracy_pct=0.0,
        ),
    ]

    result = aggregate_participant_rounds(user_id, rounds)
    # (1 * 800 + 1 * 0) / 2 = 400
    assert result.aggregate_score == 400
    assert result.weighted_net_wpm == 40.0
    assert result.is_eligible is True


def test_disqualification_strips_eligibility_and_zeroes_score() -> None:
    """Verify that disqualification in any round strips eligibility and zeroes aggregate score."""
    user_id = uuid.uuid4()
    rounds = [
        RoundScoreItem(
            round_id=uuid.uuid4(),
            sequence_number=1,
            weight=1,
            is_round_voided=False,
            participant_status="completed",
            arena_score=950,
            net_wpm=95.0,
            accuracy_pct=100.0,
        ),
        RoundScoreItem(
            round_id=uuid.uuid4(),
            sequence_number=2,
            weight=1,
            is_round_voided=False,
            participant_status="disqualified",  # Disqualified in Round 2
            arena_score=0,
            net_wpm=0.0,
            accuracy_pct=0.0,
        ),
    ]

    result = aggregate_participant_rounds(user_id, rounds)
    assert result.aggregate_score == 0
    assert result.is_eligible is False
    assert "disqualified" in str(result.ineligibility_reason)
