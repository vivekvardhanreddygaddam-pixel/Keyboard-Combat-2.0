"""TypeVector Arena — Golden Test Vectors for arena-score-v1 and Canonicalization."""

import pytest

from typevector.domains.scoring.canonicalization import (
    CanonicalizationMode,
    segment_grapheme_clusters,
    segment_typing_units,
)
from typevector.domains.scoring.engine import (
    MAX_INCOMPLETE_SCORE,
    MIN_COMPLETE_SCORE,
    compute_official_score,
)
from typevector.errors import InvariantViolationError


def test_guard_against_empty_challenge_prompt() -> None:
    """Invariant: Challenge prompt cannot be empty (N > 0 required)."""
    with pytest.raises(InvariantViolationError) as exc:
        compute_official_score(
            challenge_text="",
            committed_text="hello",
            active_elapsed_ms=10000,
        )
    assert "N > 0 required" in str(exc.value)


def test_golden_vector_empty_input() -> None:
    """Golden Vector 1: Participant committed zero characters."""
    metrics = compute_official_score(
        challenge_text="The quick brown fox jumps over the lazy dog.",
        committed_text="",
        active_elapsed_ms=30000,
    )
    assert metrics.input_units_count == 0
    assert metrics.correct_units_count == 0
    assert metrics.error_units_count == 0
    assert metrics.gross_wpm == 0.0
    assert metrics.net_wpm == 0.0
    assert metrics.accuracy_pct == 100.00  # Conventional default when no errors made
    assert metrics.is_complete is False
    assert metrics.arena_score == 0
    assert metrics.arena_score <= MAX_INCOMPLETE_SCORE


def test_golden_vector_first_unit_mismatch() -> None:
    """Golden Vector 2: First unit typed incorrectly."""
    metrics = compute_official_score(
        challenge_text="Python programming",
        committed_text="J",  # Should be 'P'
        active_elapsed_ms=5000,
    )
    assert metrics.input_units_count == 1
    assert metrics.correct_units_count == 0
    assert metrics.error_units_count == 1
    assert metrics.net_wpm == 0.0
    assert metrics.accuracy_pct == 0.0
    assert metrics.is_complete is False
    assert metrics.arena_score == 0
    assert metrics.arena_score <= MAX_INCOMPLETE_SCORE


def test_golden_vector_substitutions() -> None:
    """Golden Vector 3: Typos / character substitutions penalize Net WPM."""
    metrics = compute_official_score(
        challenge_text="abcdefghij",  # 10 chars
        committed_text="abcxefghij",  # 1 substitution ('x' instead of 'd')
        active_elapsed_ms=10000,  # 10s
    )
    assert metrics.correct_units_count == 9
    assert metrics.error_units_count == 1
    assert metrics.is_complete is False  # Has error, so not exact completion
    assert metrics.accuracy_pct == 90.00
    # Gross WPM = (10 / 5) / (10 / 60) = 12.00
    assert metrics.gross_wpm == 12.00
    # Net WPM = (9/5 - 1) / (10/60) = (1.8 - 1) * 6 = 4.80
    assert metrics.net_wpm == 4.80
    assert metrics.arena_score <= MAX_INCOMPLETE_SCORE


def test_golden_vector_extra_units_beyond_target() -> None:
    """Golden Vector 4: Excess typing beyond target length counts as errors."""
    metrics = compute_official_score(
        challenge_text="hello",  # 5 units
        committed_text="helloworld",  # 10 units (5 extra)
        active_elapsed_ms=10000,
    )
    assert metrics.correct_units_count == 5
    assert metrics.error_units_count == 5
    assert metrics.is_complete is False
    assert metrics.accuracy_pct == 50.00
    assert metrics.arena_score <= MAX_INCOMPLETE_SCORE


def test_golden_vector_exact_completion_at_multiple_durations() -> None:
    """Golden Vector 5: Exact completions across durations always score >= 700."""
    target = "Competitive typing integrity is foundational to tournament esports."
    len(target)

    # Fast 15s completion (high WPM)
    fast_metrics = compute_official_score(
        challenge_text=target,
        committed_text=target,
        active_elapsed_ms=15000,
    )
    assert fast_metrics.is_complete is True
    assert fast_metrics.accuracy_pct == 100.00
    assert fast_metrics.arena_score >= MIN_COMPLETE_SCORE
    assert fast_metrics.net_wpm > 50.0

    # Normal 60s completion
    normal_metrics = compute_official_score(
        challenge_text=target,
        committed_text=target,
        active_elapsed_ms=60000,
    )
    assert normal_metrics.is_complete is True
    assert normal_metrics.accuracy_pct == 100.00
    assert normal_metrics.arena_score >= MIN_COMPLETE_SCORE

    # Slower 120s completion
    slow_metrics = compute_official_score(
        challenge_text=target,
        committed_text=target,
        active_elapsed_ms=120000,
    )
    assert slow_metrics.is_complete is True
    assert slow_metrics.accuracy_pct == 100.00
    assert slow_metrics.arena_score >= MIN_COMPLETE_SCORE

    # Faster completion must strictly score higher than slower completion
    assert fast_metrics.arena_score > normal_metrics.arena_score > slow_metrics.arena_score


def test_golden_vector_timeout_incomplete_score_boundary() -> None:
    """Golden Vector 6: 99% complete attempt timed out must NOT breach 699 ceiling."""
    target = "A" * 100
    # Participant typed 99 correct characters out of 100 at 120 WPM
    committed = "A" * 99
    metrics = compute_official_score(
        challenge_text=target,
        committed_text=committed,
        active_elapsed_ms=10000,
    )
    assert metrics.is_complete is False
    assert metrics.completion_ratio == 0.99
    assert metrics.accuracy_pct == 100.00
    # Even at elite speed, must not reach 700!
    assert metrics.arena_score <= MAX_INCOMPLETE_SCORE
    assert metrics.arena_score >= 600


def test_golden_vector_unicode_never_counts_raw_bytes() -> None:
    """Golden Vector 7: Multi-byte Unicode characters must count as single typing units, not UTF-8 bytes."""
    # "café" in NFC is 4 characters (c, a, f, é). In UTF-8, 'é' is 2 bytes (total 5 bytes).
    target_cafe = "café"
    units_cafe = segment_grapheme_clusters(target_cafe)
    assert len(units_cafe) == 4
    assert len(target_cafe.encode("utf-8")) == 5

    # Japanese greeting "こんにちは" has 5 characters (15 bytes in UTF-8)
    target_jp = "こんにちは"
    units_jp = segment_grapheme_clusters(target_jp)
    assert len(units_jp) == 5
    assert len(target_jp.encode("utf-8")) == 15

    # Emoji family cluster: 👨‍👩‍👧‍👦 (25 bytes in UTF-8, 1 extended grapheme cluster)
    target_emoji = "👨‍👩‍👧‍👦"
    units_emoji = segment_grapheme_clusters(target_emoji)
    assert len(units_emoji) == 1
    assert len(target_emoji.encode("utf-8")) == 25

    metrics = compute_official_score(
        challenge_text=target_jp,
        committed_text=target_jp,
        active_elapsed_ms=5000,
    )
    assert metrics.target_units_count == 5
    assert metrics.input_units_count == 5
    assert metrics.is_complete is True
    assert metrics.arena_score >= MIN_COMPLETE_SCORE


def test_golden_vector_code_whitespace_and_newlines() -> None:
    """Golden Vector 8: Code canonicalization preserves indentation, spaces, and LF newlines."""
    code_prompt = "def add(a, b):\r\n    return a + b\n"
    code_typed = "def add(a, b):\n    return a + b\n"

    units_prompt = segment_typing_units(code_prompt, CanonicalizationMode.CODE_SCALAR_V1)
    units_typed = segment_typing_units(code_typed, CanonicalizationMode.CODE_SCALAR_V1)

    # CRLF normalized once to LF
    assert units_prompt == units_typed

    metrics = compute_official_score(
        challenge_text=code_prompt,
        committed_text=code_typed,
        active_elapsed_ms=10000,
        mode=CanonicalizationMode.CODE_SCALAR_V1,
    )
    assert metrics.is_complete is True
    assert metrics.accuracy_pct == 100.00
    assert metrics.arena_score >= MIN_COMPLETE_SCORE
