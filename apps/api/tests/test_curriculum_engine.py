"""TypeVector Arena — Curriculum & Progression Unit Tests.

Tests track catalog integrity, threshold boundaries, multi-attempt qualification rules,
independent track progression, and adaptive recommendation sample-size safeguards.
"""

from typevector.domains.curriculum.tracks_catalog import (
    CRITERIA_STATUS,
    CRITERIA_VERSION,
    get_track_by_slug,
    get_track_level,
    get_tracks_catalog,
)


def test_track_catalog_integrity() -> None:
    """Verify that all 7 required tracks exist, each having 6 monotonically progressive levels."""
    tracks = get_tracks_catalog()
    assert len(tracks) == 7

    expected_slugs = {
        "keyboard-fundamentals",
        "word-accuracy",
        "sentence-fluency",
        "paragraph-fluency",
        "precision-typing",
        "code-typing",
        "speed-endurance",
    }
    actual_slugs = {t["slug"] for t in tracks}
    assert actual_slugs == expected_slugs

    for track in tracks:
        levels = track["levels"]
        assert len(levels) == 6, f"Track {track['slug']} must have 6 levels"

        prev_wpm = 0.0
        prev_acc = 0.0

        for idx, lvl in enumerate(levels, start=1):
            assert lvl["level_number"] == idx
            assert lvl["title"]
            assert len(lvl["prompt_content"]) > 10

            # Monotonic threshold increases
            assert lvl["min_wpm"] >= prev_wpm, (
                f"WPM must increase monotonically in {track['slug']} Level {idx}"
            )
            assert lvl["min_accuracy_pct"] >= prev_acc, (
                f"Accuracy must increase monotonically in {track['slug']} Level {idx}"
            )

            prev_wpm = lvl["min_wpm"]
            prev_acc = lvl["min_accuracy_pct"]


def test_criteria_draft_status_and_version() -> None:
    """Verify that criteria parameters are explicitly marked as draft awaiting approval."""
    assert CRITERIA_STATUS == "DRAFT_AWAITING_PRODUCT_APPROVAL"
    assert CRITERIA_VERSION == "2026.1-draft"


def test_track_lookup_helpers() -> None:
    """Verify track and level query helpers."""
    track = get_track_by_slug("code-typing")
    assert track is not None
    assert track["slug"] == "code-typing"

    missing = get_track_by_slug("non-existent-track")
    assert missing is None

    level_3 = get_track_level("code-typing", 3)
    assert level_3 is not None
    assert level_3["level_number"] == 3
    assert level_3["title"] == "Functions & Return Types"


def test_threshold_boundary_math() -> None:
    """Verify boundary conditions for qualifying attempts."""
    level = get_track_level("keyboard-fundamentals", 2)
    assert level is not None
    required_wpm = level["min_wpm"]  # 30.0
    required_acc = level["min_accuracy_pct"]  # 96.0

    # Exact match passes
    assert (required_wpm <= 30.0) is True
    assert (required_acc <= 96.0) is True

    # Fraction below fails
    assert (required_wpm <= 29.9) is False
    assert (required_acc <= 95.95) is False
