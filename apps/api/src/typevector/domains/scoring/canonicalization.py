"""TypeVector Arena — Official Scoring Canonicalization and Typing Unit Segmentation."""

import hashlib
import unicodedata
from enum import StrEnum

CANONICALIZATION_SPEC_VERSION = "2026.1-official"


class CanonicalizationMode(StrEnum):
    """Authoritative canonicalization modes for tournament competition."""

    PARAGRAPH_GRAPHEME_V1 = "canonical-paragraph-v1"
    CODE_SCALAR_V1 = "canonical-code-v1"


def _is_grapheme_extend_or_spacing(char: str) -> bool:
    """Return True if character extends or combines with previous base character."""
    cat = unicodedata.category(char)
    # Mn: Nonspacing Mark, Mc: Spacing Mark, Me: Enclosing Mark
    if cat in ("Mn", "Mc", "Me"):
        return True
    # Variation selectors (VS1-VS16, VS17-VS256)
    cp = ord(char)
    return bool(65024 <= cp <= 65039 or 917760 <= cp <= 917999)


def segment_grapheme_clusters(text: str) -> list[str]:
    """Segment NFC-normalized text into extended grapheme clusters (UAX #29 pinned v1).

    Ensures that combined marks, emoji sequences, and ZWJ clusters count as single
    typing units, and raw UTF-8 byte counts are NEVER used as typing units.
    """
    if not text:
        return []

    # 1. NFC normalization
    normalized = unicodedata.normalize("NFC", text)
    # 2. Normalize CRLF and CR to LF once
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

    clusters: list[str] = []
    current_cluster: list[str] = []
    in_zwj = False

    for char in normalized:
        if not current_cluster:
            current_cluster.append(char)
            in_zwj = char == "\u200d"
            continue

        # If previous was ZWJ, next character joins the same cluster
        if in_zwj:
            current_cluster.append(char)
            in_zwj = char == "\u200d"
            continue

        if char == "\u200d":
            current_cluster.append(char)
            in_zwj = True
            continue

        # Combining marks or variation selectors join the current cluster
        if _is_grapheme_extend_or_spacing(char):
            current_cluster.append(char)
        else:
            # Regional indicators (flag sequence)
            prev_char = current_cluster[-1]
            if (
                0x1F1E6 <= ord(prev_char) <= 0x1F1FF
                and 0x1F1E6 <= ord(char) <= 0x1F1FF
                and len(current_cluster) == 1
            ):
                current_cluster.append(char)
                clusters.append("".join(current_cluster))
                current_cluster = []
            else:
                clusters.append("".join(current_cluster))
                current_cluster = [char]

    if current_cluster:
        clusters.append("".join(current_cluster))

    return clusters


def segment_code_scalars(text: str) -> list[str]:
    """Segment code text into Unicode scalar values with single CRLF/CR to LF normalization.

    Preserves tabs, spaces, indentation, casing, punctuation, and newlines exactly as typed.
    """
    if not text:
        return []

    # Normalize CRLF and CR to LF once at boundary
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    # Return sequence of individual Unicode scalars
    return list(normalized)


def segment_typing_units(
    text: str,
    mode: CanonicalizationMode | str = CanonicalizationMode.PARAGRAPH_GRAPHEME_V1,
) -> list[str]:
    """Segment input text into authoritative tournament typing units."""
    mode_str = str(mode)
    if mode_str == CanonicalizationMode.CODE_SCALAR_V1:
        return segment_code_scalars(text)
    return segment_grapheme_clusters(text)


def compute_canonical_digest(units: list[str]) -> str:
    """Compute deterministic SHA-256 digest over canonicalized unit sequence."""
    payload = "\x1f".join(units).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
