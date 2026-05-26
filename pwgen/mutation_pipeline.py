"""Composable mutation functions — each is a pure str→str transform."""
from __future__ import annotations
import random
import string
from typing import Generator

LEET_MAP = {'a': '@', 'e': '3', 'i': '1', 'l': '1', 'o': '0', 's': '$', 't': '7'}
LEET_FULL_MAP = {**LEET_MAP, 'b': '8', 'g': '9', 'q': '9', 'z': '2', 'h': '#'}

_YEARS = [str(y) for y in range(1990, 2027)]
_SYMBOLS = list("!@#$%^&*")


def _leet(pw: str) -> str:
    return "".join(LEET_MAP.get(c.lower(), c) for c in pw)


def _full_leet(pw: str) -> str:
    return "".join(LEET_FULL_MAP.get(c.lower(), c) for c in pw)


def _insert_at_pos(pw: str, char: str, pos: int) -> str:
    return pw[:pos] + char + pw[pos:]


MUTATIONS: dict[str, object] = {
    "capitalize":    lambda p: p.capitalize(),
    "upper":         lambda p: p.upper(),
    "lower":         lambda p: p.lower(),
    "reverse":       lambda p: p[::-1],
    "toggle_case":   lambda p: p.swapcase(),
    "double":        lambda p: p + p,
    "prefix_bang":   lambda p: "!" + p,
    "suffix_123":    lambda p: p + "123",
    "leet_swap":     _leet,
    "l33t_full":     _full_leet,
    "append_symbol": lambda p: p + random.choice(_SYMBOLS),
    "append_year":   lambda p: p + random.choice(_YEARS),
    "insert_digit":  lambda p: _insert_at_pos(p, random.choice(string.digits), random.randint(0, len(p))),
}

_STANDARD = [
    "capitalize", "append_year", "append_symbol",
    "leet_swap", "reverse", "insert_digit", "toggle_case",
]
_AGGRESSIVE = list(MUTATIONS.keys())

PROFILES: dict[str, list[str]] = {
    "none": [],
    "standard": _STANDARD,
    "aggressive": _AGGRESSIVE,
}


def apply_mutations(
    base: str,
    enabled: list[str],
    max_expansion: int,
) -> Generator[str, None, None]:
    yield base
    count = 0
    for name in enabled:
        if count >= max_expansion:
            break
        fn = MUTATIONS.get(name)
        if fn is None:
            continue
        result = fn(base)  # type: ignore[operator]
        if result != base:
            yield result
            count += 1
