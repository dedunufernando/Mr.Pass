"""Candidate scoring — Shannon entropy + pattern classification + sorting."""
from __future__ import annotations
import math
import re
from collections import Counter
from typing import Iterable

from .filter import walk_ratio, QWERTY_ADJ


# ---------------------------------------------------------------------------
# Entropy
# ---------------------------------------------------------------------------

def shannon_bits(pw: str) -> float:
    """Shannon entropy in bits for a password string."""
    if not pw:
        return 0.0
    freq = Counter(pw)
    total = len(pw)
    return -sum((c / total) * math.log2(c / total) for c in freq.values())


def charset_entropy(pw: str) -> float:
    """
    Estimate entropy based on detected character classes.
    More reliable than Shannon alone for short passwords.
    """
    pool = 0
    if any(c.islower() for c in pw):
        pool += 26
    if any(c.isupper() for c in pw):
        pool += 26
    if any(c.isdigit() for c in pw):
        pool += 10
    if any(not c.isalnum() for c in pw):
        pool += 32
    if pool == 0:
        pool = 1
    return len(pw) * math.log2(pool)


# ---------------------------------------------------------------------------
# Pattern classification
# ---------------------------------------------------------------------------

def classify(pw: str) -> str:
    """Return the dominant pattern class of a password."""
    # Pure numeric first — "1234567" is numeric, not keyboard_walk
    if re.fullmatch(r'\d+', pw):
        return "numeric"
    # Keyboard walk before alpha — "qwerty" is a walk, not plain alpha
    if walk_ratio(pw) > 0.6:
        return "keyboard_walk"
    if re.fullmatch(r'[a-zA-Z]+', pw):
        return "alpha"
    if re.search(r'(.)\1{2,}', pw):
        return "repeat_block"
    if re.search(r'(19|20)\d{2}$', pw):
        return "date_suffix"
    if any(c in pw for c in '@$!#%^&*'):
        return "symbol_mutant"
    if re.fullmatch(r'[a-zA-Z0-9]+', pw):
        return "alnum_mixed"
    return "mixed"


# ---------------------------------------------------------------------------
# Scored candidate
# ---------------------------------------------------------------------------

def score(pw: str) -> dict:
    """Return a score dict for a single candidate."""
    s = shannon_bits(pw)
    cs = charset_entropy(pw)
    return {
        "pw": pw,
        "shannon_bits": round(s, 3),
        "charset_bits": round(cs, 3),
        "pattern": classify(pw),
        "length": len(pw),
    }


# ---------------------------------------------------------------------------
# Batch sorting
# ---------------------------------------------------------------------------

def sort_by_entropy(candidates: list[str], descending: bool = True) -> list[str]:
    return sorted(candidates, key=shannon_bits, reverse=descending)


def sort_by_charset_entropy(candidates: list[str], descending: bool = True) -> list[str]:
    return sorted(candidates, key=charset_entropy, reverse=descending)


def top_n(candidates: Iterable[str], n: int) -> list[str]:
    """Return the n highest-entropy candidates without sorting the full list."""
    import heapq
    # heapq.nlargest with key
    return heapq.nlargest(n, candidates, key=shannon_bits)
