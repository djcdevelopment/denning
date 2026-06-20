# Workbook — 2026-06-19 — I-4b closed-loop admission knee

*The payoff demo: does admitting N* concurrent sessions beat over-admitting? Built a concurrent streaming driver; found the knee.*

## Built
- **`experiments/i4b_closed_loop.py`** — `llama-server -np N` on Card B, N concurrent urllib streaming sessions (ThreadPoolExecutor), goodput = # meeting SLO (TBT med ≤ 50 ms AND TTFT ≤ 2 s) + live budget + footprint.

## Ran (ctx 2048/slot, n_predict 200, true overlap)
| N | goodput | TBT med | agg t/s |
|---|---|---|---|
| 6 | 6/6 | 24.8 | 217 |
| 8 | 8/8 | 29.3 | **229** ← N* |
| 10 | 0/10 | 149 | 67.5 |
| 12 | 0/12 | 155 | 78 |

(First pass with n_predict 64 was artifact-noisy — thread skew; longer generations gave a clean cliff. N=8 reproduced.)

## Finding
- **Sharp admission knee at N\*=8**: below it all sessions meet SLO and aggregate *rises*; past it (N≥10) goodput → 0 AND aggregate collapses 3.4× (229→67.5). **Over-admission loses on every axis.** Admitting N\* dominates — finding N\* is the defense.
- **Binding term here = compute-concurrency, NOT memory** (footprint 0; the serving engine cliffs past ~8–10 concurrent sequences on Vulkan/Arc). So **N\* = min(compute-concurrency≈8, memory-budget≈132)**: I-4b = the compute term, I-4a = the memory term; the controller takes the min. Memory binds under a co-tenant / large ctx (H1/I-4a); compute binds at small ctx.

## Caveat
Compute-bound knee (not the memory cliff). The memory-bound N-session knee needs b70tools (PDH) instrumentation + a co-tenant/large-ctx — the D3D12 probe budget didn't reflect Vulkan VRAM. Single-run/N (knee sharp + N=8 reproduced → not noise).

Result: [`../results/I4b-admission-knee-20260619.md`](../results/I4b-admission-knee-20260619.md).

## Next (refinements)
Memory-bound knee under a live co-tenant (instrumented) → show the controller's `min()` switch compute→memory as the co-tenant grows; average + ctx sweep for the N\*(ctx) surface.
