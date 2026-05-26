"""
Visualization module — requires matplotlib (and optionally seaborn).

Available charts:
  plot_entropy_histogram  — Shannon entropy distribution across candidates
  plot_keyboard_heatmap   — Character frequency mapped to keyboard layout
  plot_pattern_distribution — Bar chart of pattern class counts
  plot_all                — Save all three to a directory
"""
from __future__ import annotations
import math
import os
from collections import Counter
from typing import Iterable

# Lazy imports — only fail at call-time if matplotlib missing
_mpl_err: Exception | None = None
try:
    import matplotlib
    matplotlib.use("Agg")   # non-interactive backend (safe in CLI/GUI)
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
except ImportError as e:
    _mpl_err = e

_snb_err: Exception | None = None
try:
    import seaborn as sns
except ImportError as e:
    _snb_err = e


def _require_mpl() -> None:
    if _mpl_err:
        raise ImportError(
            "matplotlib is required for visualizations. "
            "Install with: pip install matplotlib"
        ) from _mpl_err


# ---------------------------------------------------------------------------
# Keyboard layout
# ---------------------------------------------------------------------------

# Row, Col positions for each key (0-indexed, row 0 = number row)
KEYBOARD_POS: dict[str, tuple[int, int]] = {}

_ROWS = [
    "1234567890-=",
    "qwertyuiop[]",
    "asdfghjkl;'",
    "zxcvbnm,./",
]
for _r, _row in enumerate(_ROWS):
    for _c, _ch in enumerate(_row):
        KEYBOARD_POS[_ch] = (_r, _c)
        KEYBOARD_POS[_ch.upper()] = (_r, _c)

# Digit row mapped separately (digits are on row 0)
for _i, _d in enumerate("1234567890"):
    KEYBOARD_POS[_d] = (0, _i)


def _make_heatmap_grid(candidates: list[str]) -> tuple:
    """Return (grid 4×12, col_labels, row_labels) for keyboard heatmap."""
    import numpy as np
    freq: Counter = Counter()
    for pw in candidates:
        freq.update(pw.lower())

    grid = np.zeros((4, 12), dtype=float)
    for ch, count in freq.items():
        if ch in KEYBOARD_POS:
            r, c = KEYBOARD_POS[ch]
            if r < 4 and c < 12:
                grid[r, c] += count

    row_labels = ["1–0", "Q–P", "A–'", "Z–/"]
    return grid, row_labels


# ---------------------------------------------------------------------------
# 1. Entropy histogram
# ---------------------------------------------------------------------------

def plot_entropy_histogram(
    candidates: list[str],
    output_path: str,
    *,
    threshold_bits: float | None = None,
    title: str = "Candidate Entropy Distribution",
) -> str:
    """Save a Shannon entropy histogram PNG to output_path."""
    _require_mpl()

    from .filter import shannon_bits

    scores = [shannon_bits(pw) for pw in candidates]
    if not scores:
        raise ValueError("No candidates to plot.")

    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor("#1e1e2e")
    ax.set_facecolor("#11111b")

    n, bins, patches = ax.hist(scores, bins=40, color="#89b4fa", edgecolor="#313244")

    if threshold_bits is not None:
        ax.axvline(x=threshold_bits, color="#f38ba8", linestyle="--", linewidth=1.5,
                   label=f"{threshold_bits}-bit threshold")
        ax.legend(facecolor="#313244", edgecolor="#45475a", labelcolor="#cdd6f4")

    ax.set_xlabel("Shannon Entropy (bits)", color="#cdd6f4")
    ax.set_ylabel("Count", color="#cdd6f4")
    ax.set_title(title, color="#cdd6f4", pad=10)
    ax.tick_params(colors="#cdd6f4")
    for spine in ax.spines.values():
        spine.set_edgecolor("#45475a")

    # Annotation
    mean_e = sum(scores) / len(scores)
    ax.axvline(x=mean_e, color="#a6e3a1", linestyle=":", linewidth=1.2,
               label=f"mean {mean_e:.2f} bits")
    ax.legend(facecolor="#313244", edgecolor="#45475a", labelcolor="#cdd6f4")

    plt.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


# ---------------------------------------------------------------------------
# 2. Keyboard heatmap
# ---------------------------------------------------------------------------

def plot_keyboard_heatmap(
    candidates: list[str],
    output_path: str,
    *,
    title: str = "Character Frequency Heatmap",
) -> str:
    """Save a keyboard-layout heatmap PNG to output_path."""
    _require_mpl()
    import numpy as np

    grid, row_labels = _make_heatmap_grid(candidates)

    fig, ax = plt.subplots(figsize=(12, 4))
    fig.patch.set_facecolor("#1e1e2e")
    ax.set_facecolor("#11111b")

    col_labels = [str(i) for i in range(12)]

    # Use seaborn if available, else plain imshow
    if _snb_err is None:
        import seaborn as sns
        sns.heatmap(
            grid, ax=ax,
            cmap="Blues",
            xticklabels=col_labels,
            yticklabels=row_labels,
            linewidths=0.5,
            linecolor="#313244",
            annot=False,
            cbar_kws={"shrink": 0.8},
        )
    else:
        im = ax.imshow(grid, cmap="Blues", aspect="auto")
        plt.colorbar(im, ax=ax, shrink=0.8)
        ax.set_xticks(range(12))
        ax.set_xticklabels(col_labels)
        ax.set_yticks(range(4))
        ax.set_yticklabels(row_labels)

    ax.set_title(title, color="#cdd6f4", pad=10)
    ax.tick_params(colors="#cdd6f4")
    for spine in ax.spines.values():
        spine.set_edgecolor("#45475a")

    plt.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


# ---------------------------------------------------------------------------
# 3. Pattern distribution bar chart
# ---------------------------------------------------------------------------

def plot_pattern_distribution(
    candidates: list[str],
    output_path: str,
    *,
    title: str = "Pattern Class Distribution",
) -> str:
    """Save a bar chart of pattern classes to output_path."""
    _require_mpl()

    from .scorer import classify

    counts: Counter = Counter(classify(pw) for pw in candidates)
    classes = sorted(counts, key=lambda k: -counts[k])
    values  = [counts[c] for c in classes]
    colors  = [
        "#89b4fa", "#a6e3a1", "#f9e2af", "#fab387",
        "#f38ba8", "#cba6f7", "#94e2d5", "#eba0ac",
    ]

    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor("#1e1e2e")
    ax.set_facecolor("#11111b")

    bars = ax.bar(classes, values, color=colors[:len(classes)], edgecolor="#313244")
    ax.bar_label(bars, labels=[f"{v:,}" for v in values],
                 color="#cdd6f4", fontsize=9, padding=3)

    total = sum(values)
    ax.set_xlabel("Pattern Class", color="#cdd6f4")
    ax.set_ylabel("Count", color="#cdd6f4")
    ax.set_title(f"{title}  (total {total:,})", color="#cdd6f4", pad=10)
    ax.tick_params(colors="#cdd6f4")
    for spine in ax.spines.values():
        spine.set_edgecolor("#45475a")

    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


# ---------------------------------------------------------------------------
# 4. Convenience: save all three
# ---------------------------------------------------------------------------

def plot_all(
    candidates: list[str],
    output_dir: str,
    *,
    entropy_threshold: float | None = None,
) -> dict[str, str]:
    """Save all three charts into output_dir. Returns {chart_name: path}."""
    os.makedirs(output_dir, exist_ok=True)
    results = {}
    results["entropy"]  = plot_entropy_histogram(
        candidates,
        os.path.join(output_dir, "entropy.png"),
        threshold_bits=entropy_threshold,
    )
    results["keyboard"] = plot_keyboard_heatmap(
        candidates,
        os.path.join(output_dir, "keyboard.png"),
    )
    results["patterns"] = plot_pattern_distribution(
        candidates,
        os.path.join(output_dir, "patterns.png"),
    )
    return results
