"""TypeVector Arena — Ranked Input Engine & Property-Based Invariant Tests."""

import random
import unicodedata

from typevector.domains.ranked_input.engine import (
    apply_ranked_operations,
    canonicalize_insert_text,
    compute_projection_digest,
)
from typevector.domains.ranked_input.protocol import BackspaceOp, InsertOp, RankedOperation


def test_canonicalization_standard_nfc_and_newlines() -> None:
    """Verify v1_standard canonicalization enforces NFC normalization and LF newlines."""
    # Decomposed e + combining acute
    decomposed = "e\u0301"
    canonical = canonicalize_insert_text(decomposed, version="v1_standard")
    assert canonical == "\u00e9"
    assert unicodedata.is_normalized("NFC", canonical)

    # CRLF and CR normalization to \n
    crlf_text = "line1\r\nline2\rline3\nline4"
    res = canonicalize_insert_text(crlf_text, version="v1_standard")
    assert res == "line1\nline2\nline3\nline4"


def test_canonicalization_strips_rogue_control_characters() -> None:
    """Verify that rogue ASCII control codes below 32 (except tab and newline) are stripped."""
    dirty_text = "hello\x00\x07world\twith\nnewlines\x1b[31m"
    clean = canonicalize_insert_text(dirty_text, version="v1_standard")
    assert "\x00" not in clean
    assert "\x07" not in clean
    assert "\x1b" not in clean
    assert "\t" in clean
    assert "\n" in clean
    assert clean == "helloworld\twith\nnewlines[31m"


def test_projection_tail_insert_and_backspace() -> None:
    """Verify incremental tail operations on text projection."""
    ops: list[RankedOperation] = [
        InsertOp(text="The quick brown"),
        InsertOp(text=" fox"),
        BackspaceOp(count=4),
        InsertOp(text=" cat"),
    ]
    text, added, backspaces = apply_ranked_operations("", ops)
    assert text == "The quick brown cat"
    assert added == len("The quick brown") + len(" fox") + len(" cat")
    assert backspaces == 4


def test_projection_over_backspace_clamps_to_empty() -> None:
    """Verify that backspacing more than the string length clamps cleanly to empty string."""
    ops: list[RankedOperation] = [
        InsertOp(text="short"),
        BackspaceOp(count=100),
    ]
    text, added, backspaces = apply_ranked_operations("", ops)
    assert text == ""
    assert added == 5
    assert backspaces == 5, "Actual backspaces must be clamped to original length 5, not 100"


def test_projection_digest_deterministic() -> None:
    """Verify compute_projection_digest produces correct, repeatable SHA-256."""
    empty_digest = compute_projection_digest("")
    assert empty_digest == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    text = "TypeVector Arena 2026"
    d1 = compute_projection_digest(text)
    d2 = compute_projection_digest(text)
    assert d1 == d2
    assert len(d1) == 64


def test_property_sequence_monotonicity_and_log_equivalence() -> None:
    """Property-based test: Incremental batch projection equals full-log replay.

    Invariant: For any arbitrary sequence of valid batches, incrementally updating
    the projection across batches 1..N yields the exact same text and digest as
    replaying all operations from the accepted log in one pass.
    """
    random.seed(42)
    sample_words = ["apple", "banana", "cherry", "delta", "echo", "foxtrot", "golf", " ", "\n", "."]

    batches: list[list[RankedOperation]] = []
    all_ops_flat: list[RankedOperation] = []

    # Generate 50 realistic batches
    for _ in range(50):
        batch_ops: list[RankedOperation] = []
        op_count = random.randint(1, 5)
        for _ in range(op_count):
            if random.random() < 0.25 and all_ops_flat:
                # 25% chance of backspace
                cnt = random.randint(1, 4)
                op = BackspaceOp(count=cnt)
            else:
                word = random.choice(sample_words)
                op = InsertOp(text=word)
            batch_ops.append(op)
            all_ops_flat.append(op)
        batches.append(batch_ops)

    # 1. Incremental simulation (how the server evaluates incoming batches S=1..N)
    incremental_text = ""
    for b in batches:
        incremental_text, _, _ = apply_ranked_operations(incremental_text, b)
    incremental_digest = compute_projection_digest(incremental_text)

    # 2. Cumulative log replay (audit replay of the entire accepted log)
    replayed_text, _, _ = apply_ranked_operations("", all_ops_flat)
    replayed_digest = compute_projection_digest(replayed_text)

    assert incremental_text == replayed_text, (
        "Incremental projection must match cumulative log replay"
    )
    assert incremental_digest == replayed_digest, "Digest must match"


def test_property_no_double_apply_invariant() -> None:
    """Property test: Applying a batch twice strictly violates sequence idempotency.

    Proves why the monotonic sequence watermark check (S <= W) and replay logic
    are essential to avoid corrupting the projected state.
    """
    initial_text = "RankedAttempt"
    batch_ops: list[RankedOperation] = [InsertOp(text=" #1")]

    # First legitimate apply
    valid_once, _, _ = apply_ranked_operations(initial_text, batch_ops)
    assert valid_once == "RankedAttempt #1"

    # If applied a second time by mistake (simulating missing sequence gating)
    corrupted_double, _, _ = apply_ranked_operations(valid_once, batch_ops)
    assert corrupted_double == "RankedAttempt #1 #1"

    # Invariant: Double apply produces divergence, proving monotonic sequence gating is required!
    assert corrupted_double != valid_once
