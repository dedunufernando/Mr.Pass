"""
Week 4 milestone: full end-to-end test — wordlist + aggressive mutations,
all export formats, viz, breach-check module, hc22000.
"""
from __future__ import annotations
import gzip
import json
import os
import tempfile

import pytest

from pwgen.rule_compiler import compile_rules
from pwgen.generator import generate
from pwgen.filter import passes_all
from pwgen.pipeline import run_pipeline
from pwgen.io import write_candidates
from pwgen.scorer import classify, shannon_bits, sort_by_entropy
from pwgen.breach_check import _sha1, LocalHIBP, annotate_breached
from pwgen.mutation_pipeline import apply_mutations, PROFILES


# ---------------------------------------------------------------------------
# Export formats
# ---------------------------------------------------------------------------

def _base_candidates() -> list[str]:
    rules = compile_rules({
        "charset_options": {"include": "abcABC123!"},
        "min_length": 4,
        "max_length": 6,
        "output": {"format": "txt", "path": "x"},
    })
    return list(generate(rules))[:200]


def test_txt_format_round_trip():
    candidates = ["hello", "world", "pass123"]
    rules = compile_rules({})
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "out.txt")
        write_candidates(candidates, rules, path=p, fmt="txt", include_header=False)
        lines = [l.strip() for l in open(p) if l.strip()]
    assert lines == candidates


def test_csv_format_has_columns():
    candidates = ["abc", "123", "qwerty"]
    rules = compile_rules({})
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "out.csv")
        write_candidates(candidates, rules, path=p, fmt="csv", include_header=False)
        content = open(p).read()
    assert "candidate,entropy_bits,pattern_class" in content
    for pw in candidates:
        assert pw in content


def test_json_format_structure():
    candidates = ["abc", "ABC", "123"]
    rules = compile_rules({})
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "out.json")
        write_candidates(candidates, rules, path=p, fmt="json", include_header=True)
        payload = json.loads(open(p).read())
    assert "candidates" in payload
    assert "warning" in payload
    pws = [c["pw"] for c in payload["candidates"]]
    for pw in candidates:
        assert pw in pws


def test_hc22000_format():
    candidates = ["password", "admin123", "letmein"]
    rules = compile_rules({})
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "out.hc22000")
        write_candidates(candidates, rules, path=p, fmt="hc22000", include_header=True)
        content = open(p).read()
    assert "hc22000" in content
    for pw in candidates:
        assert pw in content


def test_gzip_format():
    candidates = ["abc", "def"]
    rules = compile_rules({})
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "out.txt.gz")
        write_candidates(candidates, rules, path=p, fmt="txt",
                         compress=True, include_header=False)
        with gzip.open(p, "rt") as f:
            content = f.read()
    for pw in candidates:
        assert pw in content


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

def test_classify_numeric():
    assert classify("1234567") == "numeric"


def test_classify_alpha():
    assert classify("abcdefg") == "alpha"


def test_classify_keyboard_walk():
    assert classify("qwertyu") == "keyboard_walk"


def test_classify_date_suffix():
    assert classify("pass2024") == "date_suffix"


def test_classify_symbol_mutant():
    assert classify("p@ss!") == "symbol_mutant"


def test_sort_by_entropy():
    words = ["aaaa", "abcd", "a1B!"]
    sorted_words = sort_by_entropy(words)
    # Highest entropy first
    entropies = [shannon_bits(w) for w in sorted_words]
    assert entropies == sorted(entropies, reverse=True)


# ---------------------------------------------------------------------------
# Breach check (offline only — no real API calls in tests)
# ---------------------------------------------------------------------------

def test_sha1_hash():
    # SHA-1 of "password" is 5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8
    assert _sha1("password") == "5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8"


def test_local_hibp_lookup():
    """Create a tiny fake HIBP file and verify lookup works."""
    h = _sha1("password123")
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "hibp.txt")
        # HIBP files are sorted hash:count lines
        lines = sorted([
            f"{h}:12345",
            f"{_sha1('notbreached')}:0",
            f"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:1",
        ])
        with open(db_path, "w") as f:
            f.write("\n".join(lines) + "\n")

        db = LocalHIBP(db_path)
        assert db.is_breached("password123"), "password123 should be flagged as breached"
        assert not db.is_breached("uniquepassword_xyz_notindb"), "unique pw should not be breached"


def test_annotate_breached_skips_api():
    """annotate_breached with no api and no local path returns not-breached for all."""
    candidates = ["abc", "def"]
    results = annotate_breached(candidates, use_api=False, local_path=None)
    assert len(results) == 2
    for r in results:
        assert r["breached"] is False


# ---------------------------------------------------------------------------
# Wordlist + aggressive mutations end-to-end
# ---------------------------------------------------------------------------

def test_wordlist_aggressive_mutations_pipeline():
    """
    Week 4 milestone: run tiny wordlist through aggressive mutations,
    verify all output satisfies rules, all formats write correctly.
    """
    from pwgen.seed_loader import load_wordlist

    cfg = {
        "wordlist": {"tier": "tiny"},
        "mutations": {"profile": "aggressive", "max_expansion": 8},
        "min_length": 4,
        "max_length": 20,
        "output": {"format": "txt", "path": "x", "include_header": True, "sort_by": "none"},
    }
    rules = compile_rules(cfg)

    enabled = PROFILES["aggressive"]

    def source():
        for base in load_wordlist(rules):
            yield from apply_mutations(base, enabled, 8)

    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "w4_milestone.txt")
        result = run_pipeline(
            source(), rules,
            output_path=out,
            include_header=True,
            show_progress=False,
        )

        with open(out, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    assert result["total"] > 0, "Should generate at least some candidates"
    assert result["total"] == len(lines), "Stat count must match file line count"
    violations = [pw for pw in lines if not passes_all(pw, rules)]
    assert violations == [], f"{len(violations)} constraint violations found"


# ---------------------------------------------------------------------------
# Viz (only runs if matplotlib available)
# ---------------------------------------------------------------------------

def test_viz_entropy_histogram():
    pytest.importorskip("matplotlib")
    from pwgen.viz import plot_entropy_histogram
    candidates = [f"pw{i:04d}" for i in range(200)]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "entropy.png")
        result = plot_entropy_histogram(candidates, p)
        assert os.path.exists(result)
        assert os.path.getsize(result) > 1000  # non-empty PNG


def test_viz_pattern_distribution():
    pytest.importorskip("matplotlib")
    from pwgen.viz import plot_pattern_distribution
    candidates = ["1234567", "abcdefg", "qwerty1", "p@ssword", "abc2024"]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "patterns.png")
        result = plot_pattern_distribution(candidates, p)
        assert os.path.exists(result)


def test_viz_keyboard_heatmap():
    pytest.importorskip("matplotlib")
    from pwgen.viz import plot_keyboard_heatmap
    candidates = ["qwerty", "asdfgh", "password", "12345678"]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "keyboard.png")
        result = plot_keyboard_heatmap(candidates, p)
        assert os.path.exists(result)


def test_viz_all():
    pytest.importorskip("matplotlib")
    from pwgen.viz import plot_all
    candidates = ["password", "1234567", "qwerty", "abc!123", "P@ssw0rd"]
    with tempfile.TemporaryDirectory() as d:
        paths = plot_all(candidates, d, entropy_threshold=30.0)
        assert "entropy"  in paths
        assert "keyboard" in paths
        assert "patterns" in paths
        for p in paths.values():
            assert os.path.exists(p)
