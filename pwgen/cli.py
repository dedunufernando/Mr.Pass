"""CLI entry point."""
from __future__ import annotations
import argparse
import json
import sys
import warnings
from pathlib import Path

import yaml

from . import __version__
from .hint_parser import parse_hints
from .rule_compiler import compile_rules, RuleConflictError
from .generator import generate
from .filter import passes_all
from .io import stream_write

_LARGE_THRESHOLD = 100_000_000


def _load_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    text = p.read_text(encoding="utf-8")
    if p.suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    return json.loads(text)


def _estimate_size(charset_len: int, length: int | None, min_len: int, max_len: int) -> int:
    if length is not None:
        return charset_len ** length
    return sum(charset_len ** n for n in range(min_len, max_len + 1))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pwgen",
        description="Password candidate list generator for authorized security testing.",
    )
    p.add_argument("-v", "--version", action="version", version=f"pwgen {__version__}")

    # Config
    p.add_argument("-c", "--config", metavar="PATH", help="JSON/YAML constraints file")
    p.add_argument("-o", "--output", metavar="PATH", default="wordlist.txt")
    p.add_argument("-f", "--format", dest="fmt", metavar="FORMAT",
                   choices=["txt", "gz", "csv", "json", "hc22000"], default="txt")

    # Generation
    p.add_argument("-l", "--length", type=int)
    p.add_argument("-m", "--min-length", type=int)
    p.add_argument("-M", "--max-length", type=int)
    p.add_argument("--charset", default="digits",
                   choices=["digits", "alpha", "lower", "upper", "alnum", "ascii", "binary", "custom"])
    p.add_argument("--custom-chars", metavar="STRING")
    p.add_argument("--tier", choices=["none", "tiny", "small", "large", "custom"], default="none")
    p.add_argument("--wordlist", metavar="PATH")
    p.add_argument("--mutations", metavar="PROFILE", default="none",
                   choices=["none", "standard", "aggressive"])
    p.add_argument("--max-expand", type=int, default=50)
    p.add_argument("--large", action="store_true", help="Allow jobs > 100M candidates")

    # Constraint shortcuts
    p.add_argument("--no-consecutive", metavar="SPEC",
                   help="E.g. '0:3' = no char '0' repeated 3+ times")
    p.add_argument("--max-repeats", type=int, metavar="INT")
    p.add_argument("--min-entropy", type=float, default=0.0)
    p.add_argument("--no-keyboard-walks", action="store_true")

    # Output
    p.add_argument("--sort-by", choices=["entropy", "alpha", "length", "none"], default="entropy")
    p.add_argument("--limit", type=int)
    p.add_argument("--compress", action="store_true")
    p.add_argument("--no-header", action="store_true")

    # Misc
    p.add_argument("--stats", action="store_true")
    p.add_argument("--threads", type=int)
    p.add_argument("--debug", action="store_true")
    p.add_argument("--preset", choices=["numeric_7", "enterprise", "ctf_binary"])
    p.add_argument("--hints", nargs="+", metavar="HINT",
                   help="Plain-language hints, e.g. --hints '7 characters' 'no 3 zeros in a row'")

    # Breach check
    p.add_argument("--breach-check", action="store_true",
                   help="Flag candidates found in HIBP (k-anonymity API)")
    p.add_argument("--breach-local", metavar="PATH",
                   help="Local HIBP sorted hash file for offline check")
    p.add_argument("--exclude-breached", action="store_true",
                   help="Remove breached candidates from output")

    # Visualization
    p.add_argument("--viz-entropy", metavar="PATH",
                   help="Save entropy histogram PNG")
    p.add_argument("--viz-keyboard", metavar="PATH",
                   help="Save keyboard heatmap PNG")
    p.add_argument("--viz-patterns", metavar="PATH",
                   help="Save pattern distribution chart PNG")
    p.add_argument("--viz-all", metavar="DIR",
                   help="Save all three charts into a directory")

    # GUI
    p.add_argument("--gui", action="store_true")

    return p


def _args_to_cfg(args: argparse.Namespace) -> dict:
    cfg: dict = {}

    # Preset base
    if args.preset:
        preset_path = Path(__file__).parent.parent / "config" / "presets" / f"{args.preset}.json"
        if preset_path.exists():
            cfg = json.loads(preset_path.read_text(encoding="utf-8"))

    # File config (overrides preset)
    if args.config:
        file_cfg = _load_config(args.config)
        cfg.update(file_cfg)

    # Hint parser (layered on top)
    if args.hints:
        hint_cfg = parse_hints(args.hints)
        cfg.update(hint_cfg)

    # CLI flags (highest priority)
    if args.charset:
        if args.charset == "custom" and args.custom_chars:
            cfg["charset"] = "custom"
            cfg["custom_chars"] = args.custom_chars
        else:
            cfg["charset"] = args.charset

    if args.length is not None:
        cfg["length"] = args.length
    if args.min_length is not None:
        cfg["min_length"] = args.min_length
    if args.max_length is not None:
        cfg["max_length"] = args.max_length

    if args.no_consecutive:
        parts = args.no_consecutive.split(":")
        char = parts[0] if len(parts) >= 1 else "any"
        count = int(parts[1]) if len(parts) >= 2 else 3
        cfg.setdefault("no_consecutive", []).append({"char": char, "count": count})

    if args.max_repeats is not None:
        cfg.setdefault("max_repeats", {})["digits"] = args.max_repeats

    if args.min_entropy and args.min_entropy > 0:
        cfg["entropy"] = {"min_bits": args.min_entropy}

    if args.no_keyboard_walks:
        cfg["keyboard_walk"] = {"reject_if_walk_ratio_above": 0.5}

    if args.mutations != "none":
        cfg.setdefault("mutations", {})["profile"] = args.mutations

    if args.max_expand != 50:
        cfg.setdefault("mutations", {})["max_expansion"] = args.max_expand

    if args.tier != "none":
        cfg.setdefault("wordlist", {})["tier"] = args.tier
    if args.wordlist:
        cfg.setdefault("wordlist", {})["custom_path"] = args.wordlist

    cfg.setdefault("output", {}).update({
        "format": args.fmt,
        "path": args.output,
        "compress": args.compress,
        "sort_by": args.sort_by,
        "include_header": not args.no_header,
    })
    if args.limit:
        cfg["output"]["max_candidates"] = args.limit

    return cfg


def _print_stats(result: dict, rules) -> None:
    lo, hi = result["entropy_range"]
    raw  = result.get("raw_count", result["total"])
    filt = result.get("filtered_count", 0)
    duped = result.get("duped_count", 0)
    total = result["total"]
    elapsed = result.get("elapsed_sec", 0)
    rate    = result.get("rate_per_sec", 0)

    sep = "-" * 46
    print(f"\n{sep}")
    print(f"  Generation Statistics")
    print(sep)
    if raw != total:
        after_filt = raw - filt
        pct_filt   = filt  / max(raw, 1) * 100
        pct_dedup  = duped / max(raw, 1) * 100
        pct_final  = total / max(raw, 1) * 100
        print(f"  Candidates generated   : {raw:>12,}")
        print(f"  After constraint filter: {after_filt:>12,}  (-{pct_filt:.1f}%)")
        print(f"  After deduplication    : {total:>12,}  (-{pct_dedup:.1f}%)")
        print(f"  " + "-" * 41)
        print(f"  Final output           : {total:>12,}  ({pct_final:.1f}% of raw)")
    else:
        print(f"  Final output           : {total:>12,}")
    print(f"  Entropy range          : {lo:.1f} - {hi:.1f} bits")
    if elapsed:
        print(f"  Elapsed time           : {elapsed:.2f}s")
        print(f"  Generation rate        : {rate:>12,} cands/sec")
    if "deduper_stats" in result:
        ds = result["deduper_stats"]
        print(f"  Deduper mode           : {ds['mode']}")
    print(f"  Output file            : {result['path']}")
    print(f"{sep}\n")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.gui:
        try:
            from .gui import run_gui
            run_gui()
        except ImportError:
            print("GUI requires tkinter (included with most Python installs).")
        return

    if args.debug:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    try:
        cfg = _args_to_cfg(args)
        rules = compile_rules(cfg)
    except (RuleConflictError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)

    # Safety check for large combinatorial jobs (skip for wordlist mode)
    wordlist_mode = rules.wordlist_tier != "none" or rules.wordlist_custom_path
    if not wordlist_mode:
        cs_len = len(rules.charset)
        estimated = _estimate_size(cs_len, rules.length, rules.min_length, rules.max_length)
        if estimated > _LARGE_THRESHOLD and not args.large:
            print(
                f"[warning] Estimated {estimated:,} candidates before filtering. "
                "Use --large to proceed.",
                file=sys.stderr,
            )
            sys.exit(1)

    if wordlist_mode:
        result = _run_wordlist_mode(args, rules)
    else:
        result = _run_combinatorial_mode(args, rules)

    _post_process(args, result)


def _run_combinatorial_mode(args, rules) -> dict:
    from .generator import generate
    from .filter import shannon_bits
    from .pipeline import run_pipeline
    from .io import write_candidates

    source = generate(rules)

    if rules.sort_by == "entropy":
        candidates = list(source)
        if rules.max_candidates:
            candidates = candidates[:rules.max_candidates]
        candidates.sort(key=shannon_bits, reverse=True)
        result_path = write_candidates(
            candidates, rules,
            fmt=rules.output_format,
            path=rules.output_path,
            compress=rules.compress,
            include_header=rules.include_header,
        )
        lo = min((shannon_bits(p) for p in candidates), default=0.0)
        hi = max((shannon_bits(p) for p in candidates), default=0.0)
        result = {"total": len(candidates), "path": result_path,
                  "entropy_range": (lo, hi), "_candidates": candidates}
    else:
        result = run_pipeline(
            source, rules,
            output_path=rules.output_path,
            n_workers=args.threads,
            max_candidates=rules.max_candidates,
            compress=rules.compress,
            include_header=rules.include_header,
            show_progress=True,
        )

    if args.stats:
        _print_stats(result, rules)
    else:
        print(f"Done -- {result['total']:,} candidates -> {result['path']}")

    return result


def _run_wordlist_mode(args, rules) -> dict:
    from .seed_loader import load_wordlist
    from .mutation_pipeline import apply_mutations, PROFILES
    from .pipeline import run_pipeline

    enabled = rules.mutations_enabled or PROFILES.get(rules.mutations_profile, [])

    def source():
        for base in load_wordlist(rules):
            yield from apply_mutations(base, enabled, rules.max_expansion)

    result = run_pipeline(
        source(), rules,
        output_path=rules.output_path,
        n_workers=args.threads,
        max_candidates=rules.max_candidates,
        compress=rules.compress,
        include_header=rules.include_header,
        show_progress=True,
    )

    if args.stats:
        _print_stats(result, rules)
    else:
        print(f"Done -- {result['total']:,} candidates -> {result['path']}")

    return result


def _post_process(args, result: dict) -> None:
    """Run viz and breach-check after generation completes."""
    output_path = result["path"]

    # Load candidates from disk if not already in memory
    def _load_candidates() -> list[str]:
        if "_candidates" in result:
            return result["_candidates"]
        try:
            with open(output_path, encoding="utf-8", errors="replace") as f:
                return [l.strip() for l in f if l.strip() and not l.startswith("#")]
        except OSError:
            return []

    # ── Breach check ──────────────────────────────────────────────────────
    do_breach = getattr(args, "breach_check", False) or getattr(args, "breach_local", None)
    if do_breach:
        from .breach_check import breach_filter
        candidates = _load_candidates()
        print(f"Checking {len(candidates):,} candidates against HIBP...")
        flagged = 0
        clean: list[str] = []
        for pw, breached in breach_filter(
            candidates,
            use_api=getattr(args, "breach_check", False),
            local_path=getattr(args, "breach_local", None),
            exclude=False,
        ):
            if breached:
                flagged += 1
            if not (getattr(args, "exclude_breached", False) and breached):
                clean.append(pw)
        pct = flagged / max(len(candidates), 1) * 100
        print(f"Breach-flagged: {flagged:,} ({pct:.1f}%)")
        if getattr(args, "exclude_breached", False) and flagged:
            print(f"Removed {flagged:,} breached candidates. Rewriting output...")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("# WARNING: FOR AUTHORIZED SECURITY TESTING ONLY\n")
                for pw in clean:
                    f.write(pw + "\n")

    # ── Visualizations ────────────────────────────────────────────────────
    viz_any = (
        getattr(args, "viz_entropy", None)
        or getattr(args, "viz_keyboard", None)
        or getattr(args, "viz_patterns", None)
        or getattr(args, "viz_all", None)
    )
    if viz_any:
        try:
            from .viz import plot_entropy_histogram, plot_keyboard_heatmap, \
                             plot_pattern_distribution, plot_all
        except ImportError as e:
            print(f"[warn] Visualization requires matplotlib: {e}", file=sys.stderr)
            return

        candidates = _load_candidates()
        if not candidates:
            print("[warn] No candidates to visualize.", file=sys.stderr)
            return

        if getattr(args, "viz_all", None):
            paths = plot_all(candidates, args.viz_all,
                             entropy_threshold=getattr(args, "min_entropy", None) or None)
            for name, p in paths.items():
                print(f"Chart saved: {p}  ({name})")
        else:
            if getattr(args, "viz_entropy", None):
                p = plot_entropy_histogram(candidates, args.viz_entropy)
                print(f"Entropy chart -> {p}")
            if getattr(args, "viz_keyboard", None):
                p = plot_keyboard_heatmap(candidates, args.viz_keyboard)
                print(f"Keyboard chart -> {p}")
            if getattr(args, "viz_patterns", None):
                p = plot_pattern_distribution(candidates, args.viz_patterns)
                print(f"Patterns chart -> {p}")


if __name__ == "__main__":
    main()
