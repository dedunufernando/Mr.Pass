"""Backtracking generator with early pruning.

Fast path: if a RuleSet has no prefix-prunable constraints, uses
itertools.product (implemented in C, ~20x faster than Python backtracking).
Slow path: full recursive backtracking with early pruning for constrained runs.

For wordlist-based generation, see seed_loader.py + mutation_pipeline.py.
"""
from __future__ import annotations
import itertools
import re
from collections import Counter
from typing import Generator

from .rule_compiler import RuleSet
from .filter import walk_ratio, _char_class, passes_all

_DIGITS = set("0123456789")
_UPPER = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_LOWER = set("abcdefghijklmnopqrstuvwxyz")


def _violates_prefix(prefix: list[str], rules: RuleSet) -> bool:
    """Return True if the current prefix already breaks a prunable rule."""
    n = len(prefix)
    if n == 0:
        return False

    # must_not_start_with
    if n == 1 and rules.must_not_start_with:
        if prefix[0] in rules.must_not_start_with:
            return True

    # must_start_with_class
    if n == 1 and rules.must_start_with_class:
        if _char_class(prefix[0]) != rules.must_start_with_class:
            return True

    # no_consecutive — check only the tail of the prefix
    for rule in rules.no_consecutive:
        char = rule.get("char", "any")
        count = rule.get("count", 3)
        if char == "any":
            # count trailing same chars
            tail = prefix[-1]
            run = 1
            for c in reversed(prefix[:-1]):
                if c == tail:
                    run += 1
                else:
                    break
            if run >= count:
                return True
        else:
            # count trailing occurrences of `char`
            if prefix[-1] == char:
                run = sum(1 for _ in (c for c in reversed(prefix) if c == prefix[-1]))
                # This is simpler: just check suffix
                suffix = "".join(prefix[-(count):])
                if suffix == char * count:
                    return True

    # max_repeats — track Counter incrementally
    if rules.max_repeats:
        counts = Counter(prefix)
        digit_limit = rules.max_repeats.get("digits")
        letter_limit = rules.max_repeats.get("letters")
        any_limit = rules.max_repeats.get("any_char")
        last = prefix[-1]
        if digit_limit is not None and last in _DIGITS:
            if counts[last] > digit_limit:
                return True
        if letter_limit is not None and (last in _UPPER or last in _LOWER):
            if counts[last] > letter_limit:
                return True
        if any_limit is not None:
            if counts[last] > any_limit:
                return True

    # keyboard_walk — check prefix walk ratio; prune if already too high
    if rules.keyboard_walk_threshold is not None and n >= 3:
        if walk_ratio("".join(prefix)) > rules.keyboard_walk_threshold:
            return True

    return False


def _final_check(pw: str, rules: RuleSet) -> bool:
    """Checks that can only be evaluated on the complete string."""
    return passes_all(pw, rules)


def _needs_backtracking(rules: RuleSet) -> bool:
    """Return True if any prefix-prunable rule is active (requires slow path)."""
    if rules.no_consecutive:
        return True
    if rules.max_repeats:
        return True
    if rules.must_not_start_with:
        return True
    if rules.must_start_with_class:
        return True
    if rules.keyboard_walk_threshold is not None:
        return True
    return False


def _generate_fast(rules: RuleSet) -> Generator[str, None, None]:
    """
    Fast path using itertools.product (C-speed).
    Applies full constraint check on each complete candidate.
    Only used when no prefix-prunable rules are active.
    """
    charset = rules.charset
    lengths = (
        [rules.length]
        if rules.length is not None
        else list(range(rules.min_length, rules.max_length + 1))
    )
    has_postgen_rules = bool(
        rules.regex_blacklist or rules.regex_whitelist
        or rules.entropy_min_bits
        or rules.startswith or rules.endswith or rules.contains
        or rules.must_end_with_class or rules.must_not_end_with
        or rules.require_classes
    )
    for length in lengths:
        for combo in itertools.product(charset, repeat=length):
            pw = "".join(combo)
            if has_postgen_rules:
                if not _final_check(pw, rules):
                    continue
            yield pw


def generate(rules: RuleSet) -> Generator[str, None, None]:
    """Yield all candidates that satisfy rules.

    Automatically picks the fast (itertools.product) or slow (backtracking)
    path based on which constraints are active.
    """
    if _needs_backtracking(rules):
        lengths = (
            [rules.length]
            if rules.length is not None
            else list(range(rules.min_length, rules.max_length + 1))
        )
        for target_len in lengths:
            yield from _backtrack([], target_len, rules.charset, rules)
    else:
        yield from _generate_fast(rules)


def _backtrack(
    prefix: list[str],
    target_len: int,
    charset: str,
    rules: RuleSet,
) -> Generator[str, None, None]:
    if _violates_prefix(prefix, rules):
        return

    if len(prefix) == target_len:
        pw = "".join(prefix)
        if _final_check(pw, rules):
            yield pw
        return

    for char in charset:
        prefix.append(char)
        yield from _backtrack(prefix, target_len, charset, rules)
        prefix.pop()
