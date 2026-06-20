# Result — H4 ON-RIG: lifetime-class eviction beats LRU on real inference (2026-06-19)

> ✅ **The on-rig confirmatory H4** — upgrades the earlier [simulation](H4-lifetime-sim-20260619.md) to REAL inference with measured costs. The make-or-break for denning's control *policy*.

*The "arena" is a router managing M real `llama-server` KV slots as the resident set. A cache **HIT** (a conversation's KV resident in its slot) is a cheap turn (~40 ms); a **MISS** (evicted) re-prefills the long prefix → the real R1 stall (~2.8 s measured). The eviction policy picks the victim slot. Harness: [`../experiments/h4_arena.py`](../experiments/h4_arena.py) (+ [`h4_probe.py`](../experiments/h4_probe.py) for the hit/miss calibration).*

![H4 on-rig — lifetime-class eviction beats LRU on 10/10 seeds](../figures/h4-onrig.png)

## Mechanism (measured — `h4_probe`)
| | prefill tokens | prefill ms |
|---|---|---|
| cache **HIT** (prefix resident) | 2 | **39** |
| cache **MISS** (evicted → re-prefill) | 4606 | **3691** |

~**94×**. A miss blows the 2 s TTFT SLO; a hit meets it. So the eviction policy → hit rate → goodput, on real inference.

## Setup
6 hot long-running sessions + a stream of cold one-off sessions (30%, scan pressure); **M=4 KV slots** (overload: hot set > slots). Each session has a unique ~3.5k-token context. Policies: `classes` evicts the lowest-reuse (coldest) session [lifetime-class / provenance]; `lru` evicts least-recently-used [recency]. Metric: per-turn TTFT = server `prefill_ms`; **goodput = turns with TTFT ≤ 2 s**. 10 seeds; the *same* trace per seed feeds both policies.

## Result (10 reps)
| | classes-ON | LRU |
|---|---|---|
| mean goodput | **15.0 / 40 (37.5%)** | 11.3 / 40 (28.3%) |
| improvement | **+32.3% relative** — 95% CI **[20.2%, 44.4%]** — / +9.3 pp | |
| seeds classes ≥ LRU | **10 / 10** (9 strict wins, 1 tie) | |
| mean total prefill | 62.1 s | 71.1 s (−13%) |

## Verdict: H4 SUPPORTED on-rig — meets the pre-registered criterion
The tagged H4 prediction: *"classes-ON beats recency/TTL by ≥20% goodput-under-SLO, ≥10 averaged reps, 95% CI excluding zero."* Measured: **+32.3% (≥20%), 10 reps, CI [20.2, 44.4] excludes zero.** Combined with H1, **both make-or-breaks are now confirmed on real hardware** — the threat (the OS evicts you) and the policy (typed lifetime classes beat recency).

## Reading
- Real prefix-cache hit/miss makes the refetch cost (R1) concrete: ~40 ms vs ~2.8 s. Protecting the high-reuse (hot) sessions from cold-scan eviction keeps them resident → fewer SLO-violating re-prefills.
- Holds across 10/10 seeds. The seed-7 **tie** is honest: when a trace has little exploitable hot reuse, the policies converge — exactly as expected (and why the mean isn't inflated).
- Pairs with I-3: residency priority can't pin against a *co-tenant* (the OS wins), but it's exactly the right tool for ordering denning's *own* eviction — and here it earns +32% goodput on live inference.

## Caveats (honest)
- **Conversation-grained, not block-grained.** The arena evicts whole-conversation slots (lifetime class = session reuse frequency), not per-KV-block typed provenance. The block-grained version (SYSTEM/DOC/TURN tiers within one context) is the richer refinement — the *sim* modeled that; this is the coarser-but-real on-rig cut.
- **Baseline = LRU** (the recency family); literal per-request TTL or per-block-priority baselines differ in detail but share the provenance-blindness.
- **The CI lower bound (20.2%) grazes the 20% bar** — the point estimate (32%) clears it comfortably; more reps would widen the margin (the seed-7 tie pulls the mean down, honestly).
- **Constructed workload** (hot/cold + scan) — realistic for agents (long sessions + one-off requests) but a chosen scenario, not a captured production trace.

## Relation to the H4 simulation
The earlier [sim](H4-lifetime-sim-20260619.md) was the abstract block-grained policy model (+32 → +100 pp, idealized). This is the REAL inference version with measured prefill costs (+32% / +9 pp). The sim over-states the magnitude (block-grained protection + idealized reuse); **the on-rig number is the honest one — and still meets the bar.**

## Manifest
`experiments/h4_arena.py` + `h4_probe.py` (router over `llama-server -np 4`, `id_slot` eviction control, `cache_prompt`; `prefill_ms` = the real cost). Card B Vulkan. driver 32.0.101.8826. 10 seeds, slots=4, hot=6, length=40, SLO 2000 ms. Raw goodput classes/LRU per seed: 18/12 18/14 16/12 19/14 17/10 18/16 12/9 6/6 12/10 14/10.
