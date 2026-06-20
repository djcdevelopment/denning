#!/usr/bin/env python3
r"""Generate denning result figures (committed PNGs for the README + paper).

Reproducible: regenerates from the measured constants below (sourced from the
results/ docs). Run:
  D:\work\denning\.venv\Scripts\python.exe figures\make_figures.py
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
BLUE, CORAL, GREY = "#185FA5", "#D85A30", "#888888"


def h1_demotion_cliff():
    """The headline figure: H1 resident hog sweep (results/H1-resident-sweep-20260619.md)."""
    hog = [0, 10, 12, 14, 16, 18]                       # co-tenant VRAM held (GB)
    decode = [117.8, 117.6, 117.4, 27.2, 23.1, 19.4]    # baseline x measured decode-ratio
    spill = [0.0, 0.22, 0.24, 0.24, 2.70, 4.87]         # non_local committed (GB)

    fig, ax1 = plt.subplots(figsize=(8.4, 4.7), dpi=160)
    fig.subplots_adjust(left=0.085, right=0.9, top=0.82, bottom=0.14)

    ax1.axvspan(13.2, 18.7, color=CORAL, alpha=0.06)
    ax1.axvline(13.2, color=CORAL, ls=":", lw=1.3, alpha=0.75)

    ax1.plot(hog, decode, "-o", color=BLUE, lw=2.4, ms=6.5, label="decode throughput", zorder=3)
    ax1.set_xlabel("co-tenant VRAM held (GB)  —  oversubscription →", fontsize=10.5)
    ax1.set_ylabel("decode throughput (t/s)", color=BLUE, fontsize=10.5)
    ax1.tick_params(axis="y", labelcolor=BLUE)
    ax1.set_ylim(0, 130)
    ax1.set_xlim(-0.6, 18.7)
    ax1.grid(True, axis="y", color="#dddddd", lw=0.6)
    ax1.set_axisbelow(True)

    ax2 = ax1.twinx()
    ax2.plot(hog, spill, "--D", color=CORAL, lw=2.2, ms=6, label="shared-memory spill", zorder=3)
    ax2.set_ylabel("shared-memory spill (GB)", color=CORAL, fontsize=10.5)
    ax2.tick_params(axis="y", labelcolor=CORAL)
    ax2.set_ylim(0, 6)

    ax1.annotate("5× collapse", xy=(14, 27.2), xytext=(15.0, 66),
                 fontsize=10, color=BLUE,
                 arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.2))
    ax1.text(13.0, 126, "VRAM budget crossover ≈ 13 GB", fontsize=8.8, color=CORAL,
             va="top", ha="right")

    l1, a1 = ax1.get_legend_handles_labels()
    l2, a2 = ax2.get_legend_handles_labels()
    ax1.legend(l1 + l2, a1 + a2, loc="center left", bbox_to_anchor=(0.02, 0.46),
               fontsize=9.5, frameon=False)

    fig.suptitle("VidMm evicts a fitting model under a co-tenant: the demotion cliff",
                 fontsize=13, x=0.5, y=0.95)
    ax1.set_title("Qwen3-30B-A3B (17.9 GB resident) on one Arc Pro B70 (31 GB budget) · "
                  "Vulkan · denning H1 (reproduced ×2)", fontsize=8.6, color=GREY, pad=8)

    out = os.path.join(HERE, "h1-demotion-cliff.png")
    fig.savefig(out, dpi=160, facecolor="white")
    plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    h1_demotion_cliff()
