# Overarching Pre-Registration — denning

**STATUS: DRAFT — NOT YET BINDING.**
This file is committed as a scaffold. Every prediction marked `[DRAFT]` is a first-draft *prior* to be finalized by the operator and reviewed by the advisor at **Gate G0**. The pre-registration becomes binding only when git-tagged **`prereg-overarching`** after G0 sign-off. **No experiment may run against a hypothesis until that hypothesis's prediction is finalized and the tag is pushed.** Results files reference the tag; the commit-timestamp ordering is the integrity proof.

> How to read a prediction: each is *falsifiable*, carries a *quantitative threshold*, and states the operator's *honest prior confidence*. The point is not to be right — it is to be honest about what we expected before we looked. Several hypotheses below are **designed to possibly fail**; pre-registering forces us to report that.

Maps to wedges W1–W7 in [`docs/kv-residency-plan-v2-greenred.md`](../docs/kv-residency-plan-v2-greenred.md).

---

## H1 — VidMm involuntarily evicts a foreground serving process (W1 / RQ1)

- **Hypothesis (falsifiable):** Under an adversarial desktop VRAM-hog that drives the DXGI budget below the resident KV demand of N concurrent agent sessions on one B70, VidMm will *involuntarily* demote/evict ≥1 of the serving process's KV heaps, producing a measurable decode-stall — and a class-aware D3D12 residency policy reduces that stall vs a VidMm-naive baseline.
- **Mechanism:** WDDM virtualizes VRAM; the per-process budget (`QueryVideoMemoryInfo`) shrinks under contention and over-budget processes can be demoted to shared/system memory (the PCIe cliff).
- **Prediction `[DRAFT — operator to set, advisor to review @ G0]`:** involuntary demotion of ≥1 KV heap within ~2 s of the budget dropping below resident demand; TBT on affected sessions spikes ≥2× baseline (decode-stall ≥10% of a 10 s window). **Prior: ~50%** — genuinely uncertain. Microsoft documents the coexistence path as *cooperative* (offer/reclaim); a driver may protect a foreground compute process.
- **Confirm if:** measurable involuntary eviction AND stall ≥ threshold. **Refute if:** VidMm protects the process / stall < a few %.
- **Pre-committed pivot (if refuted):** demote co-management (W1) to a tested-and-reported secondary result; stand the program on W2 (roofline admission) + W3 (RAM<VRAM). *(This is one leg of the P0 two-sided test.)*

## H2 — Roofline admission on session count maximizes goodput (W2 / RQ2)

- **Hypothesis:** Goodput-under-SLO on one card is maximized by gating the **concurrent-decoding session count** to a roofline-derived ceiling N* (never paging active KV), and this beats a keep-resident + LRU-spill straw-man under overload.
- **Mechanism:** decode is HBM-bandwidth-bound; beyond N* the aggregate KV stream saturates bandwidth and TBT collapses (thrashing). Denning load control: admit to the working set, suspend the rest. *(Re-grounded on session count, not context length — sparse attention flattens per-step KV bandwidth in context length.)*
- **Prediction `[DRAFT]`:** an N* exists where goodput-under-SLO peaks; admission-gating to N* beats keep-resident+LRU by ≥20% goodput at 1.5–2× overload. **Prior: ~70%.**
- **Confirm if:** a clear goodput peak at a finite N* and a ≥ (threshold) win vs straw-man. **Refute if:** monotonic / no peak, or no win.
- **Pivot:** if no peak, the bottleneck isn't bandwidth-admission as modeled — re-examine the roofline model.

## H3 — Recompute-vs-refetch break-even on B70 (W2 / RQ4)

- **Hypothesis:** There exists a prefix length L* below which on-GPU recompute of a prefix's KV beats refetching it over PCIe.
- **Mechanism / back-of-envelope `[DRAFT — recompute the constants from measured kernel throughput before tagging]`:** per prefix-token, recompute ≈ `2·active_params / FLOP_rate`; refetch ≈ `KV_bytes_per_token / PCIe_BW`. For rung-1.5 (Qwen3-Coder-30B-A3B: ~3.3B active; ~49 KB/token FP8 KV) on B70 (assume ~100 TFLOPS *effective* with immature kernels; PCIe ~28 GB/s to host DRAM): recompute ≈ ~66 µs/tok vs DRAM-refetch ≈ ~1.75 µs/tok → **~38× favoring refetch.**
- **Prediction `[DRAFT]`:** **L* ≈ 0 against DRAM-refetch** — i.e., we predict recompute *loses* across the practical prefix range because B70 is bandwidth-rich/FLOP-modest. The design principle "spend FLOPs to dodge the bus" likely **inverts** on this silicon. Recompute's only plausible win is vs **NVMe-refetch** (~3–7 GB/s) or when the KV was never stored. **Prior: ~60% recompute loses to DRAM-refetch.**
- **Confirm if:** measured L* > a useful threshold (recompute wins for real prefixes). **Refute (= predicted) if:** L*≈0 vs DRAM.
- **Pre-committed framing:** if recompute loses, **that is the contribution** — a bounded negative result ("the datacenter recompute/refetch answer does NOT invert on commodity bandwidth-rich/FLOP-modest GPUs; here is the break-even and why"). Remove "spend FLOPs to dodge the bus" from the load-bearing claims and favor keep-resident + refetch. *(Second leg of the P0 two-sided test.)*

## H4 — Typed lifetime classes beat TTL / per-block priority (W4 / RQ3) — **the make-or-break ablation**

- **Hypothesis:** A typed reuse-provenance lifetime-class contract (system / session / turn / one-shot / sink) beats per-request TTL (Continuum-style) and per-block priority (KVBM-style) on goodput-under-SLO at rung-1.5, N-session co-tenancy.
- **Prediction `[DRAFT]`:** classes-ON beats classes-OFF (reuse-probability/TTL scoring kept) by ≥15% goodput-under-SLO at overload. **Prior: ~55%.**
- **Confirm if:** ≥ (threshold) and statistically robust over N≥5 runs. **Refute if:** within noise.
- **Pre-committed pivot:** if refuted, the typed contract is dressing — narrow the paper to co-management + admission (smaller paper) and report the null honestly.

## H5 — Inverted-tier cascade: recompute/keep-resident reclaim beats DRAM-warm-tier (W3)

- **Hypothesis:** In the RAM<VRAM regime, treating host DRAM as a thin spill-staging window (not a warm tier) and using keep-resident + admission (and recompute only where H3 says it wins) as the primary reclaim path beats the standard DRAM-warm-tier cascade that the offload literature assumes.
- **Prediction `[DRAFT]`:** the inverted-cascade policy beats a DRAM-warm-tier baseline by ≥ (threshold) goodput in the RAM<VRAM config; the advantage shrinks/reverses if RAM is artificially uncapped (the "real-32GB vs capped-DRAM" ablation). **Prior: ~60%.** *(Note dependency: if H3 says recompute loses, primary reclaim = keep-resident + admission, not recompute.)*
- **Confirm / refute / pivot:** as above; if no advantage, RAM<VRAM is a constraint to survive, not a design lever — report it as such.

## H6 — Fractal portability of the lifetime-class contract (W4 / RQ5)

- **Hypothesis:** The same lifetime-class contract drives sensible eviction across all tiers (VRAM → DRAM → NVMe → C:-disk) without per-tier special-casing — within-one-box portability evidence.
- **Prediction `[DRAFT]`:** one contract + one policy parameterization produces correct, non-degenerate eviction at every tier (qualitative + a portability metric: ≤ (threshold) per-tier special-case lines). **Prior: ~75%.**
- **Confirm / refute:** if a tier needs bespoke logic, the abstraction is leakier than claimed — document where and why.

---

### Cross-hypothesis notes
- **H3 ↔ H5:** the recompute-vs-refetch result gates whether recompute is a real reclaim path; H5's framing must follow H3's outcome.
- **H1 is on probation:** the whole VidMm/W1 wedge is conditional on H1; that is by design and is the first thing P0 settles.
- **Kill criteria** (full list) live in [`docs/kv-residency-plan-v2-greenred.md`](../docs/kv-residency-plan-v2-greenred.md) §"Kill criteria (v2)" and are mirrored into each Prediction Card's gates.
