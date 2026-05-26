"""
Week 3 milestone: 100% of generated candidates satisfy ALL constraints.

Tests a full combinatorial run over a small charset+length so every
candidate can be exhaustively verified.
"""
import pytest
from pwgen.rule_compiler import compile_rules
from pwgen.generator import generate
from pwgen.filter import passes_all
from pwgen.pipeline import run_pipeline
from pwgen.jit import try_build_jit_filter, is_numba_available
import tempfile, os


# ── Core correctness guarantee ──────────────────────────────────────────────

CONFIGS = [
    # (description, cfg)
    ("digits-4-no-constraint",
     {"charset": "binary", "length": 4}),
    ("digits-5-no-consec-any-3",
     {"charset_options": {"include": "012"}, "length": 5,
      "no_consecutive": [{"char": "any", "count": 3}]}),
    ("digits-4-max-repeat-2",
     {"charset_options": {"include": "0123"}, "length": 4,
      "max_repeats": {"digits": 2}}),
    ("digits-6-combined",
     {"charset_options": {"include": "01234"}, "length": 6,
      "no_consecutive": [{"char": "0", "count": 3}],
      "max_repeats": {"digits": 2}}),
    ("binary-5-entropy",
     {"charset": "binary", "length": 5,
      "entropy": {"min_bits": 0.5}}),
    ("binary-4-must-not-start-0",
     {"charset": "binary", "length": 4,
      "position_rules": {"must_not_start_with": ["0"]}}),
    ("digits-4-regex-blacklist",
     {"charset_options": {"include": "012"}, "length": 4,
      "patterns": {"regex_blacklist": ["^00"]}}),
    ("alnum-3-require-upper",
     {"charset_options": {"include": "abcABC123"}, "length": 3,
      "charset_options": {"include": "abcABC123",
                          "require_classes": ["upper"]}}),
]


@pytest.mark.parametrize("desc,cfg", CONFIGS, ids=[c[0] for c in CONFIGS])
def test_all_candidates_satisfy_constraints(desc, cfg):
    """100% of generated candidates must pass passes_all()."""
    rules = compile_rules(cfg)
    violations = []
    for candidate in generate(rules):
        if not passes_all(candidate, rules):
            violations.append(candidate)
    assert violations == [], (
        f"[{desc}] {len(violations)} violations: {violations[:5]}"
    )


# ── Fast-path vs slow-path agree ─────────────────────────────────────────────

def test_fast_and_slow_path_same_output():
    """itertools.product fast path and backtracking slow path must produce identical sets."""
    from pwgen.generator import _generate_fast, _backtrack, _needs_backtracking

    # Config with no prunable rules → fast path
    cfg_fast = {"charset_options": {"include": "01"}, "length": 5}
    rules_fast = compile_rules(cfg_fast)
    assert not _needs_backtracking(rules_fast)
    fast = set(_generate_fast(rules_fast))
    slow = set(_backtrack([], 5, rules_fast.charset, rules_fast))
    assert fast == slow, f"Mismatch: {len(fast)} fast vs {len(slow)} slow"


def test_fast_path_with_post_gen_rules():
    """Fast path still applies regex/entropy rules correctly."""
    cfg = {
        "charset_options": {"include": "01"},
        "length": 4,
        "patterns": {"regex_blacklist": ["^00"]},
    }
    rules = compile_rules(cfg)
    for cand in generate(rules):
        assert not cand.startswith("00"), f"Blacklist violated: {cand}"


# ── Pipeline correctness ──────────────────────────────────────────────────────

def test_pipeline_output_satisfies_constraints():
    """All candidates written by the pipeline must satisfy rules."""
    cfg = {
        "charset_options": {"include": "0123"},
        "length": 5,
        "no_consecutive": [{"char": "any", "count": 3}],
        "max_repeats": {"digits": 2},
        "output": {"format": "txt", "path": "tmp", "include_header": False},
    }
    rules = compile_rules(cfg)
    source = generate(rules)

    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "out.txt")
        result = run_pipeline(
            source, rules,
            output_path=out,
            include_header=False,
            show_progress=False,
        )
        with open(out) as f:
            written = [l.strip() for l in f if l.strip()]

    assert result["total"] == len(written), "Count mismatch between stats and file"
    violations = [pw for pw in written if not passes_all(pw, rules)]
    assert violations == [], f"{len(violations)} pipeline violations: {violations[:5]}"


# ── Deduplication correctness ─────────────────────────────────────────────────

def test_pipeline_no_duplicate_output():
    """Pipeline output must contain no duplicate lines."""
    cfg = {
        "charset": "binary",
        "length": 5,
        "output": {"format": "txt", "path": "tmp", "include_header": False},
    }
    rules = compile_rules(cfg)

    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "out.txt")
        run_pipeline(
            generate(rules), rules,
            output_path=out,
            include_header=False,
            show_progress=False,
        )
        with open(out) as f:
            lines = [l.strip() for l in f if l.strip()]

    assert len(lines) == len(set(lines)), (
        f"Duplicates found: {len(lines)} lines, {len(set(lines))} unique"
    )


# ── JIT module ───────────────────────────────────────────────────────────────

def test_jit_filter_agrees_with_python():
    """JIT filter (or its Python fallback) must agree with passes_all."""
    cfg = {
        "charset": "digits",
        "charset_options": {"include": "0123456789"},
        "length": 6,
        "no_consecutive": [{"char": "0", "count": 3}],
        "max_repeats": {"digits": 2},
    }
    rules = compile_rules(cfg)
    jit_filter = try_build_jit_filter(rules)
    assert jit_filter is not None

    test_cases = ["012345", "000123", "111000", "123456", "000000", "112233"]
    for pw in test_cases:
        jit_result  = jit_filter(pw)
        full_result = passes_all(pw, rules)
        assert jit_result == full_result, (
            f"JIT/Python mismatch on {pw!r}: jit={jit_result} py={full_result}"
        )
