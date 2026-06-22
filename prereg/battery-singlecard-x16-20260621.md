# Pre-registration — Single-card B70 @ PCIe x16 battery (2026-06-21, afternoon)

Rig change since the morning dual-card battery: pulled the 2nd B70 and the RTX 2070 Super
for airflow (machine too hot to game during the day). One B70 remains, now in the primary
slot and **also driving the 4K display**. The engine enumerates exactly one device —
`Vulkan0: Intel(R) Arc(TM) Pro B70 Graphics (32630 MiB free 31861)`. The old
"never serve device 0" rule was 2070-specific and is now moot: **Vulkan0 IS the B70.**

Usable VRAM ceiling: 32630 MiB total, ~0.9 GiB consumed by the 4K desktop at idle → ~31 GiB
for model + KV. C: 91 GiB free. Watchdog thresholds 65/20 (disk), 30/31/31.6 (phys).

Safety note for this config: the serving card is the display card, so a GPU wedge freezes the
monitor. Avoid the known wedge condition (flash-attn OFF at high depth, per D1). Keep FA on
for depth work.

This file is git-tagged BEFORE any data is collected. A refuted prediction is a successful
measurement, not a failure.

## Predictions

**P1 — Prefill is unchanged by x16.** Prefill throughput at matched depths lands within ±10%
of the morning x8 numbers (pp512 ≈ 2016 t/s; f16 depth pp 2014 → 69.6 @ 0 → 64k). Prefill is
compute-bound once weights are resident; PCIe width affects load, not steady prefill.
REFUTE if x16 shows >15% prefill gain.

**P2 — Model load is disk-bound, not PCIe-bound.** Cold-load wall-clock scales ~linearly with
file size at the D: NVMe sequential-read rate (~3-3.5 GB/s), so Qwen3-30B-A3B (17.3 GiB) cold-
loads in ~6-9 s. x16 buys =<10% vs x8 because the disk read dominates the transfer.
REFUTE if effective load rate > 6 GB/s, or load is dominated by GPU-upload/driver time.

**P3 — Model rotation is cheap-ish but RAM-bounded (vllama).** A warm-cache reload (same model
loaded a second time) is faster than cold but NOT free: 32 GiB host RAM cannot fully cache a
17 GiB model plus the working set, so warm reload is ~30-70% of cold, not ~0. A full A->B->A
rotation costs ~2-3x a single cold load.
REFUTE if warm reload is approx instant (RAM fully caches -> contradicts the RAM<VRAM inversion)
or if there is no warm speedup at all.

**P4 — denning's restore keystone survives the display-shared single card.** Restore-vs-
reprefill stays >=50x at 16k/32k/64k (morning: 114-219x), denning admission subtracts the
~0.9 GiB display overhead from the live budget, and display compositor contention adds <10%
jitter to restore latency.
REFUTE if the restore advantage falls below ~20x or admission ignores display overhead and OOMs.

**P5 — vLLM does not run on native Windows/Arc.** No XPU wheel for Windows; install or runtime
fails without WSL/Linux. The realistic Windows/Arc engine set is llama.cpp Vulkan (+ IPEX-LLM).
The real vLLM baseline belongs on the Linux box now being set up.
REFUTE if vLLM installs and serves the model on native Windows/Arc.

**P6 (optional, last) — A too-big model triggers WDDM spill.** Llama-3.3-70B-Q4 (~40 GiB > ~31
GiB usable) pins dedicated usage near the cap while Shared GPU Memory climbs into system RAM,
and decode collapses to <2 t/s (PCIe-bound spill) — the model-side spill we couldn't trigger
with a single KV stream =<128k in the morning.
REFUTE if the 70B OOM-fails cleanly (no shared spill) or runs at usable speed.
