"""TypeVector Arena — Official Scoring Engine (arena-score-v1)."""

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from typevector.domains.scoring.canonicalization import (
    CanonicalizationMode,
    compute_canonical_digest,
    segment_typing_units,
)
from typevector.errors import InvariantViolationError

SCORER_VERSION: Final[str] = "arena-score-v1"
PROTOCOL_VERSION: Final[str] = "arena-ws-v1"
CANONICALIZATION_VERSION: Final[str] = "2026.1-official"

# Scoring Policy Status: unapproved proposed policy cannot be used for prize tournaments
SCORING_POLICY_STATUS: Final[str] = "DRAFT_AWAITING_TOURNAMENT_APPROVAL"

# Exact completion bounds
MAX_INCOMPLETE_SCORE: Final[int] = 699
MIN_COMPLETE_SCORE: Final[int] = 700


@dataclass(frozen=True)
class ScoreMetrics:
    """Deterministic typed score metrics for an official attempt."""

    scorer_version: str
    canonicalization_version: str
    gross_wpm: float
    net_wpm: float
    accuracy_pct: float
    arena_score: int
    is_complete: bool
    completion_ratio: float
    target_units_count: int
    input_units_count: int
    correct_units_count: int
    error_units_count: int
    active_elapsed_ms: int
    canonical_hash: str
    replay_manifest: dict[str, Any]


def compute_official_score(
    challenge_text: str,
    committed_text: str,
    active_elapsed_ms: int,
    mode: CanonicalizationMode | str = CanonicalizationMode.PARAGRAPH_GRAPHEME_V1,
    configuration_metadata: dict[str, Any] | None = None,
) -> ScoreMetrics:
    """Compute official tournament score adhering strictly to arena-score-v1 specifications.

    INVARIANTS:
    1. Guard N > 0: Challenge prompt must contain at least 1 typing unit.
    2. Guard D > 0: Active elapsed time must be strictly positive (clamped to min 100ms).
    3. Incomplete attempts must score <= 699.
    4. Exact completed attempts must score >= 700.
    5. Never count raw UTF-8 bytes as typing units.
    """
    # 1. Segment target challenge prompt into typing units
    target_units = segment_typing_units(challenge_text, mode)
    n = len(target_units)
    if n <= 0:
        raise InvariantViolationError("Target challenge prompt cannot be empty (N > 0 required).")

    # 2. Segment committed participant input into typing units
    input_units = segment_typing_units(committed_text, mode)
    m = len(input_units)

    # 3. Guard elapsed active duration D > 0
    d_ms = max(100, int(active_elapsed_ms))

    # 4. Compare typing units linearly
    correct_count = 0
    mismatch_count = 0
    min_len = min(m, n)

    for i in range(min_len):
        if input_units[i] == target_units[i]:
            correct_count += 1
        else:
            mismatch_count += 1

    # Excess input characters beyond target length count as errors
    extra_count = max(0, m - n)
    error_count = mismatch_count + extra_count

    # 5. Completion assessment
    is_complete = (m == n) and (correct_count == n) and (error_count == 0)
    completion_ratio = round(correct_count / n, 4)

    # 6. Gross WPM (Standard 5-stroke word convention)
    # Gross WPM = (m / 5.0) / (d_ms / 60000.0) = (m * 12000.0) / d_ms
    gross_wpm = round((m * 12000.0) / d_ms, 2)

    # 7. Net WPM (Gross minus uncorrected errors penalty)
    # Net WPM = ((correct_count / 5.0) - error_count) / (d_ms / 60000.0)
    net_wpm_raw = (correct_count * 12000.0 - error_count * 60000.0) / d_ms
    net_wpm = max(0.0, round(net_wpm_raw, 2))

    # 8. Accuracy Percentage
    accuracy_pct = 100.0 if m == 0 else round(correct_count / m * 100.0, 2)

    # 9. Gated Integer Arena Score Calculation
    if not is_complete:
        # Incomplete attempt: strictly clamped to [0, 699]
        if correct_count == 0 or net_wpm <= 0.0:
            arena_score = 0
        else:
            speed_factor = min(1.0, net_wpm / 100.0)
            acc_factor = accuracy_pct / 100.0
            raw_score = math.floor(
                MAX_INCOMPLETE_SCORE * completion_ratio * acc_factor * speed_factor
            )
            arena_score = min(MAX_INCOMPLETE_SCORE, max(0, raw_score))
    else:
        # Exact completion: guaranteed >= 700
        speed_bonus = math.floor(net_wpm * 2.0 * (accuracy_pct / 100.0))
        arena_score = MIN_COMPLETE_SCORE + max(0, speed_bonus)

    # 10. Canonical and Replay Hashes
    canonical_hash = compute_canonical_digest(input_units)
    challenge_digest = compute_canonical_digest(target_units)
    config_dict = configuration_metadata or {}
    config_digest = hashlib.sha256(
        json.dumps(config_dict, sort_keys=True).encode("utf-8")
    ).hexdigest()

    manifest_dict = {
        "scorer_version": SCORER_VERSION,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "canonicalization_mode": str(mode),
        "challenge_digest_sha256": challenge_digest,
        "accepted_input_evidence_digest_sha256": canonical_hash,
        "configuration_digest_sha256": config_digest,
        "gross_wpm": gross_wpm,
        "net_wpm": net_wpm,
        "accuracy_pct": accuracy_pct,
        "arena_score": arena_score,
        "is_complete": is_complete,
        "completion_ratio": completion_ratio,
        "target_units_count": n,
        "input_units_count": m,
        "correct_units_count": correct_count,
        "error_units_count": error_count,
        "active_elapsed_ms": d_ms,
        "computed_at": datetime.now(UTC).isoformat(),
    }
    manifest_raw = json.dumps(manifest_dict, sort_keys=True).encode("utf-8")
    manifest_digest = hashlib.sha256(manifest_raw).hexdigest()
    manifest_dict["manifest_digest_sha256"] = manifest_digest

    return ScoreMetrics(
        scorer_version=SCORER_VERSION,
        canonicalization_version=CANONICALIZATION_VERSION,
        gross_wpm=gross_wpm,
        net_wpm=net_wpm,
        accuracy_pct=accuracy_pct,
        arena_score=arena_score,
        is_complete=is_complete,
        completion_ratio=completion_ratio,
        target_units_count=n,
        input_units_count=m,
        correct_units_count=correct_count,
        error_units_count=error_count,
        active_elapsed_ms=d_ms,
        canonical_hash=canonical_hash,
        replay_manifest=manifest_dict,
    )


def verify_score_replay(
    challenge_text: str,
    committed_text: str,
    active_elapsed_ms: int,
    manifest: dict[str, Any],
) -> bool:
    """Verify bitwise reproducible replay against a stored manifest."""
    mode = manifest.get("canonicalization_mode", CanonicalizationMode.PARAGRAPH_GRAPHEME_V1)
    recomputed = compute_official_score(
        challenge_text=challenge_text,
        committed_text=committed_text,
        active_elapsed_ms=active_elapsed_ms,
        mode=mode,
    )
    return (
        recomputed.arena_score == manifest.get("arena_score")
        and math.isclose(recomputed.gross_wpm, manifest.get("gross_wpm", 0.0), rel_tol=1e-5)
        and math.isclose(recomputed.net_wpm, manifest.get("net_wpm", 0.0), rel_tol=1e-5)
        and math.isclose(recomputed.accuracy_pct, manifest.get("accuracy_pct", 0.0), rel_tol=1e-5)
        and recomputed.is_complete == manifest.get("is_complete")
        and recomputed.canonical_hash == manifest.get("accepted_input_evidence_digest_sha256")
    )
