"""
Multithreaded producer → filter → dedupe → write pipeline.

Architecture:
  Producer thread  — generates raw candidates (generator or wordlist+mutations)
  Worker threads   — filter + dedupe from shared input queue
  Writer thread    — batched disk flushes

Stats tracked per stage so --stats can show the full funnel.
"""
from __future__ import annotations
import logging
import os
import queue
import threading
import time
from typing import Callable, Generator, Iterable

from .deduper import Deduper
from .filter import passes_all, shannon_bits
from .rule_compiler import RuleSet

log = logging.getLogger(__name__)

_SENTINEL = object()
_QUEUE_MAX  = 200_000   # bounded raw queue (memory cap)
_WRITE_BATCH = 10_000   # lines per disk flush


# ---------------------------------------------------------------------------
# Stage counters (shared between threads via locks)
# ---------------------------------------------------------------------------

class _Counters:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.raw       = 0   # produced by generator
        self.filtered  = 0   # rejected by passes_all
        self.duped     = 0   # rejected by deduper
        self.written   = 0   # reached output
        self.entropy_rejected = 0  # rejected by entropy alone (for stats)
        self.min_ent   = float("inf")
        self.max_ent   = float("-inf")

    def add_raw(self, n: int = 1) -> None:
        with self._lock:
            self.raw += n

    def add_filtered(self, n: int = 1) -> None:
        with self._lock:
            self.filtered += n

    def add_duped(self, n: int = 1) -> None:
        with self._lock:
            self.duped += n

    def add_written(self, pw: str) -> None:
        e = shannon_bits(pw)
        with self._lock:
            self.written += 1
            if e < self.min_ent:
                self.min_ent = e
            if e > self.max_ent:
                self.max_ent = e

    @property
    def entropy_range(self) -> tuple[float, float]:
        lo = self.min_ent if self.min_ent != float("inf")  else 0.0
        hi = self.max_ent if self.max_ent != float("-inf") else 0.0
        return lo, hi


# ---------------------------------------------------------------------------
# Thread workers
# ---------------------------------------------------------------------------

def _producer(source: Iterable[str], raw_q: queue.Queue, n_workers: int, counters: _Counters) -> None:
    try:
        for item in source:
            counters.add_raw()
            raw_q.put(item)
    except Exception as exc:
        log.error("Producer error: %s", exc)
    finally:
        for _ in range(n_workers):
            raw_q.put(_SENTINEL)


def _worker(
    raw_q: queue.Queue,
    clean_q: queue.Queue,
    rules: RuleSet,
    deduper: Deduper,
    deduper_lock: threading.Lock,
    counters: _Counters,
    max_candidates: int | None,
) -> None:
    while True:
        item = raw_q.get()
        if item is _SENTINEL:
            break
        # Early exit if max already reached
        if max_candidates and counters.written >= max_candidates:
            continue
        if not passes_all(item, rules):
            counters.add_filtered()
            continue
        with deduper_lock:
            if not deduper.is_new(item):
                counters.add_duped()
                continue
        clean_q.put(item)
    clean_q.put(_SENTINEL)


def _writer(
    clean_q: queue.Queue,
    fh,
    n_workers: int,
    max_candidates: int | None,
    counters: _Counters,
    stop_event: threading.Event,
) -> None:
    finished = 0
    batch: list[str] = []

    while finished < n_workers:
        try:
            item = clean_q.get(timeout=0.05)
        except queue.Empty:
            continue
        if item is _SENTINEL:
            finished += 1
            continue

        counters.add_written(item)
        batch.append(item)

        if max_candidates and counters.written >= max_candidates:
            fh.write("\n".join(batch) + "\n")
            fh.flush()
            batch.clear()
            stop_event.set()
            break

        if len(batch) >= _WRITE_BATCH:
            fh.write("\n".join(batch) + "\n")
            fh.flush()
            batch.clear()

    if batch:
        fh.write("\n".join(batch) + "\n")
        fh.flush()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_pipeline(
    source: Iterable[str],
    rules: RuleSet,
    *,
    output_path: str,
    n_workers: int | None = None,
    max_candidates: int | None = None,
    compress: bool = False,
    include_header: bool = True,
    show_progress: bool = True,
    progress_callback: Callable[[int, float], None] | None = None,
) -> dict:
    """
    Run the full multithreaded pipeline and return a detailed stats dict.

    Args:
        progress_callback: optional fn(written_count, rate) called every 0.2s
                           for embedding in a GUI.
    """
    import gzip

    n_workers = n_workers or max(1, (os.cpu_count() or 4) - 1)
    max_candidates = max_candidates or rules.max_candidates

    if compress and not output_path.endswith(".gz"):
        output_path += ".gz"

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    raw_q: queue.Queue   = queue.Queue(maxsize=_QUEUE_MAX)
    clean_q: queue.Queue = queue.Queue(maxsize=_QUEUE_MAX)
    stop_event = threading.Event()

    # Tuned Bloom filter: lower error rate for larger expected sets
    deduper     = Deduper(use_bloom=True, error_rate=0.001)
    deduper_lock = threading.Lock()
    counters     = _Counters()

    open_fn = gzip.open if compress else open
    t_start = time.perf_counter()

    # tqdm progress bar
    pbar = None
    if show_progress:
        try:
            from tqdm import tqdm
            pbar = tqdm(
                unit=" cands",
                desc="Generating",
                dynamic_ncols=True,
                bar_format="{desc}: {n_fmt}{unit} [{elapsed}<{remaining}, {rate_fmt}]",
            )
        except ImportError:
            pass

    with open_fn(output_path, "wt", encoding="utf-8") as fh:
        # Placeholder header (rewritten after run for plain txt)
        header_placeholder = ""
        if include_header and not compress:
            header_placeholder = ("# " + " " * 78 + "\n") * 6 + "\n"
            fh.write(header_placeholder)
        header_len = len(header_placeholder)

        prod = threading.Thread(
            target=_producer,
            args=(source, raw_q, n_workers, counters),
            daemon=True,
        )
        workers = [
            threading.Thread(
                target=_worker,
                args=(raw_q, clean_q, rules, deduper, deduper_lock, counters, max_candidates),
                daemon=True,
            )
            for _ in range(n_workers)
        ]
        writer_thread = threading.Thread(
            target=_writer,
            args=(clean_q, fh, n_workers, max_candidates, counters, stop_event),
            daemon=True,
        )

        prod.start()
        for w in workers:
            w.start()
        writer_thread.start()

        # Monitor loop in main thread
        last_written = 0
        last_tick    = time.perf_counter()
        while writer_thread.is_alive():
            time.sleep(0.2)
            now_written = counters.written
            now_tick    = time.perf_counter()
            delta       = now_written - last_written
            elapsed_tick = now_tick - last_tick

            if pbar is not None:
                pbar.update(delta)

            if progress_callback and elapsed_tick > 0:
                rate = delta / elapsed_tick
                progress_callback(now_written, rate)

            last_written = now_written
            last_tick    = now_tick

        # Final update
        if pbar is not None:
            pbar.update(counters.written - last_written)
            pbar.close()

        prod.join()
        for w in workers:
            w.join()
        writer_thread.join()

    elapsed = time.perf_counter() - t_start
    total   = counters.written
    lo, hi  = counters.entropy_range
    rate    = total / elapsed if elapsed > 0 else 0

    # Rewrite header in-place (plain txt only)
    if include_header and not compress:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        header_lines = [
            "# WARNING: FOR AUTHORIZED SECURITY TESTING ONLY. Do NOT use for unauthorized access.",
            f"# Generated:          {now}",
            f"# Candidates (raw):   {counters.raw:,}",
            f"# After filter:       {counters.raw - counters.filtered:,}  (-{counters.filtered / max(counters.raw,1)*100:.1f}%)",
            f"# After dedup:        {total:,}  (-{counters.duped / max(counters.raw,1)*100:.1f}%)",
            f"# Entropy range:      {lo:.1f} to {hi:.1f} bits",
            f"# Rate:               {rate:,.0f} cands/sec",
            "",
        ]
        header_text = "\n".join(header_lines)
        with open(output_path, "r+", encoding="utf-8") as fh:
            body = fh.read()[header_len:]
            fh.seek(0)
            fh.write(header_text + "\n")
            fh.write(body)
            fh.truncate()

    log.info(
        "Pipeline done: %s written / %s raw in %.2fs (%.0f/s)",
        f"{total:,}", f"{counters.raw:,}", elapsed, rate,
    )

    return {
        "total":           total,
        "path":            output_path,
        "entropy_range":   (lo, hi),
        "elapsed_sec":     round(elapsed, 3),
        "rate_per_sec":    round(rate),
        "raw_count":       counters.raw,
        "filtered_count":  counters.filtered,
        "duped_count":     counters.duped,
        "deduper_stats":   deduper.stats,
    }
