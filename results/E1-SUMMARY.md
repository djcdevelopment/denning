# E1 + H2′ — Empirical Summary (2026-06-19)

*Consolidated results from the on-rig validation run (single session; torch-xpu 2.12.1+xpu + prebuilt llama.cpp Vulkan b9279; dual Arc Pro B70, driver 32.0.101.8826). The cost model's core (R1–R3) and the admission thesis (H2′ roofline) are **empirically confirmed**. Per-result docs + JSON recordings are alongside; this is the narrative + figure-set for the HotOS position paper.*

## Headline
On a real fabric-less, FLOP-modest dual-B70 box, **every load-bearing prediction of the cost model held.** The central physics bet — *spend compute/compression to beat the scarce bus, and admission-control to stay snappy* — is **measured, not hypothesized.** Integrity: every prediction (cost-model R1–R3) was committed to git (`1118d0c`) **before** the data confirming it; run by Claude under operator authorization; nothing fabricated; caches kept off C:; predictions **not** tagged as the operator's.

## Rig (measured)
2× Arc Pro B70 · per-card **31.87 GiB** VRAM / **31.12 GiB** DXGI budget / 15.96 GiB shared ("48 GB" = sum; pooled dedicated **63.7 GiB**) · 32 GB system RAM · PCIe x8 · driver **32.0.101.8826** · Vulkan 1.4.348 · `VK_EXT_pageable_device_local_memory` present.

## R1 — recompute vs refetch ✅
`R_prefill` = **1500 t/s** → recompute 667 µs/tok vs refetch 3.8 µs/tok → **refetch ~176× cheaper.** Recompute is a *capacity* tool, not bus-saving.

## R2 — compression-over-the-bus (the linchpin) ✅✅
B_pcie **13.9 GB/s** (matches x8); B_dq isolated 168/94 (int8/int4). Threshold `B_pcie·r/(r−1)` = 27.8 (FP8) / 18.5 (INT4).
| co-tenant on the card | B_dq (int8/int4) | R2 verdict |
|---|---|---|
| isolated | 168 / 94 | **WINS 6–8×** |
| **real decode** (single stream) | 169 / 94 | **WINS 6–8×** |
| synthetic saturation (matmul) | 48 / 41 | **WINS 1.7–2.2×** |
Compression wins across the whole contention spectrum; the penalty is **co-tenant-duty-cycle-dependent** (real single-stream decode barely contends; a saturated GPU is the pessimistic bound).

## R3 — card→card ✅
**6.48 GB/s ≈ 0.47× host→VRAM** (host-bounced; no P2P on Windows). Asymmetric feed only pays if Card 1 *computes*.

## H2′ — decode roofline + cliff (Qwen3-30B-A3B, Vulkan) ✅
| ctx | decode t/s | vs empty |
|---|---|---|
| 0 | 132.8 | 1.00× |
| 8K | 74.3 | 0.56× |
| 16K | 58.2 | 0.44× |
| 32K | 38.0 | 0.29× |
| 64K | **11.5** | **0.087×** |
~Linear to 32K, then a **superlinear cliff** (64K = 11.5× slower than empty; the Vulkan attention-kernel cliff). Admission keeps sessions left of it. **q8-KV finding (prediction corrected):** q8 KV is **2–4× SLOWER** at depth, not faster — isolated to the **flash-attention kernel** (f16+FA ≈ q8+FA, both ~4× slower than f16-no-FA). On Vulkan/Arc **FA is a pessimization** and quantized KV (which forces FA) is a trap; the default attention path wins. Kernel + engine is a first-class variable. (See `E1-q8kv-roofline`.)

## H2′ — N-session admission scaling ✅
Aggregate decode **60.9 → 80.6 → 97.4 → 109.9 t/s** @ parallel 1/2/4/8 (still rising at 8 → `N*` > 8 at small ctx); prefill plateaus ~B=4. `N* = min(bandwidth, commit)`, shrinks as context grows.

## Architecture axis — MoE vs dense ✅
At equal ~32B total / Q4 / single card: **MoE (3B active) decodes 5.7× faster than dense 32B** (130 vs 23 t/s), prefills 2.9× faster — decode streams active params, so MoE is the bandwidth-efficient architecture here. Empirically validates the MoE choice for this hardware.

## Kernel/engine axis — flash attention is a pessimization on Vulkan/Arc ✅ (surprising)
`-fa` (required for quantized KV) is **~4× slower than default attention at depth** (f16+FA ≈ q8+FA ≈ 10 t/s @32K vs f16-no-FA 38). So q8 KV is a *capacity-vs-speed trap* on this stack, and **kernel + engine is a first-class variable** (a corrected prediction → a real finding).

## Status vs roadmap
**I-2 / E1 substantially DONE** (R1/R2/R3 + roofline + N-session measured on-rig). Remaining E1 refinements: q8-KV roofline (in flight), dequant-under-N-decode, copy-engine scheduling sweep, SYCL-vs-Vulkan cliff (needs ollama/ipex-llm harness), llama.cpp-matched dequant kernel. **Caveats:** dequant is a torch proxy; single-card; Vulkan. **Done since:** G0 + tag (`prereg-launch-suppositions`); I-1 safing watchdog (rehearsed); **H1 CONFIRMED** — VidMm degrades foreground compute under a co-tenant. Pilot (load-under-contention): decode 0.52×, ~1 GB spill, reproducible ×2. **Resident-server variant (I-3): decode 0.19× (5× slower) evicting a *hot* model + a hog sweep showing a sharp demotion cliff at the VRAM-budget crossover** (spill scales ~linearly above it; below it the hog is harmless — the control). See `H1-eviction-pilot-20260619` + `H1-resident-sweep-20260619`. **Defense feasibility (I-3):** D3D12 residency priority does NOT protect against a co-tenant — intra-process hint only; budget splits ~evenly (15.3/15.3 GB) MAX vs NORMAL. So no hard pin exists; the defense is **admission control on the live VidMm budget** (drops 31→15 GB under a co-tenant) + intra-arena lifetime-class ordering → **I-4a:** the closed-form admission controller (admit iff footprint ≤ live VidMm budget) **predicts the H1 cliff 5/5** — live budget oracle works (31→15 GB under a co-tenant); `N*`=132 small-ctx sessions at full budget. See `defense-feasibility-d3d12-priority-20260619` + `I4a-admission-controller-20260619`. **I-4b:** the closed-loop admission knee — goodput-under-SLO peaks at **N\*=8** (all SLO-met, 229 t/s) and **collapses to 0 by N=10** (67 t/s); over-admission is worse on every axis. Binding term here is **compute-concurrency** (no VRAM spill) → **N\* = min(compute-concurrency≈8, memory-budget≈132)**; the controller takes the min (memory binds under co-tenant/large-ctx per I-4a/H1). See `I4b-admission-knee-20260619`. **I-4c:** the memory-bound knee — goodput collapses (4→0) when a co-tenant forces the spill, b70tools-instrumented (both terms of `N*` now measured). **H4 — CONFIRMED on-rig:** a lifetime-class arena (router over real `llama-server` KV slots; cache miss = ~2.8 s real re-prefill) beats LRU by **+32% goodput** (95% CI [20, 44], 10 reps, 10/10 seeds) → **both make-or-breaks now confirmed on real hardware** (H1 threat + H4 policy). The earlier sim was exploratory. See `I4c-memory-knee-20260619` + `H4-arena-onrig-20260619`. **Figures:** 6 charts in `figures/` (on the README, regenerate via `figures/make_figures.py`). **Still needs the operator:** on-rig H4 (the arena) + the asymmetric two-card build.

## Recordings (in `results/raw/`)
idle-baseline events.jsonl · e1-microbench-cardA / cardB-contended / Bdq-real-decode JSON · (bench tables in the per-result docs + commit messages).
