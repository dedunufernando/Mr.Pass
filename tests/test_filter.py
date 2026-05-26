from pwgen.rule_compiler import compile_rules
from pwgen.filter import passes_all, shannon_bits, walk_ratio


def rs(cfg):
    return compile_rules(cfg)


def test_length_pass():
    assert passes_all("1234567", rs({"length": 7}))


def test_length_fail():
    assert not passes_all("123456", rs({"length": 7}))


def test_no_consecutive_pass():
    assert passes_all("1230123", rs({"no_consecutive": [{"char": "0", "count": 3}]}))


def test_no_consecutive_fail():
    assert not passes_all("1000123", rs({"no_consecutive": [{"char": "0", "count": 3}]}))


def test_max_repeats_pass():
    assert passes_all("12345", rs({"max_repeats": {"digits": 2}}))


def test_max_repeats_fail():
    assert not passes_all("11145", rs({"max_repeats": {"digits": 2}}))


def test_entropy_pass():
    assert passes_all("aB3!xY9", rs({"entropy": {"min_bits": 2}}))


def test_entropy_fail():
    assert not passes_all("0000000", rs({"entropy": {"min_bits": 2}}))


def test_regex_blacklist_fail():
    assert not passes_all("000abc", rs({"patterns": {"regex_blacklist": ["^000"]}}))


def test_regex_blacklist_pass():
    assert passes_all("abc000", rs({"patterns": {"regex_blacklist": ["^000"]}}))


def test_must_not_start():
    assert not passes_all("0abc", rs({"position_rules": {"must_not_start_with": ["0"]}}))
    assert passes_all("abc0", rs({"position_rules": {"must_not_start_with": ["0"]}}))


def test_must_end_with_class():
    assert passes_all("abc1", rs({"position_rules": {"must_end_with_class": "digit"}}))
    assert not passes_all("abc!", rs({"position_rules": {"must_end_with_class": "digit"}}))


def test_keyboard_walk_reject():
    # "qwerty" is a strong keyboard walk
    r = rs({"keyboard_walk": {"reject_if_walk_ratio_above": 0.4}})
    assert not passes_all("qwerty", r)


def test_require_upper():
    r = rs({"charset_options": {"require_classes": ["upper"]}})
    assert not passes_all("abc123", r)
    assert passes_all("Abc123", r)


def test_shannon_bits_all_same():
    assert shannon_bits("0000") == 0.0


def test_shannon_bits_varied():
    assert shannon_bits("01234567") > 2.0


def test_walk_ratio_qwerty():
    assert walk_ratio("qwerty") > 0.5


def test_walk_ratio_random():
    assert walk_ratio("x7mZ!2") < 0.3
