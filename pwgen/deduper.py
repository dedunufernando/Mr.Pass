"""Bloom-filter-based deduplication — O(1) memory, ~99.9% accuracy."""
from __future__ import annotations
from typing import Generator, Iterable

try:
    from pybloom_live import ScalableBloomFilter

    def make_bloom() -> ScalableBloomFilter:
        return ScalableBloomFilter(
            mode=ScalableBloomFilter.SMALL_SET_GROWTH,
            error_rate=0.001,
        )

    _BLOOM_AVAILABLE = True
except ImportError:
    _BLOOM_AVAILABLE = False


class Deduper:
    """Wraps a Bloom filter (or plain set fallback) to track seen candidates."""

    def __init__(self, use_bloom: bool = True, error_rate: float = 0.001) -> None:
        if use_bloom and _BLOOM_AVAILABLE:
            from pybloom_live import ScalableBloomFilter
            self._seen = ScalableBloomFilter(
                mode=ScalableBloomFilter.SMALL_SET_GROWTH,
                error_rate=error_rate,
            )
            self._mode = "bloom"
        else:
            self._seen: set[str] = set()  # type: ignore[assignment]
            self._mode = "set"
        self._total = 0
        self._dupes = 0

    def is_new(self, candidate: str) -> bool:
        self._total += 1
        if candidate in self._seen:
            self._dupes += 1
            return False
        self._seen.add(candidate)
        return True

    @property
    def stats(self) -> dict:
        return {
            "mode": self._mode,
            "seen": self._total,
            "duplicates": self._dupes,
            "unique": self._total - self._dupes,
        }


def dedupe_stream(
    source: Iterable[str],
    use_bloom: bool = True,
) -> Generator[str, None, None]:
    """Yield only first-seen candidates from source."""
    deduper = Deduper(use_bloom=use_bloom)
    for candidate in source:
        if deduper.is_new(candidate):
            yield candidate
