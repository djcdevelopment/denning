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


def decode_roofline():
    """The long-context decode cliff (results/E1-SUMMARY.md, H2')."""
    ctx = [0, 8, 16, 32, 64]                  # K tokens
    tps = [132.8, 74.3, 58.2, 38.0, 11.5]     # decode t/s

    fig, ax = plt.subplots(figsize=(7.6, 4.4), dpi=160)
    fig.subplots_adjust(left=0.1, right=0.96, top=0.83, bottom=0.14)
    ax.axvspan(40, 66, color=CORAL, alpha=0.06)
    ax.plot(ctx, tps, "-o", color=BLUE, lw=2.4, ms=7, zorder=3)
    ax.set_xlabel("context length (K tokens)", fontsize=10.5)
    ax.set_ylabel("decode throughput (t/s)", fontsize=10.5)
    ax.set_ylim(0, 148)
    ax.set_xlim(-2, 66)
    ax.grid(True, color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    for x, y in zip(ctx, tps):
        ax.annotate(f"{y:.0f}", (x, y), textcoords="offset points", xytext=(0, 9),
                    fontsize=8.5, color=BLUE, ha="center")
    ax.annotate("11.5× slower\nthan empty", xy=(64, 11.5), xytext=(49, 56),
                fontsize=9.5, color=CORAL, ha="center",
                arrowprops=dict(arrowstyle="->", color=CORAL, lw=1.2))
    fig.suptitle("Decode roofline: the long-context cliff", fontsize=13, y=0.95)
    ax.set_title("Qwen3-30B-A3B · one Arc Pro B70 · Vulkan · denning H2′",
                 fontsize=8.6, color=GREY, pad=8)
    out = os.path.join(HERE, "decode-roofline.png")
    fig.savefig(out, dpi=160, facecolor="white")
    plt.close(fig)
    print("wrote", out)


def i4b_admission_knee():
    """The N-session goodput knee (results/I4b-admission-knee-20260619.md)."""
    N = [6, 8, 10, 12]
    goodput = [6, 8, 0, 0]
    agg = [217, 229, 67.5, 78]
    labels = [str(n) for n in N]

    fig, ax1 = plt.subplots(figsize=(7.6, 4.4), dpi=160)
    fig.subplots_adjust(left=0.09, right=0.9, top=0.83, bottom=0.14)
    bars = ax1.bar(labels, goodput, color=BLUE, width=0.55, zorder=2,
                   label="sessions meeting SLO")
    ax1.set_xlabel("concurrent sessions (N)", fontsize=10.5)
    ax1.set_ylabel("goodput (sessions meeting SLO)", color=BLUE, fontsize=10.5)
    ax1.tick_params(axis="y", labelcolor=BLUE)
    ax1.set_ylim(0, 13)
    for b, g in zip(bars, goodput):
        ax1.annotate(str(g), (b.get_x() + b.get_width() / 2, g),
                     textcoords="offset points", xytext=(0, 4), ha="center",
                     fontsize=9, color=BLUE)
    ax2 = ax1.twinx()
    ax2.plot(labels, agg, "--D", color=CORAL, lw=2.2, ms=6, label="aggregate throughput")
    ax2.set_ylabel("aggregate decode (t/s)", color=CORAL, fontsize=10.5)
    ax2.tick_params(axis="y", labelcolor=CORAL)
    ax2.set_ylim(0, 260)
    ax1.annotate("N* = 8", xy=(1, 8), xytext=(1, 11.4), fontsize=11.5, color=BLUE, ha="center")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=9, frameon=False)
    fig.suptitle("Admission knee: over-admitting collapses goodput and throughput",
                 fontsize=11.5, y=0.95)
    ax1.set_title("N concurrent sessions · Qwen3-30B-A3B · Vulkan · denning I-4b",
                  fontsize=8.6, color=GREY, pad=8)
    out = os.path.join(HERE, "i4b-admission-knee.png")
    fig.savefig(out, dpi=160, facecolor="white")
    plt.close(fig)
    print("wrote", out)


def moe_vs_dense():
    """MoE vs dense decode/prefill (results/E1-moe-vs-dense-20260619.md)."""
    import numpy as np
    groups = ["prefill (pp512)", "decode (tg128)"]
    moe = [1500.6, 130.3]
    dense = [513.7, 23.0]
    x = np.arange(len(groups))
    w = 0.34

    fig, ax = plt.subplots(figsize=(7.0, 4.4), dpi=160)
    fig.subplots_adjust(left=0.12, right=0.96, top=0.83, bottom=0.11)
    b1 = ax.bar(x - w / 2, moe, w, color=BLUE, label="MoE — Qwen3-30B-A3B (3B active)")
    b2 = ax.bar(x + w / 2, dense, w, color=CORAL, label="dense — Qwen2.5-32B")
    ax.set_xticks(x)
    ax.set_xticklabels(groups, fontsize=10)
    ax.set_ylabel("throughput (t/s)", fontsize=10.5)
    ax.set_ylim(0, 1720)
    for bars in (b1, b2):
        for b in bars:
            ax.annotate(f"{b.get_height():.0f}",
                        (b.get_x() + b.get_width() / 2, b.get_height()),
                        textcoords="offset points", xytext=(0, 3), ha="center", fontsize=8.5)
    ax.annotate("5.7× faster decode", xy=(1 - w / 2, 130), xytext=(0.45, 720),
                fontsize=10, color=BLUE,
                arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.2))
    ax.legend(fontsize=9, frameon=False, loc="upper right")
    ax.grid(True, axis="y", color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    fig.suptitle("MoE streams fewer active params: 5.7× faster decode", fontsize=12, y=0.95)
    ax.set_title("equal ~32B total, Q4, one Arc Pro B70 · Vulkan · denning",
                 fontsize=8.6, color=GREY, pad=8)
    out = os.path.join(HERE, "moe-vs-dense.png")
    fig.savefig(out, dpi=160, facecolor="white")
    plt.close(fig)
    print("wrote", out)


def i4c_memory_knee():
    """The MEMORY-bound admission knee (results/I4c-memory-knee-20260619.md)."""
    hog = [0, 10, 12, 14, 16]
    goodput = [4, 4, 4, 0, 0]
    spill = [0.2, 0.2, 0.2, 1.07, 2.92]
    labels = [str(h) for h in hog]

    fig, ax1 = plt.subplots(figsize=(7.6, 4.4), dpi=160)
    fig.subplots_adjust(left=0.09, right=0.9, top=0.83, bottom=0.14)
    ax1.axvspan(2.5, 4.5, color=CORAL, alpha=0.06)
    bars = ax1.bar(labels, goodput, color=BLUE, width=0.55, zorder=2)
    ax1.set_xlabel("co-tenant VRAM held (GB)", fontsize=10.5)
    ax1.set_ylabel("goodput (sessions meeting SLO)", color=BLUE, fontsize=10.5)
    ax1.tick_params(axis="y", labelcolor=BLUE)
    ax1.set_ylim(0, 5)
    for b, g in zip(bars, goodput):
        ax1.annotate(str(g), (b.get_x() + b.get_width() / 2, g), textcoords="offset points",
                     xytext=(0, 4), ha="center", fontsize=9, color=BLUE)
    ax2 = ax1.twinx()
    ax2.plot(labels, spill, "--D", color=CORAL, lw=2.2, ms=6)
    ax2.set_ylabel("shared-memory spill (GB)", color=CORAL, fontsize=10.5)
    ax2.tick_params(axis="y", labelcolor=CORAL)
    ax2.set_ylim(0, 3.3)
    ax1.text(2.45, 4.85, "budget crossover ≈ 13 GB", fontsize=8.8, color=CORAL, ha="center", va="top")
    fig.suptitle("Memory-bound admission knee: a co-tenant forces the spill", fontsize=12, y=0.95)
    ax1.set_title("N=4 sessions, short ctx · footprint 18.3 GB · one Arc Pro B70 (31 GB) · denning I-4c",
                  fontsize=8.6, color=GREY, pad=8)
    out = os.path.join(HERE, "i4c-memory-knee.png")
    fig.savefig(out, dpi=160, facecolor="white")
    plt.close(fig)
    print("wrote", out)


def h4_lifetime_classes():
    """H4 simulation: lifetime classes vs LRU (results/H4-lifetime-sim-20260619.md)."""
    cap = [36, 40, 48, 56, 64, 72, 80, 96]
    on = [19.5, 75.3, 100, 100, 100, 100, 100, 100]
    lru = [0.0, 0.0, 0.0, 0.0, 2.4, 23.7, 67.3, 99.8]

    fig, ax = plt.subplots(figsize=(7.8, 4.5), dpi=160)
    fig.subplots_adjust(left=0.1, right=0.96, top=0.83, bottom=0.14)
    ax.axvspan(34, 92, color=CORAL, alpha=0.05)
    ax.fill_between(cap, lru, on, color=BLUE, alpha=0.08, zorder=1)
    ax.plot(cap, on, "-o", color=BLUE, lw=2.4, ms=6, label="classes-ON (lifetime-class)", zorder=3)
    ax.plot(cap, lru, "--s", color=CORAL, lw=2.2, ms=6, label="LRU / TTL (recency)", zorder=3)
    ax.set_xlabel("arena capacity (KV units)  —  smaller = more overload", fontsize=10.5)
    ax.set_ylabel("high-reuse block hit rate (%)", fontsize=10.5)
    ax.set_ylim(-3, 108)
    ax.set_xlim(34, 97)
    ax.grid(True, color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    ax.text(54, 52, "H4 advantage\n(overload + reuse)", fontsize=9.5, color=BLUE, ha="center")
    ax.annotate("working set fits\n(policy irrelevant)", xy=(96, 100), xytext=(86, 36),
                fontsize=8.3, color=GREY, ha="center",
                arrowprops=dict(arrowstyle="->", color=GREY, lw=1))
    ax.legend(fontsize=9, frameon=False, loc="center right")
    fig.suptitle("H4 (simulation): lifetime classes protect reuse; LRU thrashes it",
                 fontsize=11.5, y=0.95)
    ax.set_title("8 agent sessions w/ shared prefixes · 60 reps · denning H4 SIM (not on-rig)",
                 fontsize=8.6, color=GREY, pad=8)
    out = os.path.join(HERE, "h4-lifetime-classes.png")
    fig.savefig(out, dpi=160, facecolor="white")
    plt.close(fig)
    print("wrote", out)


def h4_onrig():
    """H4 on-rig: lifetime-class vs LRU per-seed goodput (results/H4-arena-onrig-20260619.md)."""
    import numpy as np
    classes = [18, 18, 16, 19, 17, 18, 12, 6, 12, 14]
    lru = [12, 14, 12, 14, 10, 16, 9, 6, 10, 10]
    x = np.arange(10)
    w = 0.4

    fig, ax = plt.subplots(figsize=(8.0, 4.4), dpi=160)
    fig.subplots_adjust(left=0.09, right=0.96, top=0.82, bottom=0.13)
    ax.bar(x - w / 2, classes, w, color=BLUE, label="classes-ON (lifetime-class)")
    ax.bar(x + w / 2, lru, w, color=CORAL, label="LRU (recency)")
    ax.set_xticks(x)
    ax.set_xticklabels([str(s) for s in range(10)])
    ax.set_xlabel("workload seed", fontsize=10.5)
    ax.set_ylabel("goodput (turns meeting TTFT SLO, /40)", fontsize=10.5)
    ax.set_ylim(0, 22)
    ax.legend(fontsize=9, frameon=False, loc="upper right")
    ax.grid(True, axis="y", color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    fig.suptitle("H4 on-rig: lifetime-class eviction beats LRU on real inference (10/10 seeds, +32%)",
                 fontsize=11, y=0.95)
    ax.set_title("6 hot sessions + cold scan, 4 KV slots · cache miss = ~2.8 s real re-prefill · denning H4",
                 fontsize=8.6, color=GREY, pad=8)
    out = os.path.join(HERE, "h4-onrig.png")
    fig.savefig(out, dpi=160, facecolor="white")
    plt.close(fig)
    print("wrote", out)


def h4_blockgrained():
    """H4 block-grained, real costs: classes vs LRU vs TTL (results/H4-blockgrained-20260619.md)."""
    cap = [16, 18, 20, 22, 24, 26, 28, 32]
    classes = [0, 0, 43.0, 63.6, 64.4, 70.7, 89.0, 95.0]
    lru = [0, 0, 0, 0, 0.7, 15.2, 54.4, 94.1]
    ttl = [0, 0, 0, 0, 0.7, 15.2, 54.4, 94.1]

    fig, ax = plt.subplots(figsize=(7.8, 4.5), dpi=160)
    fig.subplots_adjust(left=0.1, right=0.96, top=0.83, bottom=0.14)
    ax.axvspan(15, 30, color=CORAL, alpha=0.05)
    ax.fill_between(cap, lru, classes, color=BLUE, alpha=0.08)
    ax.plot(cap, classes, "-o", color=BLUE, lw=2.4, ms=6, label="classes (typed lifetime)")
    ax.plot(cap, lru, "--s", color=CORAL, lw=2.2, ms=6, label="LRU (recency)")
    ax.plot(cap, ttl, ":", color=GREY, lw=2.6, label="TTL (time-window) ≡ LRU")
    ax.set_xlabel("arena capacity (K tokens)  —  smaller = more overload", fontsize=10.5)
    ax.set_ylabel("goodput-under-SLO (%)", fontsize=10.5)
    ax.set_ylim(-3, 103)
    ax.set_xlim(15.5, 32.5)
    ax.grid(True, color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    ax.text(23.5, 40, "typed-class\nadvantage", fontsize=9.5, color=BLUE, ha="center")
    ax.legend(fontsize=9, frameon=False, loc="upper left")
    fig.suptitle("H4 block-grained (real costs): typed classes beat LRU and TTL", fontsize=11.5, y=0.95)
    ax.set_title("SYSTEM/DOC/TURN blocks · miss priced at 0.94 ms/token (measured) · denning H4",
                 fontsize=8.6, color=GREY, pad=8)
    out = os.path.join(HERE, "h4-blockgrained.png")
    fig.savefig(out, dpi=160, facecolor="white")
    plt.close(fig)
    print("wrote", out)


def s1_swap():
    """S1: swap (refetch) vs re-prefill (recompute) goodput (results/S1-swap-arena-20260619.md)."""
    import numpy as np
    off = [18, 18, 16]
    on = [23, 24, 22]
    x = np.arange(3)
    w = 0.38

    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=160)
    fig.subplots_adjust(left=0.1, right=0.96, top=0.82, bottom=0.12)
    b1 = ax.bar(x - w / 2, off, w, color=CORAL, label="re-prefill on miss (recompute, ~2.4 s)")
    b2 = ax.bar(x + w / 2, on, w, color=BLUE, label="swap/restore on miss (refetch, ~84 ms)")
    ax.set_xticks(x)
    ax.set_xticklabels([f"seed {s}" for s in range(3)])
    ax.set_ylabel("goodput (turns meeting TTFT SLO, /40)", fontsize=10.5)
    ax.set_ylim(0, 31)
    for bars in (b1, b2):
        for b in bars:
            ax.annotate(str(int(b.get_height())), (b.get_x() + b.get_width() / 2, b.get_height()),
                        textcoords="offset points", xytext=(0, 3), ha="center", fontsize=9)
    ax.legend(fontsize=9, frameon=False, loc="upper center")
    ax.grid(True, axis="y", color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    fig.suptitle("S1 swap: refetch-on-miss (84 ms) beats re-prefill (2.4 s) — +33% goodput",
                 fontsize=11, y=0.95)
    ax.set_title("a cache miss restored from disk vs recomputed · R1 on real KV ≈ 29× · denning S1",
                 fontsize=8.6, color=GREY, pad=8)
    out = os.path.join(HERE, "h4-swap.png")
    fig.savefig(out, dpi=160, facecolor="white")
    plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    h1_demotion_cliff()
    decode_roofline()
    i4b_admission_knee()
    moe_vs_dense()
    i4c_memory_knee()
    h4_lifetime_classes()
    h4_onrig()
    h4_blockgrained()
    s1_swap()
