"""
Password mutation engine — generates systematic real-world password variants.

Each mutation is a generator function (str → Iterator[str]) so it can produce
many variants from a single seed word.  apply_mutations() chains them all and
deduplicates output up to max_expansion candidates per seed.

Standard mutations for seed "dedunu":
  dedunu, Dedunu, DEDUNU, unuded, d3dunu, dedunu0..9,
  dedunu!@#$…, dedunu1990..2026, Dedunu0..9, Dedunu!@#…,
  d3dunu0..9, dedunu123/1234/12345, dedunu01..99, !dedunu, …

Aggressive adds: full leet, double, toggle, insert-symbol, cross-suffix,
  year+symbol combos, prepend digits, prepend symbols, etc.
"""
from __future__ import annotations
from typing import Generator

# ── Character maps ─────────────────────────────────────────────────────────────
LEET_MAP: dict[str, str] = {
    'a': '@', 'e': '3', 'i': '1', 'l': '1',
    'o': '0', 's': '$', 't': '7',
}
LEET_FULL_MAP: dict[str, str] = {
    **LEET_MAP, 'b': '8', 'g': '9', 'q': '9', 'z': '2', 'h': '#',
}

_YEARS   = [str(y) for y in range(1990, 2027)]
_RECENT  = [str(y) for y in range(2000, 2027)]   # shorter list for combos
_SYMBOLS = list("!@#$%^&*_-+=?")
_DIGITS  = list("0123456789")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _leet(pw: str) -> str:
    return "".join(LEET_MAP.get(c.lower(), c) for c in pw)


def _full_leet(pw: str) -> str:
    return "".join(LEET_FULL_MAP.get(c.lower(), c) for c in pw)


# ── Mutation generators ────────────────────────────────────────────────────────
# Each takes a single str and yields str variants.

def _capitalize(p: str):
    yield p.capitalize()

def _upper(p: str):
    yield p.upper()

def _lower(p: str):
    yield p.lower()

def _reverse(p: str):
    yield p[::-1]

def _toggle_case(p: str):
    yield p.swapcase()

def _double(p: str):
    yield p + p

def _prefix_bang(p: str):
    yield "!" + p

def _leet_swap(p: str):
    r = _leet(p)
    if r != p:
        yield r

def _leet_full_swap(p: str):
    r = _full_leet(p)
    if r != p:
        yield r

def _suffix_123(p: str):
    yield p + "123"
    yield p + "1234"
    yield p + "12345"
    yield p + "000"
    yield p + "001"
    yield p + "007"
    yield p + "999"
    yield p + "1!"
    yield p + "2@"

def _append_digits(p: str):
    """Append each single digit: dedunu0, dedunu1, …, dedunu9"""
    for d in _DIGITS:
        yield p + d

def _prepend_digits(p: str):
    """Prepend each single digit: 0dedunu, 1dedunu, …"""
    for d in _DIGITS:
        yield d + p

def _append_symbols(p: str):
    """Append each symbol: dedunu!, dedunu@, …"""
    for s in _SYMBOLS:
        yield p + s

def _prepend_symbols(p: str):
    """Prepend each symbol: !dedunu, @dedunu, …"""
    for s in _SYMBOLS[:5]:
        yield s + p

def _suffix_2digit(p: str):
    """Append two-digit numbers 00-99: dedunu00, …, dedunu99"""
    for n in range(100):
        yield p + f"{n:02d}"

def _append_years(p: str):
    """Append years 1990-2026: dedunu1990, dedunu2004, …"""
    for y in _YEARS:
        yield p + y

def _cap_digit(p: str):
    """Capitalised + digit: Dedunu0, Dedunu1, …"""
    cap = p.capitalize()
    if cap != p:
        for d in _DIGITS:
            yield cap + d

def _cap_symbol(p: str):
    """Capitalised + symbol: Dedunu!, Dedunu@, …"""
    cap = p.capitalize()
    if cap != p:
        for s in _SYMBOLS:
            yield cap + s

def _cap_year(p: str):
    """Capitalised + year: Dedunu2004, Dedunu1990, …"""
    cap = p.capitalize()
    if cap != p:
        for y in _YEARS:
            yield cap + y

def _leet_digit(p: str):
    """Leet + digit: d3dunu0, d3dunu1, …"""
    lt = _leet(p)
    if lt != p:
        for d in _DIGITS:
            yield lt + d

def _leet_symbol(p: str):
    """Leet + symbol: d3dunu!, d3dunu@, …"""
    lt = _leet(p)
    if lt != p:
        for s in _SYMBOLS[:5]:
            yield lt + s

def _year_symbol(p: str):
    """word+year+symbol: dedunu2004!, dedunu2004@, …"""
    for y in _RECENT:
        for s in _SYMBOLS[:5]:
            yield p + y + s

def _cap_year_symbol(p: str):
    """Dedunu2004!, Dedunu2004@, …"""
    cap = p.capitalize()
    if cap != p:
        for y in _RECENT:
            for s in _SYMBOLS[:3]:
                yield cap + y + s

def _digit_symbol(p: str):
    """word+digit+symbol: dedunu1!, dedunu2@, …"""
    for d in _DIGITS:
        for s in _SYMBOLS[:4]:
            yield p + d + s

def _symbol_digit(p: str):
    """word+symbol+digit: dedunu!1, dedunu@2, …"""
    for s in _SYMBOLS[:4]:
        for d in _DIGITS:
            yield p + s + d

def _insert_symbol_mid(p: str):
    """Insert a symbol at the midpoint: ded!unu, ded@unu, …"""
    mid = len(p) // 2
    for s in _SYMBOLS[:5]:
        yield p[:mid] + s + p[mid:]

def _truncate_suffix(p: str):
    """Short truncations + suffix — e.g. dedu2004, dedu!"""
    if len(p) > 4:
        short = p[:4]
        for d in _DIGITS:
            yield short + d
        for s in _SYMBOLS[:4]:
            yield short + s
        for y in _RECENT[-10:]:
            yield short + y


# ── Registry ───────────────────────────────────────────────────────────────────

MUTATIONS: dict[str, object] = {
    "capitalize":       _capitalize,
    "upper":            _upper,
    "lower":            _lower,
    "reverse":          _reverse,
    "toggle_case":      _toggle_case,
    "double":           _double,
    "prefix_bang":      _prefix_bang,
    "suffix_123":       _suffix_123,
    "leet_swap":        _leet_swap,
    "l33t_full":        _leet_full_swap,
    "append_digits":    _append_digits,
    "prepend_digits":   _prepend_digits,
    "append_symbols":   _append_symbols,
    "prepend_symbols":  _prepend_symbols,
    "suffix_2digit":    _suffix_2digit,
    "append_years":     _append_years,
    "cap_digit":        _cap_digit,
    "cap_symbol":       _cap_symbol,
    "cap_year":         _cap_year,
    "leet_digit":       _leet_digit,
    "leet_symbol":      _leet_symbol,
    "year_symbol":      _year_symbol,
    "cap_year_symbol":  _cap_year_symbol,
    "digit_symbol":     _digit_symbol,
    "symbol_digit":     _symbol_digit,
    "insert_symbol_mid":_insert_symbol_mid,
    "truncate_suffix":  _truncate_suffix,
}

# Standard: practical, not too large
_STANDARD = [
    "capitalize",        # Dedunu
    "append_digits",     # dedunu0-9
    "append_symbols",    # dedunu!@#…
    "cap_digit",         # Dedunu0-9
    "cap_symbol",        # Dedunu!@#…
    "suffix_123",        # dedunu123, dedunu1234, …
    "leet_swap",         # d3dunu
    "suffix_2digit",     # dedunu00-99
    "append_years",      # dedunu1990-2026
    "cap_year",          # Dedunu1990-2026
    "digit_symbol",      # dedunu1!, dedunu2@, …
]

# Aggressive: everything
_AGGRESSIVE = list(MUTATIONS.keys())

PROFILES: dict[str, list[str]] = {
    "none":       [],
    "standard":   _STANDARD,
    "aggressive": _AGGRESSIVE,
}


# ── Core function ──────────────────────────────────────────────────────────────

def apply_mutations(
    base: str,
    enabled: list[str],
    max_expansion: int,
) -> Generator[str, None, None]:
    """
    Yield base word then all enabled mutation variants (deduplicated).
    Stops after max_expansion variants (not counting base).
    """
    seen: set[str] = {base}
    yield base

    count = 0
    for name in enabled:
        if count >= max_expansion:
            return
        fn = MUTATIONS.get(name)
        if fn is None:
            continue
        try:
            for result in fn(base):  # type: ignore[operator]
                if count >= max_expansion:
                    return
                if result not in seen:
                    seen.add(result)
                    yield result
                    count += 1
        except Exception:
            continue
