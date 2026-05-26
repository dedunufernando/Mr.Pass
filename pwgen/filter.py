"""Post-generation constraint filter — fast-path with early exit."""
from __future__ import annotations
import math
import re
from collections import Counter

from .rule_compiler import RuleSet

QWERTY_ADJ: dict[str, list[str]] = {
    '1': ['2', 'q'],           '2': ['1', '3', 'q', 'w'],
    '3': ['2', '4', 'w', 'e'], '4': ['3', '5', 'e', 'r'],
    '5': ['4', '6', 'r', 't'], '6': ['5', '7', 't', 'y'],
    '7': ['6', '8', 'y', 'u'], '8': ['7', '9', 'u', 'i'],
    '9': ['8', '0', 'i', 'o'], '0': ['9', 'o', 'p'],
    'q': ['1', '2', 'w', 'a'], 'w': ['2', '3', 'q', 'e', 'a', 's'],
    'e': ['3', '4', 'w', 'r', 's', 'd'], 'r': ['4', '5', 'e', 't', 'd', 'f'],
    't': ['5', '6', 'r', 'y', 'f', 'g'], 'y': ['6', '7', 't', 'u', 'g', 'h'],
    'u': ['7', '8', 'y', 'i', 'h', 'j'], 'i': ['8', '9', 'u', 'o', 'j', 'k'],
    'o': ['9', '0', 'i', 'p', 'k', 'l'], 'p': ['0', 'o', 'l'],
    'a': ['q', 'w', 's', 'z'], 's': ['w', 'e', 'a', 'd', 'z', 'x'],
    'd': ['e', 'r', 's', 'f', 'x', 'c'], 'f': ['r', 't', 'd', 'g', 'c', 'v'],
    'g': ['t', 'y', 'f', 'h', 'v', 'b'], 'h': ['y', 'u', 'g', 'j', 'b', 'n'],
    'j': ['u', 'i', 'h', 'k', 'n', 'm'], 'k': ['i', 'o', 'j', 'l', 'm'],
    'l': ['o', 'p', 'k'],
    'z': ['a', 's', 'x'], 'x': ['s', 'd', 'z', 'c'],
    'c': ['d', 'f', 'x', 'v'], 'v': ['f', 'g', 'c', 'b'],
    'b': ['g', 'h', 'v', 'n'], 'n': ['h', 'j', 'b', 'm'],
    'm': ['j', 'k', 'n'],
}


def shannon_bits(pw: str) -> float:
    if not pw:
        return 0.0
    freq = Counter(pw)
    total = len(pw)
    return -sum((c / total) * math.log2(c / total) for c in freq.values())


def walk_ratio(pw: str) -> float:
    s = pw.lower()
    if len(s) < 2:
        return 0.0
    adjacent = sum(
        1 for i in range(len(s) - 1)
        if s[i] in QWERTY_ADJ and s[i + 1] in QWERTY_ADJ.get(s[i], [])
    )
    return adjacent / (len(s) - 1)


def _char_class(c: str) -> str:
    if c.isdigit():
        return "digit"
    if c.isupper():
        return "upper"
    if c.islower():
        return "lower"
    return "symbol"


def passes_all(pw: str, rules: RuleSet) -> bool:
    # Length
    if not (rules.min_length <= len(pw) <= rules.max_length):
        return False

    # Must-start / must-end class
    if rules.must_start_with_class and pw:
        if _char_class(pw[0]) != rules.must_start_with_class:
            return False
    if rules.must_end_with_class and pw:
        if _char_class(pw[-1]) != rules.must_end_with_class:
            return False

    # Must-not-start / must-not-end
    if rules.must_not_start_with and pw:
        if pw[0] in rules.must_not_start_with:
            return False
    if rules.must_not_end_with and pw:
        if pw[-1] in rules.must_not_end_with:
            return False

    # Startswith / endswith / contains
    if rules.startswith and not any(pw.startswith(s) for s in rules.startswith):
        return False
    if rules.endswith and not any(pw.endswith(s) for s in rules.endswith):
        return False
    if rules.contains:
        if not all(s in pw for s in rules.contains):
            return False

    # Consecutive chars
    for rule in rules.no_consecutive:
        char = rule.get("char", "any")
        count = rule.get("count", 3)
        if char == "any":
            if re.search(r'(.)\1{' + str(count - 1) + r',}', pw):
                return False
        else:
            if char * count in pw:
                return False

    # Max repeats
    if rules.max_repeats:
        counts = Counter(pw)
        digit_limit = rules.max_repeats.get("digits")
        letter_limit = rules.max_repeats.get("letters")
        any_limit = rules.max_repeats.get("any_char")
        if digit_limit is not None:
            if any(counts[d] > digit_limit for d in "0123456789" if d in counts):
                return False
        if letter_limit is not None:
            alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
            if any(counts[c] > letter_limit for c in alphabet if c in counts):
                return False
        if any_limit is not None:
            if any(v > any_limit for v in counts.values()):
                return False

    # Require character classes
    if rules.require_classes:
        for cls in rules.require_classes:
            if cls == "digit" and not any(c.isdigit() for c in pw):
                return False
            if cls == "upper" and not any(c.isupper() for c in pw):
                return False
            if cls == "lower" and not any(c.islower() for c in pw):
                return False
            if cls == "symbol" and not any(not c.isalnum() for c in pw):
                return False

    # Entropy
    if rules.entropy_min_bits is not None:
        if shannon_bits(pw) < rules.entropy_min_bits:
            return False

    # Regex blacklist
    for pattern in rules.regex_blacklist:
        if re.search(pattern, pw):
            return False

    # Regex whitelist (all must match)
    for pattern in rules.regex_whitelist:
        if not re.search(pattern, pw):
            return False

    # Keyboard walk
    if rules.keyboard_walk_threshold is not None:
        if walk_ratio(pw) > rules.keyboard_walk_threshold:
            return False

    return True
