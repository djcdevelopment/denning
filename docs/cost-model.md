# Cost Model — denning's analytical spine

*The theory the experiments confirm or break. Written BEFORE the box per Uncle's counsel (4-lens follow-up, 2026-06-19): a research program needs a small predictive model that the empirics validate — deviations from it are the findings. **Status: DRAFT.** Constants marked `[MEASURE]` are predicted from prior work / specs and are exactly what E1 measures; the predictions here are pre-registration fodder, not results.*

## Notation

| Symbol | Meaning | Est. value (B70 rig) |
|---|---|---|
| `B_vram` | VRAM bandwidth | ~608 GB/s |
| `B_pcie` | PCIe 4.0 x8 effective | ~12–14 GB/s `[MEASURE]` |
| `B_dq(s)` | dequant-kernel output throughput, scheme s | `[MEASURE]` (isolated AND contended) |
| `R_prefill` | prefill rate (tokens/s) → recompute | `[MEASURE]` (prior MoE est. anomalously low) |
| `k` | KV bytes/token (Qwen3-Coder-30B-A3B, GQA-4, 48L) | ~96 KB FP16 / ~49 KB FP8 / ~24.5 KB INT4 |
| `r` | compression ratio | 2× (FP8), 4× (INT4) |
| `H` | commit headroom (the true wall) | ~`[MEASURE]`; commit, not free RAM |

## 1. Materialization cost (the E1 model)

Cost to put one KV block of `L` tokens onto the compute card, modeled as **fixed overhead + per-token rate** (the fixed term is why an L-crossover exists at all — it lives in the small-block, latency-dominated regime):

- **recompute:**        `t_rc(L)   = α_rc + L / R_prefill`
- **refetch-raw:**      `t_raw(L)  = α_pcie + L·k / B_pcie`
- **refetch-compressed+decompress:** `t_cmp(L) = α_pcie + α_dq + L·k/(r·B_pcie) + L·k / B_dq`

Crossover: `L* = (α_j − α_i)/(β_i − β_j)` where `β` is the per-token slope.

### Result 1 — recompute loses to refetch on *time*, decisively, and it's ~L-independent.
Per-token, `β_rc = 1/R_prefill` vs `β_raw = k/B_pcie ≈ 49 KB / 13 GB/s ≈ 3.8 µs/tok` (FP8). Recompute means a *full forward pass* per token (billions of FLOPs) — its per-token cost dwarfs moving 49 KB unless `R_prefill` is enormous. **So refetch dominates for all but trivially small L.** ⇒ **recompute is a *capacity* tool (avoid storing cold KV at all), not a bus-saving one.** This refines the H3 card, which framed recompute-vs-refetch as an L*-sweep — the sweep only matters in the tiny-L fixed-overhead corner; asymptotically refetch wins. *(Where "spend FLOPs to dodge the bus" actually lives is Result 2, not recompute.)*

### Result 2 — the entire compression bet reduces to ONE measured number.
`t_cmp < t_raw` (ignoring the small α gap) iff `β_cmp < β_raw`:
```
k/(r·B_pcie) + k/B_dq  <  k/B_pcie
  ⇒  B_dq  >  B_pcie · r/(r−1)
```
- r = 2 (FP8): need `B_dq > 2·B_pcie ≈ 26 GB/s`
- r = 4 (INT4): need `B_dq > (4/3)·B_pcie ≈ 17 GB/s`
- r → ∞: need `B_dq > B_pcie ≈ 13 GB/s`

**So compression-over-the-straw wins iff the dequant kernel produces output faster than ~13–26 GB/s.** Isolated bit-unpack dequant runs at *hundreds* of GB/s — trivially clears it. **The whole question is whether, *under concurrent decode contention*, `B_dq` stays above the threshold.** That contended `B_dq` is the single number E1 must nail; it is the make-or-break of the compression idea, the asymmetric feed, and the "spend FLOPs" principle. *(This is why E1's headline figure must be the CONTENDED crossover, not the isolated one — Uncle's #1 sharpening.)*

### Result 3 — the asymmetric Card-1→Card-2 path is a different, worse number.
On Windows there is no GPU P2P, so card→card ≈ **two PCIe x8 hops + a host bounce** ⇒ effective `B_c2c ≈ B_pcie/2` or worse `[MEASURE]`. The asymmetric-feed economics use `B_c2c`, not `B_pcie` — E1 adds it as a fourth primitive. Card-1-as-feeder only beats host-staging if Card 1 *computes* on what it holds (prefill / draft / control), not if it's pure storage.

## 2. Admission model (the H2′ roofline / thrash knee)

Decode is bandwidth-bound and attention reads **all** resident KV each step, so per-step time scales with *total resident active KV*. For `N` concurrently-decoding sessions of avg KV `k̄·L̄`:

```
TBT(N) ≈ α_step + N·k̄·L̄ / B_vram
```
Aggregate decode throughput `N/TBT → B_vram/(k̄·L̄)` is **roughly constant in N** (bandwidth roofline — adding sessions doesn't raise aggregate tok/s). But per-session TBT grows linearly with N, so **goodput-under-SLO peaks at the largest N meeting the SLO:**
```
N*_bw = SLO_TBT · B_vram / (k̄·L̄)        (bandwidth knee)
N*    = min( N*_bw , capacity_limit )     (§3)
```
Admission control = cap concurrent decoders at `N*`; admit beyond it → thrash (TBT blows the SLO). **Caveat:** MLA / sparse attention shrink `k̄` per step and flatten this — which is why the v2 re-center grounds the claim on *session count*, and why N* must be measured per model, not assumed.

## 3. Commit-charge feasibility region (the real constraint — and a genuinely novel framing)

WDDM backs VRAM with system commit, so the binding constraint is **not** VRAM capacity but commit headroom (observed: 92% commit at 60% physical):
```
Σ_resident ( weights + KV + activations )  ≤  H   (commit headroom, NOT free RAM, NOT VRAM)
```
This is the feasibility region every admission/eviction decision lives inside. Capacity-limit in §2 is `H`, not VRAM. No datacenter paper models this (they're commit-rich) — it's an ownable contribution and the reason the north star is *system-RAM cost*.

## 4. Lifetime-class eviction objective (the W4/H4 spine)

Eviction minimizes total future materialization cost subject to §3:
```
minimize  Σ_blocks  P(reuse) · materialization_cost(block)     s.t. Σ resident ≤ H
```
where `materialization_cost` is the **min** of Results 1–3 for that block. **Bélády-MIN** (evict the block reused farthest in the future) is the offline optimum; **lifetime classes are an online approximation** that uses *reuse-provenance* (system / session / turn / one-shot / sink) as a predictor of reuse distance. **The class contract's entire value = how well provenance predicts reuse distance** — that is assumption (D), the make-or-break, tested by the H4 classes-ON/OFF ablation.

## 5. Corollaries → hypotheses (the model is falsifiable)

| Corollary (prediction) | Tested by |
|---|---|
| C1: refetch ≫ recompute on time; recompute is capacity-only | E1 (recompute arm) |
| C2: compression wins iff **contended** `B_dq > B_pcie·r/(r−1)` (~13–26 GB/s) | **E1 (headline)** |
| C3: card→card ≈ ≤½ `B_pcie`; asymmetric feed only pays if Card 1 computes | E1 4th primitive |
| C4: goodput-under-SLO peaks at `N* = min(N*_bw, H-limit)` | H2′ |
| C5: commit headroom `H`, not VRAM, is the feasibility wall | H2′ / observed |
| C6: classes beat TTL iff provenance predicts reuse-distance (assumption D) | H4 ablation |

Each is a number or a direction we commit *before* measuring. Where the measured curves **deviate** from this model (PCIe below theoretical x8, dequant memory-bound below some block size, contention nonlinearities, the prefill anomaly) — those deviations are the paper's findings.

## 6. Design substrate & the thin controller (the moving parts — kept few on purpose)

The whole runtime is a small, countable set of parts:
1. **Two cards, asymmetric roles** — Card 1 (states + light compute, e.g. prefill/feed), Card 2 (heavy compute, fed amortized). Exact roles set by E1's C3 number.
2. **A pinned deterministic arena** per card — fixed-size, max-residency, uniformly-blocked, with internal ring/bank rotation. *Inside it we are the memory manager; VidMm is locked out* (best-effort on Windows — the H1 probe measures how well the lock holds). Its determinism is what makes the constants above stop drifting.
3. **A closed-form controller** — the manager does very little: demand ("need more inference") → evaluate §1–§4 against the known limits (`N*`, `H`, the materialization crossover) → deterministic reaction (admit / defer / rotate / recompute-vs-refetch). No heuristic search; evaluated at admission/step boundaries (≈zero hot-path tax). Complexity didn't vanish — it **relocated** to (a) measuring the constants once (E1), (b) the lifetime-class *prediction* feeding the equations (assumption D / H4 — the residual intelligence), (c) the OS-boundary negotiation (co-management).
4. **`B_dq` is scheduling-dependent.** Result 2's threshold is recovered or lost by *how* dequant and decode are scheduled (copy-engine transfer vs compute-engine decode; separate queues; HAGS). Scheduling is a *knob/axis* in E1, not a new subsystem. The OS scheduler **VidSch** is VidMm's sibling — co-*scheduling* is the same co-management story, **measured, not separately built**.

## 7. Scope: we are bounding, not optimizing (keep it simple)

The deliverable is the **feasibility envelope** — the size/scaling *bounds* of local inference here — found with the *simplest* system that reveals them. Optimizations are known levers added **after** the idea is proven, only **if the use requires**:
- **Compression depth** — use only the quant we need anyway (FP8/INT4); defer sophisticated/learned compression. (Result 2 says the ceiling is the contended `B_dq`; richer compression just moves `r` — it improves the bound, it doesn't define it.)
- **Integrity / bit-checks (ECC-lite)** — deferred. Optional later: a periodic checksum of the *static* locked weights region, only if a long-running deployment needs it. KV rides un-checked (LLMs tolerate noise).
- **Asymmetric-feed elaboration** — start with the simplest split E1's C3 justifies; don't build the feed pipeline before the card→card number says it's worth it.

**Rule: no new moving part enters the core until E1's bounds say it's needed. Find the envelope first.**

**Contribution (one sentence):** *On memory-inverted, fabric-less GPUs the materialization decision inverts from the datacenter answer under compute contention, and **closed-form** admission control on this cost model — over a pinned deterministic arena, not heuristic paging — is sufficient to operate at the feasibility bound.*
