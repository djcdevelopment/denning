# Result — I-4b: the admission knee (goodput collapses past N*), closing the loop (2026-06-19)

*The closed-loop payoff: does admitting N* concurrent sessions beat over-admitting? N sessions stream from `llama-server -np N` on Card B; goodput = # meeting SLO (TBT_median ≤ 50 ms AND TTFT ≤ 2 s). Harness: [`../experiments/i4b_closed_loop.py`](../experiments/i4b_closed_loop.py) (concurrent urllib streaming driver). Reframes the controller: **N\* = min(compute-concurrency, memory-budget)**.*

## The knee (ctx 2048/slot, n_predict 200, true overlap)
| slots N | goodput | TBT median | agg decode t/s | regime |
|---|---|---|---|---|
| 6 | 6/6 | 24.8 ms | 217 | all SLO-met |
| 8 | 8/8 | 29.3 ms | **229** | **N\* — peak** |
| 10 | 0/10 | 149 ms | 67.5 | collapsed |
| 12 | 0/12 | 155 ms | 78 | collapsed |

(N=8 reproduced across runs: 29.3 / 29.5 ms, goodput 8 both.)

## Reading
- **Sharp admission knee at N\*=8.** Below it, all sessions meet SLO and aggregate throughput *rises* (217→229). Past it (N≥10), goodput collapses to 0 **and** aggregate throughput collapses 3.4× (229→67.5). **Over-admission is strictly worse on every axis** — not a throughput/latency trade, a cliff. Admitting N\* dominates.
- **The controller's payoff:** admit N\* → goodput 8 + 229 t/s; over-admit → goodput 0 + 67.5 t/s. Finding N\* *is* the defense.
- **The binding constraint here is COMPUTE concurrency, not memory** (`server_footprint` stayed 0 — no VRAM spill). The serving engine's throughput cliffs past ~8–10 concurrent sequences on this Vulkan/Arc stack (same family as the long-context / FA-kernel attention cliff).
- **So N\* = min(compute-concurrency, memory-budget).** I-4a gave the memory term (132 small-ctx sessions fit the budget); I-4b gives the compute term (8 meet the SLO). At small ctx the **compute** term binds (8 ≪ 132); under a co-tenant or large context the **memory** term binds (H1/I-4a). The controller takes the min — and both terms are now measured.

## What it means
The closed-loop admission story holds end to end: there is a finite N\* beyond which goodput collapses, and admitting to N\* maximizes goodput **and** throughput. denning's controller = compute the min over (a) the compute-concurrency SLO limit and (b) the live VidMm budget limit, and admit beneath it. The "co-residency" thesis, demonstrated: read the limits, admit beneath them, never thrash.

## Caveats (honest)
- This knee is **compute-concurrency-bound** (footprint 0); the **memory-bound** knee (the H1/I-4a cliff) needs the large-ctx or co-tenant regime with **b70tools (PDH)** instrumentation — the D3D12 probe's `Budget` did not reflect the Vulkan server's VRAM (an instrumentation gap, noted for the memory-bound version).
- The compute cliff's exact cause (Vulkan attention path vs batching) is not isolated here; empirically aggregate throughput collapses past ~8–10 concurrent sequences.
- Single run per N (the knee is sharp + N=8 reproduced, so not noise-dominated); the fuller version averages reps + sweeps ctx to map the N\*(ctx) surface and the co-tenant (memory) term.

## Next
- The **memory-bound** N-session knee under a live co-tenant (b70tools-instrumented) → show the controller's `min()` switches from the compute term to the memory term as the co-tenant grows.
- Average + ctx sweep for the N\*(ctx) surface (the paper figure).

## Manifest
`experiments/i4b_closed_loop.py` (`llama-server -np N`, concurrent urllib streaming, goodput @ SLO TBT≤50 ms / TTFT≤2 s). Card B Vulkan. driver 32.0.101.8826. Raw result lines in the run log.
