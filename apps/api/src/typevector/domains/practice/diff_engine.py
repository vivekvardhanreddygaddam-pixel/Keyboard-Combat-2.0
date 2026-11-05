"""TypeVector Arena — Deterministic Alignment & Diff Engine.

Computes character-level and category-level alignment diffs between target prompt
and user input. Educational alignment is strictly separated from ranked arena scoring.
"""

import difflib
import string
import unicodedata
from typing import Any

PUNCTUATION_CHARS = set(string.punctuation + "“”‘’—…")


def classify_char_diff(expected: str | None, actual: str | None) -> str:
    """Classify the mismatch category between an expected character and actual typed character."""
    if expected is not None and actual is not None:
        if expected == actual:
            return "match"
        if expected.lower() == actual.lower():
            return "case_error"
        if expected == " " or actual == " ":
            return "space_error"
        if expected in PUNCTUATION_CHARS or actual in PUNCTUATION_CHARS:
            return "punctuation_error"
        if expected.isdigit() or actual.isdigit():
            return "digit_symbol_error"
        return "substitution"
    if expected is not None and actual is None:
        return "omission"
    if expected is None and actual is not None:
        return "insertion"
    return "unknown"


def align_tokens_needleman_wunsch(
    target_sub: str, input_sub: str
) -> list[tuple[str | None, str | None]]:
    """Fine-grained dynamic programming alignment for mismatched blocks."""
    m = len(target_sub)
    n = len(input_sub)

    # dp[i][j] stores max score
    dp = [[0.0] * (n + 1) for _ in range(m + 1)]

    # Weights
    match_score = 2.0
    sub_cost = -1.0
    del_cost = -1.5
    ins_cost = -1.5

    for i in range(1, m + 1):
        dp[i][0] = i * del_cost
    for j in range(1, n + 1):
        dp[0][j] = j * ins_cost

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if target_sub[i - 1] == input_sub[j - 1]:
                score = match_score
            elif target_sub[i - 1].lower() == input_sub[j - 1].lower():
                score = sub_cost + 0.5  # slight preference for case matches
            else:
                score = sub_cost

            match_branch = dp[i - 1][j - 1] + score
            del_branch = dp[i - 1][j] + del_cost
            ins_branch = dp[i][j - 1] + ins_cost

            # Deterministic tie-breaking: match/sub > del > ins
            dp[i][j] = max(match_branch, del_branch, ins_branch)

    # Backtracking
    i = m
    j = n
    aligned: list[tuple[str | None, str | None]] = []

    while i > 0 or j > 0:
        if i > 0 and j > 0:
            if target_sub[i - 1] == input_sub[j - 1]:
                score = match_score
            elif target_sub[i - 1].lower() == input_sub[j - 1].lower():
                score = sub_cost + 0.5
            else:
                score = sub_cost

            if abs(dp[i][j] - (dp[i - 1][j - 1] + score)) < 1e-6:
                aligned.append((target_sub[i - 1], input_sub[j - 1]))
                i -= 1
                j -= 1
                continue

        if i > 0 and abs(dp[i][j] - (dp[i - 1][j] + del_cost)) < 1e-6:
            aligned.append((target_sub[i - 1], None))
            i -= 1
            continue

        if j > 0 and abs(dp[i][j] - (dp[i][j - 1] + ins_cost)) < 1e-6:
            aligned.append((None, input_sub[j - 1]))
            j -= 1
            continue

        # Fallback to avoid infinite loop
        if i > 0 and j > 0:
            aligned.append((target_sub[i - 1], input_sub[j - 1]))
            i -= 1
            j -= 1
        elif i > 0:
            aligned.append((target_sub[i - 1], None))
            i -= 1
        else:
            aligned.append((None, input_sub[j - 1]))
            j -= 1

    aligned.reverse()
    return aligned


def compute_deterministic_diff(target: str, user_input: str) -> dict[str, Any]:
    """Perform deterministic alignment between target prompt and user input.

    Returns:
    - segments: ordered list of character diff tokens
    - error_breakdown: count per category
    - completion_ratio: attempted characters / target characters
    - unattempted_chars: remaining tail count
    """
    # Normalize Unicode NFC for consistent character matching
    target_norm = unicodedata.normalize("NFC", target)
    input_norm = unicodedata.normalize("NFC", user_input)

    matcher = difflib.SequenceMatcher(None, target_norm, input_norm, autojunk=False)
    opcodes = matcher.get_opcodes()

    segments: list[dict[str, Any]] = []
    error_counts: dict[str, int] = {
        "match": 0,
        "substitution": 0,
        "omission": 0,
        "insertion": 0,
        "case_error": 0,
        "space_error": 0,
        "punctuation_error": 0,
        "digit_symbol_error": 0,
        "unattempted_tail": 0,
    }

    # Detect tail: If user stopped before the end of the target
    # The last opcode might be 'delete' representing unattempted text
    last_op_index = len(opcodes) - 1

    for idx, (tag, i1, i2, j1, j2) in enumerate(opcodes):
        if tag == "equal":
            for k in range(i2 - i1):
                ch = target_norm[i1 + k]
                segments.append(
                    {
                        "expected": ch,
                        "actual": ch,
                        "type": "match",
                        "category": "match",
                    }
                )
                error_counts["match"] += 1

        elif tag == "replace":
            # For small blocks, run exact Needleman-Wunsch alignment
            sub_target = target_norm[i1:i2]
            sub_input = input_norm[j1:j2]
            aligned_pairs = align_tokens_needleman_wunsch(sub_target, sub_input)

            for exp, act in aligned_pairs:
                category = classify_char_diff(exp, act)
                token_type = "match" if category == "match" else "error"
                segments.append(
                    {
                        "expected": exp,
                        "actual": act,
                        "type": token_type,
                        "category": category,
                    }
                )
                error_counts[category] = error_counts.get(category, 0) + 1

        elif tag == "delete":
            # Deletion: characters in target that user did not type
            # Check if this deletion is at the very end of input (unattempted tail)
            if idx == last_op_index and j2 == len(input_norm):
                for k in range(i2 - i1):
                    ch = target_norm[i1 + k]
                    segments.append(
                        {
                            "expected": ch,
                            "actual": None,
                            "type": "tail",
                            "category": "unattempted_tail",
                        }
                    )
                    error_counts["unattempted_tail"] += 1
            else:
                for k in range(i2 - i1):
                    ch = target_norm[i1 + k]
                    segments.append(
                        {
                            "expected": ch,
                            "actual": None,
                            "type": "error",
                            "category": "omission",
                        }
                    )
                    error_counts["omission"] += 1

        elif tag == "insert":
            # Insertion: extra characters typed by user
            for k in range(j2 - j1):
                ch = input_norm[j1 + k]
                segments.append(
                    {
                        "expected": None,
                        "actual": ch,
                        "type": "error",
                        "category": "insertion",
                    }
                )
                error_counts["insertion"] += 1

    total_target_chars = len(target_norm)
    total_input_chars = len(input_norm)
    unattempted_tail = error_counts["unattempted_tail"]
    attempted_target_chars = max(0, total_target_chars - unattempted_tail)
    completion_ratio = (
        (attempted_target_chars / total_target_chars) if total_target_chars > 0 else 1.0
    )

    return {
        "segments": segments,
        "error_counts": error_counts,
        "total_target_chars": total_target_chars,
        "total_input_chars": total_input_chars,
        "attempted_chars": attempted_target_chars,
        "unattempted_tail_chars": unattempted_tail,
        "completion_ratio": round(completion_ratio, 4),
    }
