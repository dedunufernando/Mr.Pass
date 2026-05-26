"""Critical: 100% of generated candidates must satisfy all rules."""
import pytest
from pwgen.rule_compiler import compile_rules
from pwgen.generator import generate
from pwgen.filter import passes_all


def _collect(cfg: dict) -> list[str]:
    rules = compile_rules(cfg)
    return list(generate(rules))


def _assert_all_valid(cfg: dict):
    rules = compile_rules(cfg)
    for candidate in generate(rules):
        assert passes_all(candidate, rules), f"Violation: {candidate!r}"


def test_length_4_digits():
    results = _collect({"charset": "binary", "length": 4})
    assert len(results) == 2**4  # 16


def test_all_satisfy_no_consecutive():
    _assert_all_valid({
        "charset": "binary",
        "length": 4,
        "no_consecutive": [{"char": "any", "count": 3}],
    })


def test_no_consecutive_zero():
    rules = compile_rules({
        "charset": "digits",
        "length": 4,
        "no_consecutive": [{"char": "0", "count": 3}],
    })
    for cand in generate(rules):
        assert "000" not in cand


def test_max_repeats_digits():
    rules = compile_rules({
        "charset": "digits",
        "charset_options": {"include": "012"},
        "length": 4,
        "max_repeats": {"digits": 2},
    })
    from collections import Counter
    for cand in generate(rules):
        counts = Counter(cand)
        assert all(v <= 2 for v in counts.values()), f"Repeat violation: {cand}"


def test_must_not_start_with():
    rules = compile_rules({
        "charset": "binary",
        "length": 3,
        "position_rules": {"must_not_start_with": ["0"]},
    })
    for cand in generate(rules):
        assert not cand.startswith("0"), f"Start violation: {cand}"


def test_min_max_length():
    rules = compile_rules({
        "charset": "binary",
        "min_length": 2,
        "max_length": 3,
    })
    results = list(generate(rules))
    assert all(2 <= len(c) <= 3 for c in results)
    assert len(results) == 2**2 + 2**3  # 4 + 8 = 12


def test_empty_when_impossible():
    rules = compile_rules({
        "charset_options": {"include": "0"},
        "length": 4,
        "no_consecutive": [{"char": "0", "count": 2}],
    })
    results = list(generate(rules))
    assert results == [], f"Expected empty but got: {results}"


def test_correctness_comprehensive():
    _assert_all_valid({
        "charset": "digits",
        "charset_options": {"include": "0123"},
        "length": 5,
        "no_consecutive": [{"char": "any", "count": 3}],
        "max_repeats": {"digits": 2},
    })
