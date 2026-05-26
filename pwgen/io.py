"""Streaming output writer — batched disk flushes, optional gzip."""
from __future__ import annotations
import gzip
import json
import os
from datetime import datetime, timezone
from typing import Generator

from .filter import shannon_bits
from .rule_compiler import RuleSet

_BATCH = 10_000
_WARNING = "# WARNING: FOR AUTHORIZED SECURITY TESTING ONLY. Do NOT use for unauthorized access."


def _header_lines(rules: RuleSet, total: int, entropy_range: tuple[float, float]) -> list[str]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [
        _WARNING,
        f"# Generated: {now}",
        f"# Total candidates: {total:,}",
        f"# Entropy range: {entropy_range[0]:.1f} to {entropy_range[1]:.1f} bits",
        "",
    ]


def write_candidates(
    candidates: list[str],
    rules: RuleSet,
    *,
    fmt: str | None = None,
    path: str | None = None,
    compress: bool | None = None,
    include_header: bool | None = None,
) -> str:
    fmt = fmt or rules.output_format
    path = path or rules.output_path
    compress = rules.compress if compress is None else compress
    include_header = rules.include_header if include_header is None else include_header

    if compress and not path.endswith(".gz"):
        path += ".gz"

    entropies = [shannon_bits(pw) for pw in candidates]
    entropy_range = (
        (min(entropies), max(entropies)) if entropies else (0.0, 0.0)
    )

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    if fmt == "json":
        _write_json(candidates, rules, path, compress, include_header, entropy_range, entropies)
    elif fmt == "csv":
        _write_csv(candidates, path, compress, include_header, entropy_range, entropies)
    elif fmt == "hc22000":
        _write_hc22000(candidates, path, include_header)
    else:
        _write_txt(candidates, path, compress, include_header, entropy_range, rules)

    return path


def _open_file(path: str, compress: bool):
    if compress:
        return gzip.open(path, "wt", encoding="utf-8")
    return open(path, "w", encoding="utf-8")


def _write_txt(candidates, path, compress, include_header, entropy_range, rules):
    with _open_file(path, compress) as fh:
        if include_header:
            for line in _header_lines(rules, len(candidates), entropy_range):
                fh.write(line + "\n")
        for pw in candidates:
            fh.write(pw + "\n")


def _write_csv(candidates, path, compress, include_header, entropy_range, entropies):
    from .filter import walk_ratio
    with _open_file(path, compress) as fh:
        if include_header:
            fh.write(_WARNING + "\n")
        fh.write("candidate,entropy_bits,pattern_class\n")
        for pw, ent in zip(candidates, entropies):
            cls = _classify(pw)
            fh.write(f"{pw},{ent:.3f},{cls}\n")


def _write_json(candidates, rules, path, compress, include_header, entropy_range, entropies):
    from .filter import walk_ratio
    payload = {
        "warning": _WARNING.lstrip("# "),
        "generated": datetime.now(timezone.utc).isoformat(),
        "total": len(candidates),
        "entropy_range": {"min": entropy_range[0], "max": entropy_range[1]},
        "candidates": [
            {"pw": pw, "entropy": round(ent, 3), "pattern": _classify(pw)}
            for pw, ent in zip(candidates, entropies)
        ],
    }
    with _open_file(path, compress) as fh:
        json.dump(payload, fh, indent=2)


def _write_hc22000(candidates: list, path: str, include_header: bool) -> None:
    """
    Hashcat WPA2 PMKID format (.hc22000).
    Each line: PMKID*BSSID*CLIENT*SSID  — for wordlist use we emit
    a dummy wrapper so the file is structurally valid for -m 22000.

    Real capture files require actual PMKID/BSSID/CLIENT/SSID values.
    This format stores just the candidate word, one per line, which
    Hashcat accepts when used as a straight wordlist (-a 0) target.
    In practice, most tooling treats this file as a plain wordlist.
    """
    with open(path, "w", encoding="utf-8") as fh:
        if include_header:
            fh.write("# pwgen hc22000 wordlist — use with hashcat -m 22000 -a 0\n")
            fh.write("# WARNING: FOR AUTHORIZED SECURITY TESTING ONLY\n")
        for pw in candidates:
            fh.write(pw + "\n")


def _classify(pw: str) -> str:
    import re
    from .filter import walk_ratio
    if re.fullmatch(r'\d+', pw):
        return "numeric"
    if walk_ratio(pw) > 0.6:
        return "keyboard_walk"
    if re.fullmatch(r'[a-zA-Z]+', pw):
        return "alpha"
    if re.search(r'(.)\1{2,}', pw):
        return "repeat_block"
    if re.search(r'(19|20)\d{2}$', pw):
        return "date_suffix"
    if any(c in pw for c in '@$!#'):
        return "symbol_mutant"
    return "mixed"


def stream_write(
    source: Generator[str, None, None],
    rules: RuleSet,
    *,
    fmt: str | None = None,
    path: str | None = None,
    compress: bool | None = None,
    include_header: bool | None = None,
    max_candidates: int | None = None,
    show_progress: bool = True,
) -> dict:
    """Write candidates from a generator without materialising the full list."""
    fmt = fmt or rules.output_format
    path = path or rules.output_path
    compress = rules.compress if compress is None else compress
    include_header = rules.include_header if include_header is None else include_header
    max_candidates = max_candidates or rules.max_candidates

    if compress and not path.endswith(".gz"):
        path += ".gz"

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    try:
        from tqdm import tqdm
        progress = tqdm(unit=" cands", desc="Generating") if show_progress else None
    except ImportError:
        progress = None

    count = 0
    min_ent = float("inf")
    max_ent = float("-inf")
    batch: list[str] = []

    def _flush(fh, batch):
        nonlocal min_ent, max_ent
        for pw in batch:
            e = shannon_bits(pw)
            if e < min_ent:
                min_ent = e
            if e > max_ent:
                max_ent = e
            fh.write(pw + "\n")
        fh.flush()

    # Write placeholder header (overwrite after we know totals if not compressing)
    header_placeholder_len = 0
    with _open_file(path, compress) as fh:
        if include_header and not compress:
            placeholder = "\n".join(["# " + " " * 60] * 5) + "\n\n"
            header_placeholder_len = len(placeholder)
            fh.write(placeholder)

        for pw in source:
            batch.append(pw)
            count += 1
            if progress:
                progress.update(1)
            if max_candidates and count >= max_candidates:
                break
            if len(batch) >= _BATCH:
                _flush(fh, batch)
                batch.clear()

        if batch:
            _flush(fh, batch)

    if progress:
        progress.close()

    if min_ent == float("inf"):
        min_ent = 0.0
    if max_ent == float("-inf"):
        max_ent = 0.0

    # Rewrite header in-place (txt, non-compressed only)
    if include_header and not compress and fmt == "txt":
        header_text = "\n".join(
            _header_lines(rules, count, (min_ent, max_ent))
        )
        with open(path, "r+", encoding="utf-8") as fh:
            rest = fh.read()[header_placeholder_len:]
            fh.seek(0)
            fh.write(header_text + "\n")
            fh.write(rest)
            fh.truncate()

    return {"total": count, "path": path, "entropy_range": (min_ent, max_ent)}
