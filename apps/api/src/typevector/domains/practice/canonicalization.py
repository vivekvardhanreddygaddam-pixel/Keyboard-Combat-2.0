"""TypeVector Arena — Practice Input Canonicalization.

Provides deterministic, versioned canonicalization for user practice inputs
and target prompt texts.
"""

import re
import unicodedata
from enum import StrEnum


class CanonicalizationVersion(StrEnum):
    V1_STANDARD = "v1_standard"
    V1_CODE = "v1_code"


def canonicalize_text(
    text: str, version: CanonicalizationVersion = CanonicalizationVersion.V1_STANDARD
) -> str:
    """Canonicalize a text string according to the specified version.

    Rules applied:
    - Unicode NFC normalization: Combines characters deterministically.
    - Uniform line breaks: Normalizes CRLF and CR to LF (\\n).
    - Non-breaking spaces and zero-width spaces normalized or removed.
    - Code mode preserves exact whitespace and indentation; standard mode normalizes trailing whitespace.
    """
    if not text:
        return ""

    # 1. Unicode NFC normalization
    normalized = unicodedata.normalize("NFC", text)

    # 2. Line ending normalization
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

    # 3. Replace non-breaking spaces (U+00A0) with standard ASCII space
    normalized = normalized.replace("\u00a0", " ")

    # 4. Strip zero-width characters (U+200B, U+FEFF, etc.)
    normalized = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", normalized)

    if version == CanonicalizationVersion.V1_CODE:
        # Code mode: convert horizontal tabs to 4 spaces consistently
        normalized = normalized.replace("\t", "    ")
        # Do not strip indentation; strip trailing whitespace on individual lines
        lines = [line.rstrip(" \t") for line in normalized.split("\n")]
        return "\n".join(lines).rstrip()

    # Standard mode: strip trailing space, preserve internal spacing
    return normalized.rstrip()
