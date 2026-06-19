# Result — E1 microbench (isolated): B_pcie, B_dq, B_c2c; R2 + R3 confirmed (2026-06-19)

*Real measurement via **torch-xpu 2.12.1+xpu** on **Card A (xpu:0)** while the Qwen3 decode curve ran on Card B (so B_pcie is mildly bus-contended — clean re-run on B pending). Run by Claude, authorized by operator. Recording: `raw/e1-microbench-cardA-20260619.json`. **ISOLATED dequant only** — contended B_dq (the headline) is the next run. Dequant is a torch cast/unpack proxy (memory-bound, representative); a llama.cpp-matched kernel is the camera-ready version.*

## Measured
| constant | value | note |
|---|---|---|
| **B_pcie** (host↔VRAM) | 0.95 (64 KB) → 5.3 (1 MB) → **~10.4 GB/s** (64–256 MB) | below x8 datasheet ~13 GB/s (bus contention + Card A display); **small-block latency regime real** (Uncle #3a) |
| **B_dq** int8→fp16 | **165 GB/s** | |
| **B_dq** int4-unpack→fp16 | **85.5 GB/s** | |
| **B_c2c** card→card (host-bounced) | **3.89 GB/s** | ≈ 0.38× host→VRAM |

## Cost-model results — CONFIRMED (isolated)
- **R2 (linchpin), isolated:** wins iff `B_dq > B_pcie·r/(r−1)`. FP8 (r=2): 165 > 20.7 → **WINS ~8×**. INT4 (r=4): 85.5 > 13.8 → **WINS ~6×**. Compression-over-the-bus wins isolated by 6–8×. **Open: does the margin survive contention?** → contended-B_dq is the headline next run.
- **R3:** card→card 3.89 ≈ **0.38× host→VRAM** — host-bounced, no P2P, as predicted. Asymmetric feed pays a ~2.6× penalty → **Card 1 must compute, not just store.**
- **R1** (from `E1-partial-prefill-decode`): refetch ~176× cheaper than recompute. → **all three cost-model results now have real on-rig support (isolated).**

## Next
1. **Contended B_dq (headline):** run the dequant bench *concurrently with a decode load on the same card*, across the scheduling axis (same-queue vs copy-engine-separated, HAGS on/off) → does the 6–8× margin hold? (Cost-model R2 + Uncle's #1.)
2. **Clean B_pcie re-run on Card B** (curve-free) for the authoritative transfer number.

## Manifest
torch 2.12.1+xpu · device xpu:0 (Card A, B70) · driver 32.0.101.8826 · iters 30, warmup 10 · D: venv · concurrent: Qwen3 decode curve on Card B · recording: `raw/e1-microbench-cardA-20260619.json`.
