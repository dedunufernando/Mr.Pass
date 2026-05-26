# pwgen — Password Candidate List Generator

> **FOR AUTHORIZED SECURITY TESTING ONLY.**  
> CTF challenges, penetration testing with explicit permission, and authorized audits.  
> Do NOT use for unauthorized access.

A lightweight, CLI-first password candidate generator with a rule-engine at its core.
Generates only candidates that satisfy every constraint simultaneously — using
backtracking pruning during generation, not brute-force filtering after the fact.

---

## Quick Start

```bash
pip install -e .

# Week 1 milestone — 7-digit numeric, no 3 zeros in a row, same digit max twice
pwgen --length 7 --charset digits --no-consecutive 0:3 --max-repeats 2 --stats

# Wordlist + mutations
pwgen --tier tiny --mutations standard --output out.txt --stats

# Preset
pwgen --preset numeric_7 --output numeric.txt

# Plain-language hints
pwgen --hints "7 characters" "no 3 zeros in a row" "digits only"

# With charts
pwgen --preset numeric_7 --viz-all charts/ --output out.txt --limit 100000

# GUI
pwgen --gui
```

---

## Installation

```bash
# Core
pip install -e .

# Visualization (optional)
pip install matplotlib seaborn

# JIT acceleration (optional)
pip install numba

# GPU (optional, CUDA 12)
pip install cupy-cuda12x
```

### Docker

```bash
docker build -t pwgen .
docker run --rm -v "$PWD/output:/output" pwgen \
  --preset numeric_7 --output /output/numeric.txt --stats
```

---

## Architecture

```
hints / config
     |
     v
hint_parser.py       <- plain language or JSON/YAML
     |
     v
rule_compiler.py     <- typed RuleSet + validation + conflict check
     |
     v
generator.py         <- itertools.product (fast) or backtracking (constrained)
     |
     v
mutation_pipeline.py <- composable str->str transforms
     |
     v
filter.py            <- post-mutation constraint pass
     |
     v
deduper.py           <- Bloom filter, O(1) memory
     |
     v
scorer.py            <- Shannon entropy + pattern classification
     |
     v
pipeline.py          <- multithreaded producer/worker/writer
     |
     v
io.py                <- txt / gz / csv / json / hc22000
```

---

## CLI Reference

```
Core:
  -c, --config PATH         JSON/YAML constraints file
  -o, --output PATH         Output file (default: wordlist.txt)
  -f, --format FORMAT       txt | gz | csv | json | hc22000

Generation:
  -l, --length INT          Exact length
  -m, --min-length INT      Min length
  -M, --max-length INT      Max length
  --charset CHARSET         digits | alpha | lower | upper | alnum | ascii | binary | custom
  --custom-chars STRING     Charset string (with --charset custom)
  --tier TIER               Wordlist: none | tiny | small | large | custom
  --wordlist PATH           Custom base wordlist
  --mutations PROFILE       none | standard | aggressive
  --max-expand INT          Max mutations per base (default: 50)
  --large                   Allow jobs > 100M candidates

Constraints:
  --no-consecutive SPEC     e.g. "0:3" = no '0' repeated 3+ times
  --max-repeats INT         Max times any single digit may appear
  --min-entropy FLOAT       Minimum Shannon entropy (bits)
  --no-keyboard-walks       Reject keyboard walk patterns

Breach Check:
  --breach-check            Flag via HIBP k-anonymity API
  --breach-local PATH       Local HIBP sorted hash file
  --exclude-breached        Remove breached candidates from output

Visualization (requires matplotlib):
  --viz-entropy PATH        Entropy histogram PNG
  --viz-keyboard PATH       Keyboard heatmap PNG
  --viz-patterns PATH       Pattern distribution PNG
  --viz-all DIR             Save all three charts to directory

Output:
  --sort-by FIELD           entropy | alpha | length | none
  --limit INT               Max candidates to emit
  --compress                Gzip output
  --no-header               Omit warning/metadata header
  --stats                   Print generation statistics

Misc:
  --threads INT             Worker threads (default: CPU count - 1)
  --preset NAME             numeric_7 | enterprise | ctf_binary
  --hints HINT [HINT ...]   Plain-language constraints
  --gui                     Launch Tkinter GUI
  --debug                   Verbose logging
```

---

## Constraint Config (JSON/YAML)

```json
{
  "charset": "digits",
  "length": 7,
  "no_consecutive": [{"char": "0", "count": 3}],
  "max_repeats": {"digits": 2},
  "position_rules": {
    "must_start_with_class": "letter",
    "must_not_start_with": ["0"]
  },
  "patterns": {
    "startswith": ["pass"],
    "endswith": ["123", "2025"],
    "regex_blacklist": ["^000", "(.+)\\1{2}"]
  },
  "keyboard_walk": {"reject_if_walk_ratio_above": 0.5},
  "entropy": {"min_bits": 30},
  "mutations": {
    "profile": "standard",
    "max_expansion": 50
  },
  "wordlist": {"tier": "small"},
  "output": {
    "format": "txt",
    "path": "wordlist.txt",
    "compress": false,
    "sort_by": "entropy",
    "max_candidates": null,
    "include_header": true
  }
}
```

---

## Mutation Profiles

| Profile | Mutations |
|---|---|
| `none` | Only the original base word |
| `standard` | capitalize, append_year, append_symbol, leet_swap, reverse, insert_digit, toggle_case |
| `aggressive` | All 12 mutations including double, l33t_full, prefix_bang, suffix_123 |

---

## Export Formats

| Format | Use case |
|---|---|
| `.txt` | Generic one-per-line, compatible with all tools |
| `.gz` | Compressed txt for large lists |
| `.csv` | candidate, entropy_bits, pattern_class columns |
| `.json` | Structured with metadata and per-candidate scores |
| `.hc22000` | Hashcat WPA2 PMKID wordlist format |

---

## Performance

| Mode | Speed |
|---|---|
| Raw generator (itertools fast path) | ~10M cands/sec |
| Backtracking (constrained) | ~800K cands/sec |
| Full pipeline (filter + dedup + I/O) | ~25K cands/sec |

**Fast path** activates automatically when no prefix-prunable constraints are set
(no `no_consecutive`, `max_repeats`, keyboard walk, or position rules).

Optional Numba JIT (`pip install numba`) accelerates the numeric filter hot loop.

---

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
python scripts/benchmark.py --length 6 --charset digits
```

### Project structure

```
pwgen/
  cli.py              CLI entry point (argparse)
  gui.py              Tkinter GUI
  hint_parser.py      Plain language -> constraint dict
  rule_compiler.py    Constraint dict -> validated RuleSet
  generator.py        Backtracking + itertools.product fast path
  filter.py           Constraint checking (passes_all)
  mutation_pipeline.py  12 composable str->str mutations
  seed_loader.py      Tiered wordlist loader
  deduper.py          Bloom filter deduplication
  scorer.py           Shannon entropy + pattern classifier
  pipeline.py         Multithreaded producer/worker/writer
  io.py               All output formats
  viz.py              matplotlib charts
  breach_check.py     HIBP k-anonymity API + local file
  jit.py              Optional Numba JIT acceleration
  logger.py           Rich + file logging
```

---

## Wordlists

Bundled: `tiny_1k.txt` (~55 common seeds).

For larger runs, download rockyou:
```
https://github.com/danielmiessler/SecLists/tree/master/Passwords/Leaked-Databases
```
Then: `pwgen --wordlist path/to/rockyou.txt --mutations aggressive --output out.txt`

---

## Ethical Use

This tool is intended for:
- Authorized penetration testing
- CTF competitions
- Security research with explicit permission

All output files carry a warning header. The tool does not store or transmit
any passwords beyond what is explicitly requested by the user.
