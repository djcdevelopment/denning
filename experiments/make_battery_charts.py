#!/usr/bin/env python3
"""Generate the thermal-window battery figures (2026-06-21) into figures/.
Data is the committed summary from results/battery-thermal-window-20260621.md."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import os

FIG = r"D:\work\denning\figures"
os.makedirs(FIG, exist_ok=True)
RED, BLUE, GREEN, GREY = "#c0392b", "#2980b9", "#27ae60", "#7f8c8d"


# 1 — decode cliff (tg vs depth, f16 + q8)
f16 = ([0, 4, 8, 16, 32, 48, 64], [119.6, 50.7, 32.7, 19.0, 10.4, 7.1, 5.43])
q8 = ([0, 4, 8, 16, 32, 64, 96, 128], [103.7, 45.6, 29.4, 17.2, 9.38, 4.92, 3.33, 2.52])
fig, ax = plt.subplots(figsize=(7.2, 4.6))
ax.plot(f16[0], f16[1], "o-", color=RED, label="f16 KV")
ax.plot(q8[0], q8[1], "s-", color=BLUE, label="q8 KV")
ax.set_yscale("log"); ax.set_xlabel("context depth (k tokens)"); ax.set_ylabel("decode (tg128), t/s  [log]")
ax.set_title("Decode cliff — Qwen3-30B-A3B Q4, single B70, FA on\n119 -> 5.4 t/s by 64k (22x); ~3x of the steepness is the Vulkan FA kernel (D1)")
ax.axhline(20, color=GREY, ls=":", lw=1); ax.text(70, 21, "20 t/s = 50ms TPOT SLO", color=GREY, fontsize=8)
ax.grid(True, which="both", alpha=0.3); ax.legend()
fig.tight_layout(); fig.savefig(f"{FIG}/battery-decode-cliff.png", dpi=130); plt.close(fig)


# 2 — restore vs cold re-prefill (the keystone)
labels = ["16k", "32k", "64k"]
cold = [37236.6, 142808.8, 558859.3]
restore = [325.1, 651.1, 3846.4]
speed = [114, 219, 145]
x = np.arange(3); w = 0.38
fig, ax = plt.subplots(figsize=(7.2, 4.6))
ax.bar(x - w / 2, cold, w, color=RED, label="cold re-prefill")
ax.bar(x + w / 2, restore, w, color=GREEN, label="host-KV restore")
ax.set_yscale("log"); ax.set_xticks(x); ax.set_xticklabels(labels)
ax.set_xlabel("context depth"); ax.set_ylabel("time to first token (ms)  [log]")
ax.set_title("The keystone: restore vs cold re-prefill at depth\n64k = 9.3 min rebuild vs 3.85 s restore")
for i, s in enumerate(speed):
    ax.text(i, max(cold[i], restore[i]) * 1.4, f"{s}x", ha="center", fontweight="bold", fontsize=12)
ax.grid(True, axis="y", which="both", alpha=0.3); ax.legend()
fig.tight_layout(); fig.savefig(f"{FIG}/battery-restore-vs-reprefill.png", dpi=130); plt.close(fig)


# 3 — flash-attn prefill/decode tradeoff (D1)
groups = ["pp512 @16k\n(prefill)", "tg128 @16k\n(decode)"]
fa_on = [254, 19.0]
fa_off = [28.9, 56.4]
x = np.arange(2); w = 0.38
fig, ax = plt.subplots(figsize=(7.2, 4.6))
ax.bar(x - w / 2, fa_on, w, color=BLUE, label="FA on")
ax.bar(x + w / 2, fa_off, w, color=RED, label="FA off")
ax.set_xticks(x); ax.set_xticklabels(groups); ax.set_ylabel("t/s")
ax.set_title("Flash-attn is a prefill accelerator that savages decode (16k, f16)\nFA on: 8.8x faster prefill, but 3x SLOWER decode  (FA off wedges the GPU at 64k)")
for i, (a, b) in enumerate(zip(fa_on, fa_off)):
    ax.text(i - w / 2, a, f"{a:g}", ha="center", va="bottom", fontsize=9)
    ax.text(i + w / 2, b, f"{b:g}", ha="center", va="bottom", fontsize=9)
ax.grid(True, axis="y", alpha=0.3); ax.legend()
fig.tight_layout(); fig.savefig(f"{FIG}/battery-flash-attn-tradeoff.png", dpi=130); plt.close(fig)


# 4 — spill probe (dedicated vs shared vs depth)
d = [64, 80, 96, 112, 128]
ded = [23.6, 25.11, 26.62, 28.17, 29.72]
shr = [0.14, 0.17, 0.20, 0.23, 0.26]
fig, ax = plt.subplots(figsize=(7.2, 4.6))
ax.plot(d, ded, "o-", color=BLUE, label="Dedicated VRAM (GB)")
ax.plot(d, shr, "s-", color=RED, label="Shared / system RAM (GB)")
ax.axhline(32, color=GREY, ls="--", lw=1.2); ax.text(64, 32.3, "32 GB dedicated cap", color=GREY, fontsize=9)
ax.set_ylim(0, 34); ax.set_xlabel("f16 context depth (k tokens)"); ax.set_ylabel("GB")
ax.set_title("WDDM spill probe: f16 KV fits to 128k in VRAM, no demotion\nDedicated grows ~96 KB/tok to 29.7 GB; Shared stays at ~0.2 GB baseline")
ax.grid(True, alpha=0.3); ax.legend()
fig.tight_layout(); fig.savefig(f"{FIG}/battery-spill-probe.png", dpi=130); plt.close(fig)

print("wrote 4 figures to", FIG)
