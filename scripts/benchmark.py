"""
Benchmark: candidates/sec for a given charset + length.

Usage:
  python scripts/benchmark.py
  python scripts/benchmark.py --length 6 --charset digits --threads 4
"""
from __future__ import annotations
import argparse
import sys
import time
import os

# Make sure the package is importable when run from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pwgen.rule_compiler import compile_rules, CHARSETS
from pwgen.generator import generate
from pwgen.filter import passes_all
from pwgen.pipeline import run_pipeline


def _estimate(charset_len: int, length: int) -> int:
    return charset_len ** length


def bench_generator(cfg: dict, sample_limit: int = 1_000_000) -> dict:
    """Benchmark the raw generator throughput (no I/O, no filter)."""
    rules = compile_rules(cfg)
    count = 0
    t0 = time.perf_counter()
    for _ in generate(rules):
        count += 1
        if count >= sample_limit:
            break
    elapsed = time.perf_counter() - t0
    rate = count / elapsed if elapsed > 0 else 0
    return {"count": count, "elapsed": elapsed, "rate": rate}


def bench_stream(cfg: dict, sample_limit: int, output_path: str) -> dict:
    """Benchmark single-threaded streaming pipeline (generator → filter → write)."""
    from pwgen.filter import passes_all
    from pwgen.deduper import Deduper

    rules = compile_rules(cfg)
    deduper = Deduper(use_bloom=True)
    count = 0
    t0 = time.perf_counter()

    with open(output_path, "w", encoding="utf-8") as fh:
        batch = []
        for pw in generate(rules):
            if not passes_all(pw, rules):
                continue
            if not deduper.is_new(pw):
                continue
            batch.append(pw)
            count += 1
            if count >= sample_limit:
                break
            if len(batch) >= 10_000:
                fh.write("\n".join(batch) + "\n")
                batch.clear()
        if batch:
            fh.write("\n".join(batch) + "\n")

    elapsed = time.perf_counter() - t0
    rate = count / elapsed if elapsed > 0 else 0
    return {"count": count, "elapsed": elapsed, "rate": rate}


def bench_pipeline(cfg: dict, output_path: str, n_workers: int) -> dict:
    """Benchmark the full multithreaded pipeline including I/O."""
    import tempfile
    rules = compile_rules(cfg)
    source = generate(rules)
    result = run_pipeline(
        source,
        rules,
        output_path=output_path,
        n_workers=n_workers,
        include_header=False,
        show_progress=False,
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="pwgen benchmark")
    parser.add_argument("--length", type=int, default=6)
    parser.add_argument("--charset", default="digits",
                        choices=list(CHARSETS.keys()))
    parser.add_argument("--threads", type=int, default=max(1, (os.cpu_count() or 4) - 1))
    parser.add_argument("--limit", type=int, default=2_000_000,
                        help="Max candidates to generate")
    parser.add_argument("--output", default="bench_out.txt")
    args = parser.parse_args()

    charset_len = len(CHARSETS[args.charset])
    total_possible = _estimate(charset_len, args.length)

    print(f"\n{'='*55}")
    print(f"  pwgen Benchmark")
    print(f"{'='*55}")
    print(f"  Charset      : {args.charset} ({charset_len} chars)")
    print(f"  Length       : {args.length}")
    print(f"  Possible     : {total_possible:,}")
    print(f"  Limit        : {args.limit:,}")
    print(f"  Threads      : {args.threads}")
    print(f"{'='*55}\n")

    cfg = {
        "charset": args.charset,
        "length": args.length,
        "output": {"path": args.output, "format": "txt", "include_header": False},
    }

    # 1. Raw generator speed
    print("[ 1/3 ] Raw generator (no I/O, no filter)...")
    gen_result = bench_generator(cfg, sample_limit=args.limit)
    print(f"        {gen_result['count']:>12,} candidates")
    print(f"        {gen_result['elapsed']:>10.3f} s")
    print(f"        {gen_result['rate']:>12,.0f} cands/sec\n")

    # 2. Single-threaded streaming (generator + filter + dedupe + I/O)
    print("[ 2/3 ] Single-threaded stream (filter + dedupe + I/O)...")
    stream_result = bench_stream(cfg, args.limit, args.output)
    print(f"        {stream_result['count']:>12,} candidates")
    print(f"        {stream_result['elapsed']:>10.3f} s")
    print(f"        {stream_result['rate']:>12,.0f} cands/sec\n")
    if os.path.exists(args.output):
        os.remove(args.output)

    # 3. Multithreaded pipeline
    print(f"[ 3/3 ] Multithreaded pipeline ({args.threads} workers)...")
    pipe_result = bench_pipeline({**cfg, "output": {"path": args.output, "format": "txt"}},
                                  args.output, args.threads)
    print(f"        {pipe_result['total']:>12,} candidates")
    print(f"        {pipe_result['elapsed_sec']:>10.3f} s")
    print(f"        {pipe_result['rate_per_sec']:>12,} cands/sec")
    print(f"        Deduper: {pipe_result['deduper_stats']['duplicates']:,} dupes removed\n")

    # Goal check -- use best of single vs multi
    goal = 5_000_000
    best_rate = max(int(gen_result['rate']), int(stream_result['rate']), pipe_result['rate_per_sec'])
    status = "PASS" if best_rate >= goal else "MISS (see Week 3: Numba JIT / Rust port)"
    print(f"  Best rate : {best_rate:,} cands/sec")
    print(f"  Goal      : {goal:,} cands/sec -> {status}")
    print(f"{'='*55}\n")

    # Cleanup
    if os.path.exists(args.output):
        os.remove(args.output)


if __name__ == "__main__":
    main()
