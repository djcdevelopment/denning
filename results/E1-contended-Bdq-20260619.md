# Result — E1 HEADLINE: contended B_dq → R2 holds under contention (2026-06-19)

*The linchpin of the whole project. Clean + contended run on **Card B (xpu:1, curve-free)**, torch-xpu 2.12.1+xpu. Run by Claude. Recording: `raw/e1-microbench-cardB-contended-20260619.json`. Contention = a saturating 4096³-fp16 matmul loop on a 2nd XPU stream (a proxy for "GPU busy with other work"; real-decode contention is the refinement).*

## Clean Card B numbers (authoritative)
- **B_pcie:** 1.35 (64 KB) → **13.89 GB/s** (256 MB) — **matches the x8 datasheet (~13–15)**. (Card A's earlier ~10.4 was bus-contended by the concurrent curve.) Small-block latency regime real (1.35 @ 64 KB).
- **B_dq isolated:** int8→fp16 **167.9**, int4-unpack **93.5 GB/s**.
- **B_dq CONTENDED:** int8→fp16 **48.2**, int4-unpack **41.1 GB/s** → contention cuts dequant to ~29% / ~44% of isolated (a ~2.3–3.5× penalty).
- **B_c2c:** **6.48 GB/s** ≈ 0.47× B_pcie (host-bounced; R3 confirmed clean).

## R2 — CONFIRMED isolated AND CONTENDED (the make-or-break)
threshold = `B_pcie·r/(r−1)` at B_pcie ≈ 13.9:
| scheme | threshold | isolated | **contended** | verdict |
|---|---|---|---|---|
| FP8 (r=2) | 27.8 | 167.9 ✅ | **48.2 → WINS (1.7×)** | ✅ |
| INT4 (r=4) | 18.5 | 93.5 ✅ | **41.1 → WINS (2.2×)** | ✅ |

**The compression-over-the-bus bet survives contention:** even with dequant cut ~2.5–3.5× by a saturating load, it clears the PCIe threshold by 1.7–2.2×. "Spend FLOPs to dodge the bus" holds on the real FLOP-modest B70 → the cost-model linchpin (R2), the compression arm, and the asymmetric-feed premise are empirically validated. With R1 (~176×) and R3 (0.47×), **all three cost-model results are now confirmed on the real rig.**

## Caveats (honest)
- Contention is a **synthetic compute-saturating matmul**, not real decode (bandwidth-bound — may contend with the memory-bound dequant *harder*). The real-decode-contention test is the refinement; the 1.7–2.2× margin gives headroom.
- Dequant is a **torch cast/unpack proxy** (memory-bound, representative), not a llama.cpp-matched kernel.
- Two-torch-stream "separate queue"; the **same-queue vs copy-engine-separation** axis (Uncle's scheduling point) is unmeasured — and could only *improve* the contended number.

## Manifest
torch 2.12.1+xpu · Card B (xpu:1) · driver 32.0.101.8826 · iters 30, warmup 10 · contended load = 4096³ fp16 matmul on a 2nd stream · recording: `raw/e1-microbench-cardB-contended-20260619.json`.
