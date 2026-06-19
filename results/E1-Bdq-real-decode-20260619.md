# Result — B_dq under REAL decode (2026-06-19): R2 wins by the FULL margin

*Refinement of the synthetic-contended headline. A real `llama.cpp` decode (Qwen3-30B-A3B, n=8192) ran on Card B (background process) while the dequant bench ran concurrently — two processes, **OS/VidSch-arbitrated** (the authentic scenario). Decode confirmed alive throughout the bench. Recording: `raw/e1-Bdq-real-decode-20260619.json`.*

## Measured — B_dq across the contention spectrum
| dequant | isolated | synthetic matmul load | **REAL decode load** |
|---|---|---|---|
| int8→fp16 | 168 | 48 | **169.2** |
| int4-unpack→fp16 | 94 | 41 | **94.0** |

## Reading
Under a **real single-stream decode**, B_dq ≈ **isolated** (no measurable degradation) → R2 wins by the **full 6–8×**, not just the synthetic worst-case 1.7–2.2×.

**Why:** the synthetic load was *compute-saturating* (continuous 4096³ matmuls). Real decode (3B-active MoE @ ~130 t/s) is bandwidth-bound but **low-duty-cycle** — ~7.7 ms/token with brief compute bursts — so a 64 MB dequant (~0.8 ms) slots into the gaps and the scheduler interleaves it at near-full bandwidth. **The contention penalty is co-tenant-duty-cycle-dependent:** single-stream decode barely contends; a *saturated* GPU (the synthetic case) is the pessimistic bound. **R2 wins at both ends.**

## Net on R2 (the linchpin)
Robust across the spectrum: **6–8× (real decode / isolated) → 1.7–2.2× (synthetic saturation)**. Compression-over-the-bus holds. The synthetic-contention caveat on the headline is now bounded by a real-decode datapoint at the favorable end.

## Next refinement
The duty-cycle insight names the real stress: **N concurrent decode sessions** raise the GPU duty cycle. Run dequant under N=2/4/8 concurrent decodes (one model, parallel slots) to find where B_dq actually starts to drop — the authentic "many agents" contention, and the H2′ admission knee.

## Manifest
torch-xpu 2.12.1+xpu · Card B (xpu:1) · concurrent real decode = `llama-bench -n 8192` (GGML_VK_VISIBLE_DEVICES=1) · driver 32.0.101.8826.
