"""Formatting-only normalization for offline evidence-span matching."""
import re


def normalize_evidence_span(text: str) -> str:
    # PDF parser versions can join words or insert spaces around math/symbols.
    # Preserve every non-whitespace character, including punctuation/negation.
    # This is character-span matching, not semantic or token-boundary matching.
    return re.sub(r"\s+", "", text).casefold()
