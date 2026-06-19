# Evaluation Matrix

*One table a reviewer uses to check "did they test what they claimed?" — and the skeleton of the eval section. Rows = hypotheses/RQs; columns = workload, baselines, primary metric, the isolating ablation, runs, pass/kill, and the figure/paper it feeds. (Uncle's P4.) Thresholds marked `[G0]` are set with the advisor at G0. Building this early surfaces under-specified hypotheses — **H6's workload is the thinnest and needs work.**)*

| Hyp / RQ | Workload | Baseline(s) | Primary metric | Isolating ablation | N | Pass | Kill/pivot | → |
|---|---|---|---|---|:--:|---|---|---|
| **E1 / R1** recompute vs refetch | microbench (no model) | — | materialize µs/tok | recompute vs refetch-raw | ≥5 | refetch dominates (predicted) | — | HotOS |
| **E1 / R2** compression-over-bus | microbench + decode load | refetch-raw | contended `B_dq` vs threshold | scheme {FP8,INT4} × {same-queue, engine-separated} × HAGS | ≥5 | contended `B_dq` > threshold under some schedule | < threshold for all schedules → drop compression family | **HotOS (headline)** |
| **E1 / R3** card→card | microbench | host→VRAM | effective GB/s | path: card→card vs host-staged | ≥5 | quantified (≤½ PCIe expected) | — | HotOS |
| **H1** VidMm involuntary eviction | N agent sessions + adversarial VRAM-hog (co-tenancy) | VidMm-naive | decode-stall attributable to VidMm; game frame-pacing p99 | locked-arena vs unlocked; PresentMon on/off | ≥5 | measurable involuntary eviction + stall | OS protects process / stall < few % → demote co-mgmt | ATC/MLSys |
| **H2′** admission knee | ShareGPT/WildChat multi-turn; agentic-gap traces | keep-resident + LRU; (CUDA: KVBM) | **goodput-under-SLO per GB system-RAM** | admission-ON vs OFF; gate on commit vs bandwidth | ≥5 | goodput peaks at finite `N*`; beats baseline by `[G0]`% | no peak / no win | ATC/MLSys |
| **H4** lifetime classes (spine) | same as H2′ | per-request TTL (Continuum); per-block priority (KVBM); **verdict-as-oracle** | goodput-under-SLO per GB system-RAM | **classes-ON vs classes-OFF** | ≥5 | classes beat baselines by `[G0]`% (robust) | within noise → narrow to admission-only | **ATC/MLSys (core)** |
| **H5′** 125k-MoE spill / inverted cascade | Qwen3-Coder-30B-A3B @ 125k, single card | DRAM-warm-tier cascade | spill cost; goodput per GB RAM | recompute/keep-resident reclaim vs DRAM-warm | ≥5 | inverted cascade wins by `[G0]` | no advantage → RAM<VRAM is a constraint, not a lever | ATC/MLSys |
| **H6** fractal portability | **[THIN — needs a concrete workload]** one contract across VRAM/DRAM/NVMe/disk | per-tier bespoke logic | per-tier special-case LoC; eviction quality | one parameterization vs per-tier tuning | — | non-degenerate at every tier, ≤`[G0]` special-case lines | leaks → document where | stretch / full paper |

**Stats discipline (all rows):** report P50 **and** P99 + the measured noise floor on the frozen build; raise N per the power/MDE rule until MDE < the claimed effect (`[G0]`); engine (SYCL/Vulkan) is a separate panel, never differenced. **Gap flagged:** H6 needs a real workload + metric before it's claimable — first cut to drop if scope tightens (per v2).
