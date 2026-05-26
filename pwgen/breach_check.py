"""
Breach check module — HIBP k-anonymity API + local file binary search.

k-anonymity protocol:
  1. SHA-1 hash the password
  2. Send only the first 5 hex chars to the API
  3. Check if the remainder appears in the response
  4. Never reveals the full password to the server

Local mode:
  Binary search on a sorted SHA-1 hash file (e.g. HIBP downloaded dump).
  Hash lines must be in format: HASH:count  (as distributed by HIBP)
"""
from __future__ import annotations
import bisect
import hashlib
import logging
import time
from pathlib import Path
from typing import Generator, Iterable

log = logging.getLogger(__name__)

_API_BASE = "https://api.pwnedpasswords.com/range/"
_TIMEOUT  = 4   # seconds per API call
_BACKOFF  = [1, 2, 4]  # retry delays


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _sha1(pw: str) -> str:
    return hashlib.sha1(pw.encode("utf-8")).hexdigest().upper()


def _hibp_lookup(prefix: str) -> set[str]:
    """Return the set of SHA-1 suffixes seen in HIBP for this 5-char prefix."""
    import requests
    url = _API_BASE + prefix
    for attempt, delay in enumerate([0] + _BACKOFF):
        if delay:
            time.sleep(delay)
        try:
            resp = requests.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
            suffixes = set()
            for line in resp.text.splitlines():
                parts = line.split(":")
                if parts:
                    suffixes.add(parts[0].upper())
            return suffixes
        except Exception as exc:
            if attempt == len(_BACKOFF):
                log.error("HIBP API failed after %d retries: %s", len(_BACKOFF), exc)
                return set()
            log.warning("HIBP retry %d: %s", attempt + 1, exc)
    return set()


def is_breached_api(pw: str) -> bool:
    """Check if password appears in HIBP via k-anonymity API."""
    h = _sha1(pw)
    prefix, suffix = h[:5], h[5:]
    seen_suffixes = _hibp_lookup(prefix)
    return suffix in seen_suffixes


# ---------------------------------------------------------------------------
# Local file lookup
# ---------------------------------------------------------------------------

class LocalHIBP:
    """Binary-search index over a sorted HIBP hash file (hash:count per line)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"HIBP local file not found: {path}")
        log.info("Loading HIBP local file: %s", self.path)
        self._hashes: list[str] = []
        with self.path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    self._hashes.append(line.split(":")[0].upper())
        # Must be sorted for binary search
        if self._hashes and self._hashes != sorted(self._hashes):
            log.warning("HIBP file does not appear sorted — sorting in memory.")
            self._hashes.sort()
        log.info("Loaded %s hashes from local file.", f"{len(self._hashes):,}")

    def is_breached(self, pw: str) -> bool:
        h = _sha1(pw)
        idx = bisect.bisect_left(self._hashes, h)
        return idx < len(self._hashes) and self._hashes[idx] == h


# ---------------------------------------------------------------------------
# Streaming filter
# ---------------------------------------------------------------------------

def breach_filter(
    source: Iterable[str],
    *,
    use_api: bool = True,
    local_path: str | None = None,
    exclude: bool = False,
    flag_column: bool = False,
) -> Generator[tuple[str, bool], None, None]:
    """
    Yield (candidate, is_breached) tuples.

    Args:
        source:      iterable of password strings
        use_api:     query HIBP k-anonymity API
        local_path:  path to local HIBP sorted hash file (faster, offline)
        exclude:     if True, skip breached candidates entirely
        flag_column: emit (pw, breached) tuples regardless of exclude
    """
    local_db: LocalHIBP | None = None
    if local_path:
        local_db = LocalHIBP(local_path)

    # Cache API responses — group by prefix to reduce calls
    _prefix_cache: dict[str, set[str]] = {}

    def _check(pw: str) -> bool:
        if local_db:
            return local_db.is_breached(pw)
        if use_api:
            h = _sha1(pw)
            prefix, suffix = h[:5], h[5:]
            if prefix not in _prefix_cache:
                _prefix_cache[prefix] = _hibp_lookup(prefix)
            return suffix in _prefix_cache[prefix]
        return False

    for pw in source:
        breached = _check(pw)
        if exclude and breached:
            continue
        yield pw, breached


def annotate_breached(
    candidates: list[str],
    *,
    use_api: bool = True,
    local_path: str | None = None,
) -> list[dict]:
    """Return list of {pw, breached} dicts for a batch of candidates."""
    results = []
    for pw, breached in breach_filter(
        candidates, use_api=use_api, local_path=local_path, exclude=False
    ):
        results.append({"pw": pw, "breached": breached})
    return results
