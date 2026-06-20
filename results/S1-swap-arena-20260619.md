# Result — S1: sequence-grained KV swap — refetch beats recompute on real KV (2026-06-19)

*Stage 1 of the [block-KV arena](../docs/block-kv-arena-design.md). On a cache miss, **restore** the conversation's saved KV (refetch) instead of **re-prefilling** it (recompute) — via llama-server's `--slot-save-path` + `/slots?action=save|restore`. Measures **R1 on real KV bytes** (the last cost-model constant we were inferring) and the goodput impact. Harness: [`../experiments/h4_swap_probe.py`](../experiments/h4_swap_probe.py) + [`../experiments/h4_swap_arena.py`](../experiments/h4_swap_arena.py).*

![S1 swap — refetch-on-miss beats re-prefill, +33% goodput](../figures/h4-swap.png)

## R1 on real KV (the probe)
| operation | cost |
|---|---|
| re-prefill 3507-token prefix (**recompute**) | **2422 ms** |
| save KV to disk | 220 ms (344 MB) |
| restore KV from disk (**refetch**) | **84 ms** |
| verify (post-restore) | 2-token prefill, 33 ms → fully resident |

**Refetch is ~29× cheaper than recompute on real KV.** The restore brings the *whole* KV back (verify: only 2 tokens re-prefilled). KV footprint measured directly: **344 MB / 3507 tokens = ~98 KB/token** — that's `k`, measured, not inferred.
*(Restore here is disk-tier — NVMe ~4 GB/s. A host-RAM tier would approach the PCIe-bound ~13.9 GB/s and widen the gap toward the cost model's microbench 176×.)*

## The swap arena (goodput)
Same workload as the [on-rig H4](H4-arena-onrig-20260619.md) (6 hot + cold scan, 4 slots), `classes` policy, swap ON vs OFF, 3 seeds:
| seed | swap OFF | swap ON | OFF latency | ON latency |
|---|---|---|---|---|
| 0 | 18 | 23 | 54.5 s | 43.5 s |
| 1 | 18 | 24 | 54.6 s | 40.7 s |
| 2 | 16 | 22 | 59.6 s | 45.6 s |
| **mean** | **17.3** | **23.0** | 56.2 s | 43.3 s |

**Swap beats re-prefill by +33% goodput and −23% latency** — by turning re-accesses of evicted conversations from a 2.4 s recompute into an 84 ms refetch. R1, on real goodput.

## The deeper finding: cheap swap makes the eviction policy secondary
Under swap, **classes ≈ LRU** (both goodput 23 at seed 0). Once a miss is cheap, the *quality* of the eviction decision stops mattering — LRU evicts the hot set more (12 hits vs classes' 18) but cheaply restores it (11 restores vs 5), netting the same goodput. **The R1 lever (refetch ≫ recompute) dominates the H4 policy lever.** Strategic implication: build the swap first — it's the bigger win *and* it de-risks the harder eviction-policy work.

## Verdict & gate
S1's gate (block-KV-arena-design): *"is restore ≪ re-prefill on real KV?"* → **YES (29×)**. The swap path is worth paging. S1 confirms **R1 — the cost model's linchpin — on real KV and real goodput**, and reprioritizes the program: swap infrastructure > eviction-policy sophistication. S2 (paged KV) is justified.

## Caveats (honest)
- **Sequence-grained** (whole-conversation save/restore), not block-grained — that's S2/S3 (needs paged KV).
- **Disk-tier** restore (NVMe); a host-RAM tier would be faster (the PCIe bound).
- The 220 ms **save** is paid on eviction; in a tight loop that overhead matters (async save mitigates).
- The swap win scales with **restore opportunities** (re-accesses of saved conversations); the short 40-turn trace understates it.

## Manifest
`experiments/h4_swap_probe.py` + `h4_swap_arena.py` (`llama-server --slot-save-path`, `/slots` save/restore). Card B Vulkan. `k` = 98 KB/tok; restore 84 ms / re-prefill 2422 ms (3507 tok). Slot files on `D:\tmp\slots` (transient, off-repo). driver 32.0.101.8826.
