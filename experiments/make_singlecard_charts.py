#!/usr/bin/env python3
"""Charts for the single-card B70 @ x16 battery (Rows 2/2b load, Row 4 restore).

Reads results/raw/modelload-x16-20260622.csv and results/raw/battery-C1.json,
writes two PNGs to figures/.
"""
import csv
import json
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAW = r"D:\work\denning\results\raw"
FIG = r"D:\work\denning\figures"
os.makedirs(FIG, exist_ok=True)


def short(name: str) -> str:
    n = name.lower()
    if "14b" in n:
        return "14B\n8.4G"
    if "mistral" in n:
        return "Mistral-24B\n13.4G"
    if "qwen3-30b" in n:
        return "Qwen3-30B\nMoE 17.3G"
    if "32b-instruct-q4" in n:
        return "32B-q4\n18.5G"
    if "coder" in n:
        return "coder-32B\n21.7G"
    if "q6" in n:
        return "32B-q6\n25.0G"
    return name[:10]


# ---- Chart 1: model load cold vs warm (the ~22 GiB host-RAM knee) ----
rows = []
with open(os.path.join(RAW, "modelload-x16-20260622.csv")) as f:
    for r in csv.DictReader(f):
        rows.append(r)

labels = [short(r["model"]) for r in rows]
cold = [float(r["cold_s"]) for r in rows]
warm = [float(r["warm_s"]) for r in rows]
x = np.arange(len(rows))
w = 0.38

fig, ax = plt.subplots(figsize=(10, 5.5))
ax.bar(x - w / 2, cold, w, label="cold load (disk)", color="#c0504d")
ax.bar(x + w / 2, warm, w, label="warm reload (cached)", color="#4f81bd")
ax.set_ylabel("load time (s)")
ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=8)
ax.set_title("Model load: cold vs warm (no-mmap) -- the ~22 GiB host-RAM knee")
ax.axvline(3.5, ls="--", color="gray", alpha=0.6)
ax.text(3.55, max(cold) * 0.72, "fits cache | exceeds cache\n(warm INVERTS, thrash)",
        fontsize=8, color="dimgray")
ax.legend()
fig.tight_layout()
p1 = os.path.join(FIG, "singlecard-modelload.png")
fig.savefig(p1, dpi=110)
plt.close(fig)

# ---- Chart 2: denning restore vs re-prefill (Row 4) ----
with open(os.path.join(RAW, "battery-C1.json")) as f:
    c1 = json.load(f)

depths = [f'{r["target_depth"] // 1024}k' for r in c1]
cold_ms = [r["cold_reprefill_ttft_ms"] for r in c1]
rest_ms = [r["restore_total_ms"] for r in c1]
sp = [r["speedup_x"] for r in c1]
x = np.arange(len(c1))

fig, ax = plt.subplots(figsize=(9, 5.5))
ax.bar(x - w / 2, cold_ms, w, label="cold re-prefill TTFT", color="#c0504d")
ax.bar(x + w / 2, rest_ms, w, label="denning restore TTFT", color="#4f81bd")
ax.set_yscale("log")
ax.set_ylabel("TTFT (ms, log scale)")
ax.set_xticks(x)
ax.set_xticklabels(depths)
ax.set_xlabel("context depth")
ax.set_title("denning: restore vs re-prefill (headless B70 @ x16)")
for i, s in enumerate(sp):
    ax.text(x[i], max(cold_ms[i], rest_ms[i]) * 1.15, f"{s:.0f}x",
            ha="center", fontsize=10, fontweight="bold")
ax.legend()
fig.tight_layout()
p2 = os.path.join(FIG, "singlecard-restore-vs-reprefill.png")
fig.savefig(p2, dpi=110)
plt.close(fig)

print("charts written:")
print(" ", p1)
print(" ", p2)
