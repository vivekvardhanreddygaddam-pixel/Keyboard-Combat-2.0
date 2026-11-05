"""TypeVector Arena — Unit & Property Tests for Practice Engine.

Tests canonicalization, deterministic sequence alignment, metric calculations,
error categorization, and diagnostic recommendations.
"""

from typevector.domains.practice.canonicalization import (
    CanonicalizationVersion,
    canonicalize_text,
)
from typevector.domains.practice.diff_engine import (
    classify_char_diff,
    compute_deterministic_diff,
)
from typevector.domains.practice.metrics import (
    calculate_practice_metrics,
    generate_diagnostic_suggestions,
)


def test_canonicalization_standard_rules() -> None:
    """Verify Unicode NFC, line endings, non-breaking spaces, and trailing whitespace."""
    raw = "The\u00a0quick\r\nbrown  fox\u200b   "
    canon = canonicalize_text(raw, version=CanonicalizationVersion.V1_STANDARD)
    # Non-breaking space converted to ' ', \r\n converted to \n, zero-width space removed, trailing whitespace stripped
    assert "\u00a0" not in canon
    assert "\r" not in canon
    assert "\u200b" not in canon
    assert canon == "The quick\nbrown  fox"


def test_canonicalization_code_preserves_indentation() -> None:
    """Verify tabs converted to 4 spaces and indentation preserved in code mode."""
    code_raw = "\tdef foo():\r\n\t\treturn 42   \r\n"
    canon = canonicalize_text(code_raw, version=CanonicalizationVersion.V1_CODE)
    assert "\t" not in canon
    assert "\r" not in canon
    expected = "    def foo():\n        return 42"
    assert canon == expected


def test_diff_alignment_exact_match() -> None:
    """Verify exact match produces all match segments with 100% completion."""
    target = "The quick brown fox"
    result = compute_deterministic_diff(target, target)
    assert result["total_target_chars"] == len(target)
    assert result["total_input_chars"] == len(target)
    assert result["error_counts"]["match"] == len(target)
    assert result["completion_ratio"] == 1.0
    assert result["unattempted_tail_chars"] == 0
    assert all(s["type"] == "match" for s in result["segments"])


def test_diff_alignment_substitutions_and_casing() -> None:
    """Verify character substitutions and case errors are distinguished."""
    target = "Apple"
    user_input = "apple"  # case error on first char
    result = compute_deterministic_diff(target, user_input)
    assert result["error_counts"]["case_error"] == 1
    assert result["error_counts"]["match"] == 4

    target = "cat"
    user_input = "car"  # substitution 't' -> 'r'
    result = compute_deterministic_diff(target, user_input)
    assert result["error_counts"]["substitution"] == 1
    assert result["error_counts"]["match"] == 2


def test_diff_alignment_omission_and_insertion() -> None:
    """Verify omissions (missing chars) and insertions (extra chars)."""
    # Missing character 'l'
    target = "hello"
    user_input = "helo"
    result = compute_deterministic_diff(target, user_input)
    assert result["error_counts"]["omission"] == 1
    assert result["error_counts"]["match"] == 4

    # Extra character 'l'
    user_input_extra = "helllo"
    result_extra = compute_deterministic_diff(target, user_input_extra)
    assert result_extra["error_counts"]["insertion"] == 1
    assert result_extra["error_counts"]["match"] == 5


def test_diff_alignment_unattempted_tail() -> None:
    """Verify stopped early text is classified as unattempted_tail, not errors."""
    target = "Hello World From Arena"
    user_input = "Hello World"
    result = compute_deterministic_diff(target, user_input)
    assert result["error_counts"]["unattempted_tail"] == len(" From Arena")
    assert result["attempted_chars"] == len("Hello World")
    assert result["completion_ratio"] < 1.0


def test_diff_alignment_repeated_characters_stability() -> None:
    """Verify repeated character sequences produce deterministic, stable alignment."""
    target = "aaaa"
    user_input = "aa"
    res1 = compute_deterministic_diff(target, user_input)
    res2 = compute_deterministic_diff(target, user_input)
    assert res1 == res2
    assert res1["error_counts"]["unattempted_tail"] == 2
    assert res1["error_counts"]["match"] == 2


def test_diff_classification_categories() -> None:
    """Verify fine-grained error category classification."""
    assert classify_char_diff("a", "a") == "match"
    assert classify_char_diff("A", "a") == "case_error"
    assert classify_char_diff(" ", "x") == "space_error"
    assert classify_char_diff("x", " ") == "space_error"
    assert classify_char_diff(",", ".") == "punctuation_error"
    assert classify_char_diff("1", "2") == "digit_symbol_error"
    assert classify_char_diff("a", "b") == "substitution"
    assert classify_char_diff("a", None) == "omission"
    assert classify_char_diff(None, "a") == "insertion"


def test_metric_calculations_formulas() -> None:
    """Verify Gross WPM, Net WPM, Accuracy, and Completion calculations."""
    target = "The quick brown fox jumps over the lazy dog."  # 44 chars
    # Exact match in 30 seconds
    diff_exact = compute_deterministic_diff(target, target)
    metrics_exact = calculate_practice_metrics(diff_exact, duration_seconds=30.0)

    # 44 chars / 5 = 8.8 words in 0.5 minutes = 17.6 WPM
    assert metrics_exact["gross_wpm"] == 17.6
    assert metrics_exact["net_wpm"] == 17.6
    assert metrics_exact["accuracy_pct"] == 100.0
    assert metrics_exact["completion_pct"] == 100.0

    # User with errors: 44 chars typed, 2 uncorrected errors in 30s
    diff_with_errors = {
        "total_input_chars": 44,
        "total_target_chars": 44,
        "attempted_chars": 44,
        "error_counts": {
            "match": 42,
            "substitution": 2,
            "omission": 0,
            "insertion": 0,
            "case_error": 0,
            "space_error": 0,
            "punctuation_error": 0,
            "digit_symbol_error": 0,
            "unattempted_tail": 0,
        },
    }
    metrics_err = calculate_practice_metrics(diff_with_errors, duration_seconds=30.0)
    assert metrics_err["gross_wpm"] == 17.6
    # Net: (42 / 5 - 2) / 0.5 = (8.4 - 2) / 0.5 = 6.4 / 0.5 = 12.8
    assert metrics_err["net_wpm"] == 12.8
    # Accuracy: 42 / 44 * 100 = 95.45%
    assert metrics_err["accuracy_pct"] == 95.45


def test_net_wpm_clamping_at_zero() -> None:
    """Verify that excessive errors clamp Net WPM at 0.0 rather than negative values."""
    diff_all_errors = {
        "total_input_chars": 20,
        "total_target_chars": 20,
        "attempted_chars": 20,
        "error_counts": {
            "match": 0,
            "substitution": 20,
            "omission": 0,
            "insertion": 0,
            "case_error": 0,
            "space_error": 0,
            "punctuation_error": 0,
            "digit_symbol_error": 0,
            "unattempted_tail": 0,
        },
    }
    metrics = calculate_practice_metrics(diff_all_errors, duration_seconds=10.0)
    assert metrics["net_wpm"] == 0.0


def test_diagnostic_suggestions_generation() -> None:
    """Verify evidence-backed explanations cite specific error categories."""
    # High case error scenario
    errors = {
        "match": 50,
        "case_error": 4,
        "space_error": 0,
        "punctuation_error": 0,
        "digit_symbol_error": 0,
        "substitution": 0,
        "omission": 0,
        "insertion": 0,
    }
    suggestions = generate_diagnostic_suggestions(
        accuracy_pct=92.0, net_wpm=45.0, error_counts=errors, completion_pct=100.0
    )
    assert any("Shift key" in s for s in suggestions)
    assert any("Accuracy priority" in s for s in suggestions)
