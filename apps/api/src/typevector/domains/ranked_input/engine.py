"""TypeVector Arena — Ranked Input Projection & Canonicalization Engine."""

import hashlib
import unicodedata

from typevector.domains.ranked_input.protocol import BackspaceOp, InsertOp, RankedOperation


def canonicalize_insert_text(text: str, version: str = "v1_standard") -> str:
    """Canonicalize inserted text according to pinned challenge rules.

    - v1_standard: Unicode NFC normalization, uniform LF line endings (\n),
      filter out rogue ASCII control codes (below 32) except \t and \n.
    """
    if version == "v1_standard":
        normalized = unicodedata.normalize("NFC", text)
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        # Strip ASCII control characters except \t and \n
        filtered = "".join(ch for ch in normalized if ord(ch) >= 32 or ch in ("\t", "\n"))
        return filtered
    return unicodedata.normalize("NFC", text)


def compute_projection_digest(text: str) -> str:
    """Compute deterministic SHA-256 hex digest of current text projection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply_ranked_operations(
    current_text: str,
    operations: list[RankedOperation],
    canonical_version: str = "v1_standard",
) -> tuple[str, int, int]:
    """Apply constrained tail operations (Insert and Backspace) to text projection.

    Returns:
        (new_text, added_keystrokes, actual_backspaces)
    """
    text = current_text
    added_keystrokes = 0
    actual_backspaces = 0

    for op in operations:
        if isinstance(op, InsertOp) or (isinstance(op, dict) and op.get("type") == "insert"):
            raw_text = op.text if isinstance(op, InsertOp) else op["text"]
            canonical = canonicalize_insert_text(raw_text, version=canonical_version)
            text += canonical
            added_keystrokes += len(canonical)
        elif isinstance(op, BackspaceOp) or (
            isinstance(op, dict) and op.get("type") == "backspace"
        ):
            cnt = op.count if isinstance(op, BackspaceOp) else op["count"]
            delete_len = min(cnt, len(text))
            if delete_len > 0:
                text = text[:-delete_len]
                actual_backspaces += delete_len

    return text, added_keystrokes, actual_backspaces
