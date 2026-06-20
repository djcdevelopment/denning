# Result — I-4a: closed-form admission controller validated against the H1 cliff (2026-06-19)

*The I-3 finding (no hard pin vs a co-tenant) makes admission control the defense. This is the closed-form rule + the **live VidMm budget oracle**, validated: does "admit iff footprint ≤ live budget" predict the measured H1 demotion cliff? Harness: [`../experiments/admission_controller.py`](../experiments/admission_controller.py) (reads the budget via the D3D12 probe `--size-gb 0` monitor mode).*

## The rule (cost-model §2)
With weights `W`, per-session KV `k(ctx)`, live VidMm budget `B`:
- `N*(B) = floor((B − W) / k(ctx))` — max concurrent sessions kept resident
- `admit(demand) = footprint(demand) ≤ B` — else **DEFER** / shed cold blocks first (intra-arena, by lifetime class)

## Live oracle
`QueryVideoMemoryInfo.Budget`, read live via the probe: **31.12 GB** uncontended; drops to ~15 GB under a co-tenant (I-3). `N* = 132` sessions at `W=17.9`, `k=0.1` GB, `B=31.12`.

## Validation vs the measured H1 cliff — 5/5
| hog GB | eff budget (B−hog) | model fits? | controller | measured | match |
|---|---|---|---|---|---|
| 10 | 21.1 | yes | **ADMIT** | fast (0.998) | ✅ |
| 12 | 19.1 | yes | **ADMIT** | fast (0.997) | ✅ |
| 14 | 17.1 | no | **DEFER** | CLIFF (0.231) | ✅ |
| 16 | 15.1 | no | **DEFER** | CLIFF (0.196) | ✅ |
| 18 | 13.1 | no | **DEFER** | CLIFF (0.165) | ✅ |

The model (17.9 GB) stops fitting when the co-tenant exceeds **13.2 GB → DEFER at cap 14**, exactly the measured cliff. **5/5.**

## Reading
- The closed-form rule, fed by the **live** budget oracle, is a *correct* admission predictor: it flips ADMIT→DEFER precisely at the demotion cliff. The OS hands you the limit in real time; staying under it is the whole defense.
- This **closes the I-3 loop**: can't pin (I-3) → admit beneath the live budget (I-4a, validated) → order your own eviction by lifetime class (H4) for whatever must spill.
- `N* = 132` small-context sessions at full budget shows the snappy-regime headroom; as context grows (`k` rises) or a co-tenant shrinks `B`, `N*` falls — the controller tracks it live.

## Caveats (honest)
- This is a **retro-validation** (the rule predicts the already-measured sweep) plus a **live budget read** — not yet a closed loop. The closed-**loop** demonstration (the controller actively shedding sessions/context under a *live* co-tenant to STAY off the cliff) is **I-4b** (needs dynamic workload gating).
- `k` here is nominal (0.1 GB/session); the real `k(ctx)` curve folds in for multi-session / long-context admission.

## Next (I-4b)
The closed-loop "before/after": N sessions under a live co-tenant, the controller gating admission on the live budget — show goodput stays on the SLO side of the cliff vs the uncontrolled (H1) collapse. That's the payoff figure.

## Manifest
`experiments/admission_controller.py` + `d3d12_residency_probe.exe` (monitor mode). Measured constants: `CARD_BUDGET 31.12`, `MODEL_W 17.9`; sweep from `H1-resident-sweep-20260619`. driver 32.0.101.8826.
