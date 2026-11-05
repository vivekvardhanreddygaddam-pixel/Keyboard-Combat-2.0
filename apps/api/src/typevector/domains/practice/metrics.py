"""TypeVector Arena — Practice Metric Calculations & Educational Explanations.

Defines deterministic formulas for Gross WPM, Net WPM, Accuracy, Completion,
and rule-based diagnostic suggestions.

Every metric documents:
- Numerator
- Denominator
- Unit
- Rounding
- Source of truth
- Limitations
"""

from typing import Any


def calculate_practice_metrics(
    diff_result: dict[str, Any], duration_seconds: float
) -> dict[str, Any]:
    """Calculate comprehensive, explainable typing metrics for a practice attempt.

    METRIC DEFINITIONS:
    1. Gross WPM:
       - Numerator: total_input_chars / 5.0 (Standard 5-stroke word convention)
       - Denominator: duration_seconds / 60.0
       - Unit: Words Per Minute
       - Rounding: 2 decimal places
       - Limitations: Evaluates completed input length; does not penalize uncorrected errors.

    2. Net WPM:
       - Numerator: max(0.0, (correct_chars / 5.0) - uncorrected_errors)
       - Denominator: duration_seconds / 60.0
       - Unit: Words Per Minute
       - Rounding: 2 decimal places
       - Limitations: Clamped at 0.0 WPM; uncorrected mistakes subtract full words.

    3. Accuracy %:
       - Numerator: correct_chars
       - Denominator: total_input_chars
       - Unit: Percentage [0.00 - 100.00]
       - Rounding: 2 decimal places
       - Limitations: Returns 100.00% if zero characters were typed.

    4. Completion %:
       - Numerator: attempted_chars (target characters reached prior to unattempted tail)
       - Denominator: total_target_chars
       - Unit: Percentage [0.00 - 100.00]
       - Rounding: 2 decimal places
    """
    duration = max(0.5, float(duration_seconds))  # Minimum 0.5s to prevent division by zero
    duration_minutes = duration / 60.0

    total_input_chars = diff_result["total_input_chars"]
    total_target_chars = diff_result["total_target_chars"]
    attempted_chars = diff_result["attempted_chars"]
    error_counts = diff_result["error_counts"]

    correct_chars = error_counts.get("match", 0)

    # Active errors committed by the user (excluding unattempted tail)
    uncorrected_errors = (
        error_counts.get("substitution", 0)
        + error_counts.get("omission", 0)
        + error_counts.get("insertion", 0)
        + error_counts.get("case_error", 0)
        + error_counts.get("space_error", 0)
        + error_counts.get("punctuation_error", 0)
        + error_counts.get("digit_symbol_error", 0)
    )

    # Gross WPM
    gross_wpm = (total_input_chars / 5.0) / duration_minutes
    gross_wpm = round(gross_wpm, 2)

    # Net WPM: Deduct 1 standard word (5 strokes) per uncorrected mistake
    raw_net_words = (correct_chars / 5.0) - uncorrected_errors
    net_wpm = max(0.0, raw_net_words / duration_minutes)
    net_wpm = round(net_wpm, 2)

    # Accuracy %
    accuracy_pct = (correct_chars / total_input_chars * 100.0) if total_input_chars > 0 else 100.0
    accuracy_pct = round(min(100.0, max(0.0, accuracy_pct)), 2)

    # Completion %
    if total_target_chars > 0:
        completion_pct = (attempted_chars / total_target_chars) * 100.0
    else:
        completion_pct = 100.0
    completion_pct = round(min(100.0, max(0.0, completion_pct)), 2)

    # Synthesize explainable educational recommendations
    suggestions = generate_diagnostic_suggestions(
        accuracy_pct=accuracy_pct,
        net_wpm=net_wpm,
        error_counts=error_counts,
        completion_pct=completion_pct,
    )

    return {
        "duration_seconds": round(duration, 2),
        "gross_wpm": gross_wpm,
        "net_wpm": net_wpm,
        "accuracy_pct": accuracy_pct,
        "completion_pct": completion_pct,
        "total_keystrokes": total_input_chars,
        "correct_keystrokes": correct_chars,
        "uncorrected_errors": uncorrected_errors,
        "error_counts": error_counts,
        "suggestions": suggestions,
    }


def generate_diagnostic_suggestions(
    accuracy_pct: float,
    net_wpm: float,
    error_counts: dict[str, int],
    completion_pct: float,
) -> list[str]:
    """Generate evidence-backed, transparent recommendations based on actual error frequencies."""
    suggestions: list[str] = []

    case_errors = error_counts.get("case_error", 0)
    space_errors = error_counts.get("space_error", 0)
    punct_errors = error_counts.get("punctuation_error", 0)
    sym_errors = error_counts.get("digit_symbol_error", 0)
    omissions = error_counts.get("omission", 0)
    insertions = error_counts.get("insertion", 0)

    if completion_pct < 80.0:
        suggestions.append(
            f"Passage incomplete ({completion_pct}%). Focus on finishing full sentences before accelerating."
        )

    if case_errors >= 3:
        suggestions.append(
            f"Shift key coordination: {case_errors} capitalization errors detected. "
            "Ensure the Shift key is held until the character registers, then released cleanly."
        )

    if space_errors >= 3:
        suggestions.append(
            f"Thumb cadence: {space_errors} spacing errors observed. "
            "Anchor your dominant thumb consistently above the spacebar."
        )

    if punct_errors >= 3:
        suggestions.append(
            f"Punctuation accuracy: {punct_errors} punctuation errors recorded. "
            "Recommend the Sentences & Punctuation mode drill to stabilize finger reaches."
        )

    if sym_errors >= 3:
        suggestions.append(
            f"Number & symbol precision: {sym_errors} top-row errors detected. "
            "Practice the Numbers & Symbol Precision module to eliminate top-row hesitation."
        )

    if omissions > 3 and insertions > 3:
        suggestions.append(
            "Rushing & skipping: High alternating omissions and extra characters suggest typing ahead of visual buffer. "
            "Slow down cadence to eliminate burst mistakes."
        )

    if accuracy_pct < 94.0:
        suggestions.append(
            f"Accuracy priority: Net accuracy is {accuracy_pct}%. "
            "Aim for at least 98% accuracy in Practice before attempting high-speed tournament rounds."
        )
    elif accuracy_pct >= 98.5 and net_wpm >= 65.0:
        suggestions.append(
            f"Exceptional precision: {accuracy_pct}% accuracy at {net_wpm} Net WPM. "
            "You are ready for Speed Sprint or competitive Arena rounds."
        )

    if not suggestions:
        suggestions.append(
            "Balanced typing rhythm observed. Maintain consistent finger recovery to the home row."
        )

    return suggestions
