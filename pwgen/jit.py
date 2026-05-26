"""
Optional Numba JIT acceleration for the numeric filter hot-loop.

Import this module to get a faster `passes_numeric_constraints` function.
Falls back to pure Python if numba is not installed.

Only applies when:
  - charset is digits-only
  - active constraints: no_consecutive, max_repeats (digits)
"""
from __future__ import annotations

_numba_available = False

try:
    import numba  # noqa: F401
    _numba_available = True
except ImportError:
    pass


def _passes_numeric_python(
    pw: str,
    max_repeat: int,
    no_consec_count: int,
    no_consec_char: str,
) -> bool:
    """Pure-Python fallback for numeric constraint checks."""
    if no_consec_char and no_consec_char * no_consec_count in pw:
        return False
    if max_repeat > 0:
        from collections import Counter
        counts = Counter(pw)
        if any(v > max_repeat for v in counts.values()):
            return False
    return True


if _numba_available:
    import numba
    import numpy as np

    @numba.njit(cache=True)
    def _passes_numeric_jit(
        digits: numba.types.Array,
        n: int,
        max_repeat: int,
        no_consec_count: int,
        no_consec_digit: int,   # -1 means "any"
    ) -> bool:
        """
        JIT-compiled numeric constraint checker.

        digits: int8 array of digit values (0-9)
        n:      length of password
        """
        # Check max_repeat
        if max_repeat > 0:
            counts = np.zeros(10, dtype=numba.int32)
            for i in range(n):
                counts[digits[i]] += 1
            for d in range(10):
                if counts[d] > max_repeat:
                    return False

        # Check no_consecutive
        if no_consec_count > 0:
            run = 1
            for i in range(1, n):
                if no_consec_digit == -1:
                    # any char run
                    if digits[i] == digits[i - 1]:
                        run += 1
                    else:
                        run = 1
                    if run >= no_consec_count:
                        return False
                else:
                    if digits[i] == no_consec_digit:
                        run += 1
                    else:
                        run = 1
                    if run >= no_consec_count:
                        return False
        return True

    def make_jit_filter(max_repeat: int, no_consec_count: int, no_consec_char: str):
        """Return a JIT-compiled filter function configured for given rules."""
        import numpy as np

        no_consec_digit = -1
        if no_consec_char and no_consec_char != "any" and no_consec_char.isdigit():
            no_consec_digit = int(no_consec_char)

        def _filter(pw: str) -> bool:
            arr = np.frombuffer(pw.encode(), dtype=np.int8) - ord('0')
            return _passes_numeric_jit(arr, len(pw), max_repeat, no_consec_count, no_consec_digit)

        return _filter

else:
    def make_jit_filter(max_repeat: int, no_consec_count: int, no_consec_char: str):
        """Pure-Python fallback when numba is unavailable."""
        def _filter(pw: str) -> bool:
            return _passes_numeric_python(pw, max_repeat, no_consec_count, no_consec_char)
        return _filter


def is_numba_available() -> bool:
    return _numba_available


def try_build_jit_filter(rules) -> object | None:
    """
    Inspect rules and return a JIT filter if applicable, else None.

    Applicable when:
      - charset is digits-only
      - constraints are only max_repeats.digits + one no_consecutive rule
    """
    if not set(rules.charset).issubset(set("0123456789")):
        return None  # not numeric-only

    max_repeat = rules.max_repeats.get("digits", 0) if rules.max_repeats else 0

    no_consec_count = 0
    no_consec_char  = ""
    if rules.no_consecutive and len(rules.no_consecutive) == 1:
        nc = rules.no_consecutive[0]
        no_consec_count = nc.get("count", 0)
        no_consec_char  = nc.get("char", "any")

    if max_repeat == 0 and no_consec_count == 0:
        return None  # no constraints worth JIT-ing

    return make_jit_filter(max_repeat, no_consec_count, no_consec_char)
