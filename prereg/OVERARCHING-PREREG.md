# Overarching Pre-Registration — denning

**STATUS: TAGGED & BINDING — `prereg-launch-suppositions` (2026-06-19).** Advisor-lens G0 pass cleared 2026-06-19 (the "advisor" is a viewpoint the maintainer applies, not a third party). License: Apache-2.0.
Revised 2026-06-19 after auditing prior work in `D:\work\battlemage` + `D:\work\b70tools` (see [`../docs/prior-work-integration.md`](../docs/prior-work-integration.md)). That audit found several original hypotheses were **already observed** in pilot work — so this prereg is split:

- **Part A — Prior observations (EXPLORATORY).** Documented in prior pilot work. **Cited as prior evidence, NOT pre-registered as predictions.** Tagging these would be dishonest.
- **Part B — Confirmatory pre-registrations.** Genuinely untested. These get honest quantitative predictions, get git-tagged **`prereg-launch-suppositions`** after advisor Gate G0, and are the ones whose results are an honest unveiling.

> The one rule still holds for Part B only: predictions committed (tagged) before data. A refuted Part-B prediction is a success of the method. The pilot work is the exploratory phase that generated and calibrated these confirmatory hypotheses — a standard, honest research structure.

Maps to wedges W1–W7 in [`../docs/kv-residency-plan-v2-greenred.md`](../docs/kv-residency-plan-v2-greenred.md).

---

## G0 LOCK (2026-06-19) — what this tag covers

- **Advisor-lens methodology pass:** cleared. (The "Uncle"/advisor critic is a viewpoint the maintainer applies, not a third party.) The pre-registration split, baselines (verdict-as-oracle), and noise discipline were reviewed → sound.
- **Already MEASURED ahead of G0 (predictions-first):** R1/R2/R3 (cost-model) and **H2′** (decode roofline + N-session) are confirmed — predictions git-committed (`1118d0c`) **before** the data (`2d19b09`+); see [`../results/E1-SUMMARY.md`](../results/E1-SUMMARY.md). **Cited as confirmed, NOT re-tagged here** (tagging an already-observed result would be dishonest). H2′'s exact `N*` knee is noise-limited → pending averaged runs.
- **TAGGED as forward confirmatory predictions (genuinely untested):** **H1′, H4, H5′, H6.** These are what `prereg-launch-suppositions` locks before their experiments run.
- **Locked SLO** (the goodput-under-SLO bar for H2′/H4/H5′): a session "meets SLO" iff **TTFT ≤ 2 s AND TBT p95 ≤ 50 ms** (~20 tok/s sustained — interactive-coding feel). Goodput = number of concurrent sessions meeting SLO.
- **H4 make-or-break bar** (set from the measured noise floor): single-run throughput varies ~20–30% ([`../results/E1-Nsession-scaling-20260619.md`](../results/E1-Nsession-scaling-20260619.md)), so the bar is set **above** that band — classes-ON beats classes-OFF by **≥20% goodput-under-SLO**, over **≥10 averaged reps/condition**, **95% CI excluding zero**. A smaller real effect is reported as "below the resolvable bar," not a win.

---

## PART A — Prior observations (exploratory; cite, do NOT pre-register)

- **A1 — The shared-memory spill cliff is real and characterized.** `-fit on` 70B → host RAM 21→1.1 GB, *audible audio chop*, a 70 s prompt hanging past 20 min; a live **6.23 GB** `non_local` spill caught by the PDH cross-process counter. *(battlemage `arc-b70-dual-70b-windows-vulkan.md`; b70tools `retrospective-wow-realtime-inference-impact-overnight-2026-06-16.md`.)*
- **A2 — Per-model throughput constants** (dual B70, Vulkan, Q4): 70B 188/11.6 t/s; **Qwen3-30B-A3B MoE 30.1 prefill / 81.7 decode**; 32B 242/20.7; Mistral-24B(1 card) 428.9/27.3; 14B(1 card) →1254 prefill / 45 decode. *(b70tools `docs/findings-*.md`; battlemage `bench-2026-05-24/*.jsonl`.)*
- **A3 — Long-context decode collapse is the Vulkan attention kernel, not spill; SYCL is 3.5× faster.** 32B @ 25k: 4.2 t/s Vulkan vs 14.47 t/s SYCL, with *no spill* present. *(b70tools `retrospective-bsod-fix-and-sycl-unlock-2026-06-18.md`.)*
- **A4 — The binding host wall is commit charge, not free RAM** (92% commit at 60% physical). *(b70tools overnight retro + README.)*
- **A5 — Single-card x16 beats dual-card x8/x8-split for models that fit one card**; concurrent dual-card inference shows ~−27% activity + 6× Vulkan init contention (not compute-bound). *(b70tools `findings-both-cards-concurrent-mistral24b-1.md`.)*

These motivate Part B; they are not claims denning gets to make as discoveries.

---

## PART B — Confirmatory pre-registrations (to be tagged)

### H1′ — Game-induced *involuntary* VidMm eviction of a model that FITS (W1 / RQ1)
- **Hypothesis:** When a model that fits comfortably in one card's budget is serving, and a GPU-heavy game/desktop app then runs on the same card, VidMm involuntarily shrinks the serving process's DXGI budget and demotes its KV/weights to shared memory, causing a measurable decode-stall AND/OR game frame-pacing impact.
- **Why untested:** the one prior WoW co-tenancy run captured **no frame-times** (no PresentMon) and did **not** spill (A1's spills were self-induced over-allocation). The *fitting-model + game-induced-eviction + frame-pacing* chain is open.
- **Prediction `[LOCKED @ G0 2026-06-19]`:** game launch drives a fitting serving process to involuntary demotion (PDH `non_local` rises ≥1 GB) within ~5 s; decode-stall ≥2× TBT on affected steps; game frame-time p99 degradation beyond the b70tools no-harm budget (p99 +5%). **Prior: ~50%.**
- **Confirm / refute / pivot:** confirm = measured involuntary demotion + stall/frame impact; refute = VidMm protects the foreground app and stalls < few % → demote W1 to a tested secondary result, stand on H2′/H5′.

### H2′ — Concurrent-session goodput roofline / thrash knee (W2 / RQ2) — MEASURED ✅ (see E1-SUMMARY; not re-tagged)
- **Hypothesis:** Goodput-under-SLO peaks at a finite concurrent-decoding **session count N***; admission-gating to N* beats keep-resident + LRU under overload. *(No slots-vs-goodput sweep exists in prior work — only 1–2 process contention.)*
- **Prediction `[MEASURED ✅ — see E1-SUMMARY; N* noise-limited]`:** a goodput peak exists at finite N*; gating to N* beats a no-admission baseline by ≥20% goodput at 1.5–2× overload. Gate on **commit headroom** (per A4), not free RAM. **Prior: ~70%.**

### H3′ — VRAM bandwidth, PCIe rate, and recompute-vs-refetch (W2 / RQ4) — MEASURED ✅ (R1/R3 in E1-SUMMARY; not re-tagged)
- **Hypothesis:** A prefix-length break-even L* exists below which on-GPU recompute beats PCIe refetch; predicted small on B70 (bandwidth-rich, FLOP-modest). *(Throughput constants are observed [A2]; GB/s VRAM-BW, GB/s PCIe, and the recompute/refetch comparison are NOT.)*
- **Calibrated prediction `[MEASURED ✅ — R1/R3 in E1-SUMMARY]`:** ground recompute cost in the **measured** prefill rate (e.g. Qwen3-30B-A3B ~30 t/s prefill on Vulkan — *re-measure on the frozen build, ideally SYCL per A3*), refetch cost in **measured** PCIe GB/s (x8/x8 — re-measure; never benchmarked). Predict **L*_dram ≈ 0** (refetch wins) given the FLOP-modest silicon; finite L*_nvme. **Prior: ~60% recompute loses to DRAM-refetch.** A confirmed negative is the contribution.

### H4 — Typed lifetime classes beat TTL / per-block priority (W4 / RQ3) — make-or-break
- **Hypothesis:** A typed reuse-provenance lifetime-class contract beats per-request TTL and per-block priority on goodput-under-SLO at rung-1.5, N-session co-tenancy. *(Entirely absent from prior work — b70tools has no lifetime/reuse concept.)*
- **Prediction `[LOCKED @ G0 2026-06-19]`:** classes-ON beats classes-OFF by **≥20% goodput-under-SLO** at overload, **≥10 averaged reps/condition, 95% CI excluding zero** (bar set above the measured ~20–30% single-run noise). SLO = TTFT ≤ 2 s AND TBT p95 ≤ 50 ms. **Prior: ~55%.** Refute → narrow to admission-only.

### H5′ — 125k-context MoE single-card shared-memory-spill experiment (W3)
- **Hypothesis:** At 125k+ context the Qwen3-30B-A3B KV exceeds one card's budget and spills to shared memory with a quantifiable cost; inverted-cascade handling (keep-resident + admission; recompute only where H3′ allows) beats naive spill. *(The cliff [A1] is observed; this specific run is **planned, never executed** — prior `c65536`/`c131072` overnight JSONL files are empty of results.)*
- **Prediction `[LOCKED @ G0 2026-06-19]`:** at f16 KV the single-card config spills ~2–3 GB at 131072 ctx (per the plan doc's own estimate) with a measurable decode penalty; q8 KV (~6.3 GiB) fits and avoids it. **Prior: ~65%.** *(These predictions originate in `b70tools/docs/plan-vulkan-moe-125k-shared-memory-2026-06-18.md` — cite as the prediction's source.)*

### H6 — Fractal portability of the lifetime-class contract (W4 / RQ5)
- **Hypothesis:** one lifetime-class contract drives sensible eviction across VRAM → DRAM → NVMe → C:-disk without per-tier special-casing. *(Untested.)*
- **Prediction `[LOCKED @ G0 2026-06-19]`:** one parameterization, non-degenerate eviction at every tier; ≤ (threshold) per-tier special-case lines. **Prior: ~75%.**

---

### Cross-notes
- **Engine is now a first-class variable** (A3): run the confirmatory experiments on the **frozen SYCL build** where it wins (long-context decode), Vulkan where it wins (cold-load / multi-GPU layer-split) — and report which.
- **Instrumentation:** consume b70tools (`pdh_gpu_memory`, `host_memory`, `verdict --json`); bind by PCI-BDF; gate on **commit headroom** (land the b70tools commit-gate TODO first). See `../docs/prior-work-integration.md`.
- **H3′ ↔ H5′** depend on the recompute-vs-refetch outcome; sequence H3′ first.
