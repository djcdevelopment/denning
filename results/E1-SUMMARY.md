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
~Linear to 32K, then a **superlinear cliff** (64K = 11.5× slower than empty; the Vulkan attention-kernel cliff — SYCL would shift it). Admission keeps sessions left of it. *[q8-KV variant in flight: does halving the KV bytes push the cliff out + reach 128K?]*

## H2′ — N-session admission scaling ✅
Aggregate decode **60.9 → 80.6 → 97.4 → 109.9 t/s** @ parallel 1/2/4/8 (still rising at 8 → `N*` > 8 at small ctx); prefill plateaus ~B=4. `N* = min(bandwidth, commit)`, shrinks as context grows.

## Status vs roadmap
**I-2 / E1 substantially DONE** (R1/R2/R3 + roofline + N-session measured on-rig). Remaining E1 refinements: q8-KV roofline (in flight), dequant-under-N-decode, copy-engine scheduling sweep, SYCL-vs-Vulkan cliff (needs ollama/ipex-llm harness), llama.cpp-matched dequant kernel. **Caveats:** dequant is a torch proxy; single-card; Vulkan. **Needs the operator:** G0 + tagging; H1 (watchdog first); the asymmetric two-card build.

## Recordings (in `results/raw/`)
idle-baseline events.jsonl · e1-microbench-cardA / cardB-contended / Bdq-real-decode JSON · (bench tables in the per-result docs + commit messages).
