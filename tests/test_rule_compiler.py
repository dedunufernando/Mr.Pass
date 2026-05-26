import pytest
from pwgen.rule_compiler import compile_rules, RuleConflictError, CHARSETS


def test_default_digits():
    rs = compile_rules({})
    assert rs.charset == CHARSETS["digits"]


def test_explicit_length():
    rs = compile_rules({"length": 7})
    assert rs.length == 7
    assert rs.min_length == 7
    assert rs.max_length == 7


def test_min_max_length():
    rs = compile_rules({"min_length": 4, "max_length": 8})
    assert rs.min_length == 4
    assert rs.max_length == 8


def test_conflict_min_gt_max():
    with pytest.raises(RuleConflictError):
        compile_rules({"min_length": 10, "max_length": 5})


def test_charset_alpha():
    rs = compile_rules({"charset": "alpha"})
    assert "a" in rs.charset
    assert "Z" in rs.charset
    assert "0" not in rs.charset


def test_charset_binary():
    rs = compile_rules({"charset": "binary"})
    assert set(rs.charset) == {"0", "1"}


def test_charset_custom():
    rs = compile_rules({"charset": "custom", "custom_chars": "abc123"})
    assert rs.charset == "abc123"


def test_charset_exclude():
    rs = compile_rules({"charset": "digits", "charset_options": {"exclude": "0"}})
    assert "0" not in rs.charset


def test_empty_charset_after_exclude():
    with pytest.raises(RuleConflictError):
        compile_rules({"charset": "binary", "charset_options": {"exclude": "01"}})


def test_startswith_too_long():
    with pytest.raises(RuleConflictError):
        compile_rules({"length": 3, "patterns": {"startswith": ["password"]}})


def test_no_consecutive_parsed():
    rs = compile_rules({"no_consecutive": [{"char": "0", "count": 3}]})
    assert rs.no_consecutive == [{"char": "0", "count": 3}]


def test_max_repeats_parsed():
    rs = compile_rules({"max_repeats": {"digits": 2}})
    assert rs.max_repeats["digits"] == 2


def test_entropy_parsed():
    rs = compile_rules({"entropy": {"min_bits": 30}})
    assert rs.entropy_min_bits == 30.0


def test_invalid_regex():
    with pytest.raises(RuleConflictError):
        compile_rules({"patterns": {"regex_blacklist": ["[invalid"]}})
