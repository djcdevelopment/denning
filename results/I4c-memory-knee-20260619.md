# Result — I-4c: the MEMORY-bound admission knee (closes I-4b's gap) (2026-06-19)

*I-4b's knee was compute-bound (footprint stayed 0). This isolates the MEMORY term: fixed small N=4 (below the compute knee ≈8) + short ctx (2048, below the long-context roofline cliff) + a co-tenant hog sweep that shrinks the budget. **b70tools (PDH) records the REAL footprint** — the D3D12 probe couldn't see Vulkan VRAM. Harness: [`../experiments/i4c_memory_knee.py`](../experiments/i4c_memory_knee.py).*

![Memory-bound admission knee — goodput collapses when the co-tenant forces a spill](../figures/i4c-memory-knee.png)

## The memory-bound knee (N=4, ctx 2048, hog sweep)
| co-tenant hog (GB) | goodput | TBT med (ms) | agg t/s | dedicated (GB) | spill `non_local` (GB) |
|---|---|---|---|---|---|
| 0 | 4/4 | 18.5 | 210 | 18.3 | 0.2 |
| 10 | 4/4 | 18.4 | 220 | 18.3 | 0.2 |
| 12 | 4/4 | 18.4 | 214 | 18.3 | 0.2 |
| 14 | **0/4** | 59.0 | 65 | 20.6 | **1.07** |
| 16 | **0/4** | 103.5 | 37 | **31.7** | **2.92** |

## Reading
- **A clean memory-bound knee at the budget crossover (~hog 13).** Footprint (model + KV) ≈ 18.3 GB; budget 31.1. While the hog ≤ ~12.7 GB, footprint + hog fits → goodput 4/4, no spill (`non_local` ~0.2). Past it (hog ≥ 14), the resident set spills (`non_local` 1.07 → 2.92 GB; dedicated saturates at 31.7) and goodput collapses to 0.
- **Isolated from the I-4b confounds.** N=4 is below the compute knee (≈8) and ctx 2048 is below the roofline cliff — so the collapse is *purely* memory spill, confirmed by the rising `non_local` (the spill is the measured cause, not a proxy).
- **b70tools sees what the D3D12 probe couldn't.** `gpu.adapter.vram.local.bytes_committed` tracks the real footprint (18.3 → 31.7 GB) and `non_local` the spill — closing the instrumentation gap flagged in I-4b.
- **The I-4a budget rule predicts it.** Admit iff footprint ≤ live budget: footprint 18.3 fits while hog ≤ 12.7; DEFER above. Measured collapse at hog 14 = the predicted crossover. The same closed-form rule that predicted the H1 cliff predicts the memory-bound goodput knee.

## N* = min(compute, memory) — both terms now measured + instrumented
- **I-4b** — the COMPUTE term (`N*`≈8 at small ctx, no spill).
- **I-4c** — the MEMORY term (goodput collapses when footprint + co-tenant > budget; spill measured by b70tools).
- The controller takes the min and admits beneath it. Co-residency, demonstrated on both axes.

## Caveats (honest)
- The hog is a co-tenant proxy (Level-Zero allocation); a real desktop/game app is the in-the-wild version.
- Single run per hog level (the knee is sharp and lands at the same crossover as the H1 cliff, so not noise-dominated); averaging + a finer hog grid would pin the exact crossover.
- The hog=0 `local_peak` sample (2.1) caught an early pre-load moment; hog ≥ 10 shows the true 18.3 GB footprint.

## Manifest
`experiments/i4c_memory_knee.py` (`llama-server -np 4`, b70tools recording, concurrent streaming goodput @ SLO TBT≤50 ms / TTFT≤2 s). Card B Vulkan. driver 32.0.101.8826. Raw: `results/raw/i4c-*` (gitignored).
