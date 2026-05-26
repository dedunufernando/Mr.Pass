"""Compile a raw constraint dict into a validated, typed RuleSet."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any

CHARSETS = {
    "digits":  "0123456789",
    "alpha":   "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "lower":   "abcdefghijklmnopqrstuvwxyz",
    "upper":   "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "alnum":   "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    "ascii":   "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+-=[]{}|;':\",./<>?",
    "binary":  "01",
}


class RuleConflictError(Exception):
    pass


@dataclass
class RuleSet:
    # Length
    length: int | None = None
    min_length: int = 1
    max_length: int = 16

    # Charset
    charset: str = CHARSETS["digits"]
    require_classes: list[str] = field(default_factory=list)

    # Consecutive / repeats
    no_consecutive: list[dict] = field(default_factory=list)
    max_repeats: dict[str, int] = field(default_factory=dict)

    # Position rules
    must_not_start_with: list[str] = field(default_factory=list)
    must_not_end_with: list[str] = field(default_factory=list)
    must_start_with_class: str | None = None
    must_end_with_class: str | None = None

    # Pattern rules
    startswith: list[str] = field(default_factory=list)
    endswith: list[str] = field(default_factory=list)
    contains: list[str] = field(default_factory=list)
    regex_whitelist: list[str] = field(default_factory=list)
    regex_blacklist: list[str] = field(default_factory=list)

    # Keyboard walk
    keyboard_walk_threshold: float | None = None

    # Entropy
    entropy_min_bits: float | None = None

    # Output
    output_format: str = "txt"
    output_path: str = "wordlist.txt"
    compress: bool = False
    sort_by: str = "entropy"
    max_candidates: int | None = None
    include_header: bool = True

    # Mutations
    mutations_profile: str = "none"
    mutations_enabled: list[str] = field(default_factory=list)
    max_expansion: int = 50

    # Wordlist
    wordlist_tier: str = "none"
    wordlist_custom_path: str | None = None


def compile_rules(cfg: dict[str, Any]) -> RuleSet:
    rs = RuleSet()

    # Resolve charset
    charset_name = cfg.get("charset", "digits")
    charset_opts = cfg.get("charset_options", {})
    if charset_opts.get("include"):
        rs.charset = charset_opts["include"]
    elif charset_name == "custom":
        rs.charset = cfg.get("custom_chars", "0123456789")
    else:
        rs.charset = CHARSETS.get(charset_name, CHARSETS["digits"])

    if charset_opts.get("exclude"):
        excluded = set(charset_opts["exclude"])
        rs.charset = "".join(c for c in rs.charset if c not in excluded)

    rs.charset = "".join(dict.fromkeys(rs.charset))  # deduplicate, preserve order

    if not rs.charset:
        raise RuleConflictError("Charset is empty after exclusions.")

    rs.require_classes = charset_opts.get("require_classes", [])

    # Length
    if "length" in cfg:
        rs.length = int(cfg["length"])
        rs.min_length = rs.length
        rs.max_length = rs.length
    else:
        rs.min_length = int(cfg.get("min_length", 1))
        rs.max_length = int(cfg.get("max_length", 16))

    if rs.min_length > rs.max_length:
        raise RuleConflictError(
            f"min_length ({rs.min_length}) > max_length ({rs.max_length})"
        )

    # Consecutive / repeats
    rs.no_consecutive = cfg.get("no_consecutive", [])
    rs.max_repeats = cfg.get("max_repeats", {})
    if isinstance(rs.max_repeats, dict):
        rs.max_repeats = {k: v for k, v in rs.max_repeats.items() if v is not None}

    # Position rules
    pos = cfg.get("position_rules", {})
    rs.must_not_start_with = pos.get("must_not_start_with", [])
    rs.must_not_end_with = pos.get("must_not_end_with", [])
    rs.must_start_with_class = pos.get("must_start_with_class")
    rs.must_end_with_class = pos.get("must_end_with_class")

    # Patterns
    patterns = cfg.get("patterns", {})
    rs.startswith = patterns.get("startswith", [])
    rs.endswith = patterns.get("endswith", [])
    rs.contains = patterns.get("contains", [])
    rs.regex_whitelist = patterns.get("regex_whitelist", [])
    rs.regex_blacklist = patterns.get("regex_blacklist", [])

    # Compile regexes early to catch syntax errors
    for pat in rs.regex_whitelist + rs.regex_blacklist:
        try:
            re.compile(pat)
        except re.error as exc:
            raise RuleConflictError(f"Invalid regex {pat!r}: {exc}") from exc

    # Keyboard walk
    kw = cfg.get("keyboard_walk", {})
    rs.keyboard_walk_threshold = kw.get("reject_if_walk_ratio_above")

    # Entropy
    ent = cfg.get("entropy", {})
    rs.entropy_min_bits = ent.get("min_bits")

    # Output
    out = cfg.get("output", {})
    rs.output_format = out.get("format", "txt")
    rs.output_path = out.get("path", "wordlist.txt")
    rs.compress = bool(out.get("compress", False))
    rs.sort_by = out.get("sort_by", "entropy")
    rs.max_candidates = out.get("max_candidates")
    rs.include_header = bool(out.get("include_header", True))

    # Mutations
    mut = cfg.get("mutations", {})
    rs.mutations_profile = mut.get("profile", "none")
    rs.mutations_enabled = mut.get("enabled", [])
    rs.max_expansion = int(mut.get("max_expansion", 50))

    # Wordlist
    wl = cfg.get("wordlist", {})
    rs.wordlist_tier = wl.get("tier", "none")
    rs.wordlist_custom_path = wl.get("custom_path")

    _validate(rs)
    return rs


def _char_class(c: str) -> str:
    if c.isdigit():
        return "digit"
    if c.isupper():
        return "upper"
    if c.islower():
        return "lower"
    return "symbol"


def _validate(rs: RuleSet) -> None:
    # Check must_not_start_with chars are actually in charset (warn only)
    # Check length feasibility vs startswith/endswith
    for sw in rs.startswith:
        if rs.length is not None and len(sw) > rs.length:
            raise RuleConflictError(
                f"startswith pattern {sw!r} longer than fixed length {rs.length}"
            )
    for ew in rs.endswith:
        if rs.length is not None and len(ew) > rs.length:
            raise RuleConflictError(
                f"endswith pattern {ew!r} longer than fixed length {rs.length}"
            )
