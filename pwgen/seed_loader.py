"""Load base wordlists by tier."""
from __future__ import annotations
from pathlib import Path
from typing import Generator

from .rule_compiler import RuleSet

_HERE = Path(__file__).parent.parent / "wordlists"

TIER_FILES = {
    "tiny":  _HERE / "tiny_1k.txt",
    "small": _HERE / "small_10k.txt",
}


def load_wordlist(rules: RuleSet) -> Generator[str, None, None]:
    path: Path | None = None
    if rules.wordlist_custom_path:
        path = Path(rules.wordlist_custom_path)
    elif rules.wordlist_tier in TIER_FILES:
        path = TIER_FILES[rules.wordlist_tier]

    if path is None or not path.exists():
        return

    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            word = line.rstrip("\n\r")
            if word and not word.startswith("#"):
                yield word
