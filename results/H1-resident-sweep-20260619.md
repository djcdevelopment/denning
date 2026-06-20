# Result — H1 resident-server eviction + hog sweep (I-3): VidMm evicts a HOT model; the demotion cliff (2026-06-19)

*The stricter "evict-already-resident" form of H1 — model brought **fully resident first** (persistent llama-server, baseline stream confirms), **then** the hog applies — plus a **hog sweep** mapping the demotion threshold and spill-vs-decode curve. Engine Vulkan, Card B, streaming `/completion` TBT. Harness: [`../experiments/h1_resident_pilot.py`](../experiments/h1_resident_pilot.py). Closes the load-under-contention caveat of the [pilot](H1-eviction-pilot-20260619.md).*

## Headline
Evicting a **hot, actively-decoding** resident model is **worse** than loading under contention: decode collapses **5×** (vs the pilot's 2×). And the sweep reveals a **sharp demotion cliff** at the VRAM-budget crossover, with shared-memory spill scaling ~linearly with oversubscription.

## Resident eviction (hog 15 GB, model resident first)
| | baseline | pressured | |
|---|---|---|---|
| decode | 117.8 t/s | **22.9 t/s** | **0.194×** |
| TBT median | 8.5 ms | 43.4 ms | 5.1× |
| TTFT | 113 ms | 911 ms | 8× |
| `non_local` | ~0.2 GB | **2.20 GB** | clears ≥1 GB |

→ **H1-SUPPORTED (resident).** VidMm evicts ~2.2 GB of a hot model to shared memory; decode 5× slower. The faithful form of the tagged prediction, met more strongly than the pilot.

## Hog sweep — the demotion cliff + spill-vs-decode curve
Model resident ≈ 17.9 GB; card budget ≈ 31.2 GB. Threshold = where `hog + model` crosses the budget (~cap 13).
| hog cap GB | hog+model GB | decode ratio | `non_local` peak GB | regime |
|---|---|---|---|---|
| 10 | 27.9 | 0.998 | 0.22 | **under budget — NO effect (control)** |
| 12 | 29.9 | 0.997 | 0.24 | under budget — NO effect |
| 14 | 31.9 | **0.231** | 0.24 | **AT threshold** — decode cliff; spill too small/brief for the coarse gauge |
| 16 | 33.9 | 0.196 | 2.70 | over — spill ≈ oversubscription |
| 18 | 35.9 | 0.165 | 4.87 | over — spill ≈ oversubscription |

## Reading
- **Sharp cliff at the budget crossover** (~cap 13–14). Below it the hog is *harmless* (decode unchanged) — the **control** proves the hog's mere presence doesn't slow decode; only genuine oversubscription does. At/above it, decode collapses **4–6×**.
- **Spill scales ~linearly with oversubscription**: `non_local` ≈ (hog + model − budget) — cap 16 → 2.70 GB (predicted ~2.7), cap 18 → 4.87 GB (predicted ~4.7). The exact bytes over budget are what land in PCIe-bounced shared memory. Clean mechanism confirmation.
- **Decode penalty saturates (~0.16–0.23×) while spill keeps growing.** Once the *hot* decode-path bytes are bounced over PCIe, spilling more *cold* bytes doesn't proportionally worsen decode. The penalty floor is set by the hot working set, not total spill — a key insight for the arena (lock the hot set; let cold blocks take the eviction).
- **Instrumentation nuance (honest):** at cap 14 decode collapsed (0.231) while the PDH `non_local` gauge showed no rise (0.24). The small (~0.7 GB), brief threshold spill was missed by the coarse PDH slow-collector (~4 samples/run), but the fine-grained streaming-TBT signal caught it. **Decode penalty is the more sensitive demotion indicator at the margin**; `non_local` clearly registers only at ≥2 GB spill. A faster PDH cadence would close the gap.

## What it means
H1 is confirmed in its strict form **and characterized**: VidMm does not protect hot foreground compute; the threat is a **sharp cliff at the VRAM-budget crossover**, and the cost is set by how much of the **hot working set** gets bounced over PCIe. This is exactly the regime denning's **pinned arena** must defend — lock the hot working set resident (D3D12 `MakeResident` / residency priority) so a co-tenant's spill lands on cold/evictable blocks, not the decode path. The sweep is the *before* picture; the arena's job is to flatten this cliff.

## Caveats (honest)
- `non_local` is system-wide (PDH cross-process); attribution to the model inferred from the decode penalty (the model slowed). Cross-API hog (Level-Zero) vs server (Vulkan), sharing the WDDM budget.
- PDH slow-collector cadence is coarse (~4 samples/run) → small/brief spills under-registered (cap 14). Decode-penalty is the sensitive signal; treat the `non_local` column as a floor.
- Reproducibility: the decode ratio is stable (cap-15 single run 0.194 vs cap-16 sweep 0.196); `non_local` is noisier due to sampling.

## Next
The **pinned arena**: lock the hot working set resident so eviction lands on cold blocks, then re-run this exact sweep and show the cliff is defended (the I-4 controller then admits work to stay left of the residual cliff).

## Manifest
`experiments/h1_resident_pilot.py` (+ `vram_hog.py`, `ops/safing_watchdog.py` observer). Card B Vulkan persistent `llama-server`, streaming `/completion` TBT (urllib). b70tools b9279 PDH `gpu.adapter.vram.non_local.bytes_committed`. driver 32.0.101.8826. Raw: `results/raw/h1r-*` (gitignored; values inlined).
