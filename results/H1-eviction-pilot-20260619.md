# Result — H1 core eviction pilot: VidMm does NOT protect foreground compute (2026-06-19)

*The tagged P0 / make-or-break-A (prereg `prereg-launch-suppositions`, H1′). Engine **Vulkan** (PDH `non_local` reads cleanly per the blind-spot table), Card B, single-card, **two reproducing runs**. Harness: [`../experiments/h1_eviction_pilot.py`](../experiments/h1_eviction_pilot.py) + [`../experiments/vram_hog.py`](../experiments/vram_hog.py), run under [`../ops/safing_watchdog.py`](../ops/safing_watchdog.py) (observer). Results committed after the matching prereg was tagged.*

## Question
Under an adversarial co-tenant (VRAM-hog) that oversubscribes Card B, does VidMm involuntarily push a model that otherwise **fits** into shared memory (PCIe-bounced) and stall its decode — or does it **protect** the foreground compute process and demote the hog instead?

## Predicted (tagged, before data) vs Actual
| H1′ prediction | actual (2 runs) | |
|---|---|---|
| `non_local` rises **≥ 1 GB** | **0.97 / 0.974 GB** | ≈ met (right at the threshold) |
| decode stall **≥ 2× TBT** | **2.0× — 133→70 t/s (ratio 0.52)** | ✅ met |
| VidMm **demotes** the serving process (not protect) | dedicated saturated 31.0–31.5 GB; model decode halved | ✅ foreground **not** protected |

## Runs (reproducible — not noise)
| run | baseline tg | pressured tg | ratio | `non_local` peak | dedicated peak |
|---|---|---|---|---|---|
| 1 | 133.44 | 69.55 | 0.521 | 0.97 GB | 31.01 GB |
| 2 | 133.13 | 69.54 | 0.522 | 0.974 GB | 31.49 GB |

Near-identical across runs — the eviction effect is **robust**, notably unlike the N-session throughput (which swung 20–30%). The discriminating signal of a make-or-break test is stable.

## Mechanism (measured)
The hog walked Card B free 31.2 → 16.6 GB (15 GB held). The 17.3 GB model then loaded into the oversubscribed card: **dedicated VRAM saturated at the ~31 GB cap**, and the ~1 GB that didn't fit was committed to **Shared GPU Memory** (`gpu.adapter.vram.non_local.bytes_committed` 0 → 0.97 GB) — i.e. PCIe-bounced system RAM. **Just ~1 GB on the wrong side of the bus halved decode** (133→70 t/s) — a vivid restatement of the cost model (R1/R2): a sliver of state across PCIe dominates the roofline.

## Verdict: **H1 SUPPORTED** — VidMm does not protect foreground compute
The co-management premise is real on Win10/Arc: the OS memory manager *will* degrade a fitting serving process under desktop/co-tenant contention. This is the motivation denning is built on, now measured rather than asserted — and the **pre-committed pivot does NOT fire** (it would have, had VidMm protected the foreground). Proceed toward **I-3** (the pinned arena that resists this).

## Caveats (honest)
- **Load-under-contention, not evict-already-resident.** The model loaded *while* the hog held 15 GB, so ~1 GB never got a dedicated home (vs. being evicted after full residency). The stricter variant — a persistent `llama-server` fully resident, hog applied *after* — is the I-3 follow-up.
- **`non_local` is system-wide** (PDH cross-process). Attribution to the *model's* bytes (vs the hog's) is inferred from the decode penalty (the model slowed → the model's path is over PCIe). Per-process DXGI is blind here (reads 4 KB). Strong circumstantial, not per-byte proof.
- **Cross-API**: Vulkan server + Level-Zero (torch-xpu) hog sharing the card's WDDM budget — realistic, but noted.
- `non_local` 0.97 GB is marginally **under** the predicted ≥ 1 GB; a 16 GB hog would clearly exceed. The directional and decode-penalty predictions are met.

## Next
I-3 — the resident-server variant + a **hog sweep** (find the demotion threshold and the spill-vs-decode curve), then the arena that pins residency against this.

## Manifest
`experiments/h1_eviction_pilot.py` + `vram_hog.py` · Card B Vulkan (`GGML_VK_VISIBLE_DEVICES=1`) + `xpu:1` hog · b70tools b9279 recording (PDH `gpu.adapter.vram.{local,non_local}.bytes_committed`) · safing watchdog observer · driver 32.0.101.8826. Raw recordings under `results/raw/h1-*` (gitignored; key values inlined above).
