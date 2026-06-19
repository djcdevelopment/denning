# Research Program Plan — Honest, Gated, Peer-Reviewable Execution

*The PROCESS layer for the infexp project. The technical approach is settled in [the original plan](kv-residency-comanagement-research-plan.md) and [the v2 green/red re-review](kv-residency-plan-v2-greenred.md); this document governs HOW we run it as research that survives peer review — for a first-time researcher with an MIT applied-AI advisor ("Uncle") in the loop. Bring this to Uncle at Gate G0; it is designed to be amended by his review ("anything else he wants" plugs in there).*

---

## 0. The one rule that makes this research instead of demo-ware

**Predictions are committed before data is collected. No exceptions.** Every experiment is preceded by a *Prediction Card* (below) that is git-tagged, pushed (public timestamp), and acknowledged by Uncle with a date. Results live in a separate file committed *after*, opening with a predicted-vs-actual table. The git history is the integrity proof: it is physically impossible to retrofit a prediction to a result. This is what "honest unveiling" means operationally, and it is the difference between a finding and a rationalization.

A corollary you must internalize: **a refuted prediction is a success of the method, not a failure of the project.** Several of our hypotheses are designed to possibly fail (the red team showed VidMm may never evict, and recompute may lose on FLOP-modest B70). Pre-registering forces us to *report* those honestly, and on this project a clean negative result is publishable (see §8).

---

## 1. The honesty engine: pre-registration & unveiling protocol

For each stage:
1. **Write the Prediction Card(s)** — falsifiable hypothesis + a *quantitative* prediction with your honest prior, the exact protocol, the analysis plan, and the pass/kill thresholds.
2. **Commit + tag + push** (`prereg-P0`, `prereg-P1`, …). Send to Uncle; record his dated acknowledgment. *(Optional max-rigor: post the prereg's SHA-256 publicly before running — for public-workbook credibility.)*
3. **Run / build. Do not touch the prereg.**
4. **Record results** in `results-P<n>.md`, referencing the prereg tag, opening with the predicted-vs-actual table; discuss every deviation.
5. **Assemble the Advisor Packet (§5), hit the Gate, decide PROCEED / PIVOT / STOP.**

### Prediction Card template
```
# Prediction Card — <Stage/Exp ID>            [prereg tag: prereg-XX]
Committed: <YYYY-MM-DD>   Advisor ack: <date | pending>
Maps to: <hypothesis Hn / wedge Wn / RQn>

HYPOTHESIS (falsifiable, one sentence):
MECHANISM (why we expect it):
QUANTITATIVE PREDICTION (direction + threshold + your prior confidence %):
   e.g. "VidMm involuntarily evicts >=1 KV heap within 5 s of budget shrink;
         decode-stall >= 10% of TBT. Prior: ~55% it fires."
MEASUREMENT PROTOCOL (exact): instrument, pinned config (SYCL build hash,
   model hash, quant, seeds), procedure, N>=<k> runs.
ANALYSIS PLAN: metric formula, report P50 & P99, CI method, baseline +
   measured noise floor.
PASS GATE:  <proceed if ...>
KILL/PIVOT GATE: <stop or pivot to <X> if ...>
PRE-COMMITTED PIVOT: if refuted, we do <...> (decided NOW, not after).
```

---

## 2. Hypotheses (falsifiable; each pre-registered before its stage)

| ID | Claim (one line) | Wedge/RQ | Designed-to-possibly-fail? |
|----|------------------|----------|----------------------------|
| **H1** | Under co-tenancy shrinking the DXGI budget below N resident sessions' KV demand, VidMm *involuntarily* evicts the serving process's KV heaps, causing measurable decode-stall; a class-aware D3D12 residency policy reduces it vs VidMm-naive | W1 / RQ1 | YES — VidMm may protect a foreground compute process |
| **H2** | Goodput-under-SLO on one card is maximized by gating concurrent **session count** to the bandwidth roofline (never paging active KV), beating keep-resident+LRU-spill | W2 / RQ2 | partially |
| **H3** | A prefix-length break-even L* exists below which on-GPU recompute beats PCIe refetch on B70 | W2 / RQ4 | YES — FLOP-modest B70 may push L*→0 (refetch always wins) |
| **H4** | A typed reuse-provenance lifetime-class contract beats per-request TTL and per-block priority on goodput-under-SLO (the classes-ON/OFF ablation) | W4 / RQ3 | YES — the make-or-break |
| **H5** | In RAM<VRAM, recompute-as-primary-reclaim + thin-DRAM-spill beats the standard DRAM-warm-tier cascade | W3 | partially |
| **H6** | The same lifetime-class contract governs eviction sensibly across VRAM→DRAM→NVMe→disk (within-one-box portability) | W4 / RQ5 | no (existence/quality claim) |

---

## 3. Staged plan — each stage: prereg → run → results → gate → publishable unit

| Stage | Tests | Effort* | Publishable unit produced |
|-------|-------|---------|---------------------------|
| **S0 — Setup & methodology** | — | 1–2 wk | Repo + workbook scaffold + **overarching prereg** + verified related-work; **Gate G0 = Uncle blesses methodology before any spend** |
| **S1 — P0 two-sided honesty test** | H1, H3 | 3–4 wk | Characterization workbook; HotOS-style position draft. **Gate G1** |
| **S2 — D3D12 residency backend** (only if G1 says the problem is real) | H1 (mechanism) | 4–6 wk | VidMm-cooperative-vs-naive result. **Gate G2** |
| **S3 — Lifetime-class contract + admission + killer ablation** | H2, H4 | 4–5 wk | The classes-ON/OFF result (make-or-break). **Gate G3** |
| **S4 — Telemetry + inverted-tier cascade** | H5, H6 | 3–4 wk | RAM<VRAM eval + telemetry; fractal-portability evidence. **Gate G4** |
| **S5 — Full eval, artifact packaging, write-up** | all | 4–6 wk | Submission + reproducible artifact (AE-ready). **Gate G5** |

\*Effort = weeks of *focused* work, not calendar time. Set real dates with Uncle once your hours/week are known.

Each gate can return STOP/PIVOT; the pre-committed pivots (§1) mean a stop is a clean, documented landing, not a collapse.

---

## 4. Reproducibility & peer-review standard (every result carries this)

A result is not "done" until it ships a **manifest**: exact git commit; pinned SYCL/Vulkan build hash; model name + file hash + quant; all flags/env (incl. cache-redirect to D:); seeds; raw data (CSV/JSON); the analysis notebook; and a `REPRODUCE.md`. Public workbooks = these committed *as you go*, dated. Design for **Artifact Evaluation** from S0 (many systems venues award an AE badge; a first author with a clean artifact is taken far more seriously).

**Statistical rigor (non-negotiable):** N≥5 runs per condition; report **P50 and P99, never just the mean**; confidence intervals; and the **measured baseline noise floor** on a *frozen* build (the red team's substrate-noise gate — SYCL throughput swings 3–4× by version, so single-digit-% policy wins are meaningless without a pinned baseline). Report effect sizes, not just "it's faster."

---

## 5. Advisor (Uncle) protocol — leverage him at the front and at gates

Use him where an expert adds the most: **methodology up front (G0)** and **go/no-go at gates** — *not* as a last-minute paper proofreader. Review is **event-driven at gates**, so it adapts to his availability (more if he wants; the packets are always ready).

### Advisor Review Packet (one per gate)
```
# Advisor Packet — Gate G<n>
1. PRE-REGISTERED: <prereg tag + the quantitative prediction>
2. WHAT WE DID: protocol + any deviations (and why)
3. WHAT WE FOUND: predicted-vs-actual table, plots, stats, noise floor
4. DECISION REQUESTED: PROCEED / PIVOT / STOP — our recommendation + reasoning
5. QUESTIONS FOR YOU: <3–5 sharp ones>
6. COST OF PROCEEDING: next stage's effort (so the call is informed)
```

### Where Uncle will most want to push (tee these up for him)
- Are the hypotheses **falsifiable** and the predicted thresholds **honest** (not gimmes)?
- Are the **baselines fair and strong** (vLLM/llama.cpp native, Continuum-TTL, KVBM-style priority, the keep-resident+LRU straw-man) — no strawmen?
- Is the **statistical plan** sound (runs, CIs, noise floor)?
- Is the **novelty delta** correctly positioned vs *verified* 2026 prior art (FluxMoE, KTransformers, Symphony, vAttention)?
- Is the **scope sane for a solo first-timer** (he will likely cut — let him; the red team already did)?

---

## 6. Baselines, metrics, ablations (the comparative spine)

- **Baselines:** keep-resident + LRU/TTL spill (straw-man floor); llama.cpp native; Continuum-style per-request TTL; KVBM-style per-block priority. On a CUDA box (if available) KVBM itself, to show "ties on fast fabric, wins on fabric-less."
- **Primary metric:** goodput-under-SLO (requests/s meeting a TTFT+TBT target) at N concurrent sessions. **Secondary:** decode-stall-attributable-to-VidMm-eviction; recompute-vs-refetch break-even L*; per-class miss-ratio; HBM-hours; per-decode-step policy overhead (must show <1%).
- **Must-run ablation:** classes-ON vs classes-OFF (H4). If it doesn't move goodput, the typed-class contribution falls and the paper narrows — and we *report that honestly*.

---

## 7. Threats to validity (living section — add as you find them)

Single-box / single-vendor generalization; substrate noise (pinned-build mitigation); model-staleness of the rung-1 anchor; VidMm behavior varying by driver version; benchmark realism (use ShareGPT/WildChat/agentic traces, not synthetic). Each gets a sentence on how we mitigate or bound it.

Added from the 4-lens review (2026-06-19):
- **T2 — synthesized workloads.** The adversarial VRAM-hog and the agent-session load are operator-synthesized; state how they map to a real co-tenancy distribution (game + IDE + N agents) or bound the artificiality.
- **T3 — measurement-instrument perturbation.** The P0 harness's own polling/logging must be shown NOT to perturb TBT (report harness overhead the way b70tools reports its ~16.6 MiB / <130 ms footprint).
- **T4 — single-operator / single-window drift.** Driver/thermal/background drift across a multi-week solo campaign → mitigate by **interleaving conditions within a session** (A,B,A,B…), not all-of-A-then-all-of-B (REPRODUCE.md flight rule 8).
- *(T1 — pre-registering the SLO threshold — touches the prereg; it's in the G0 decision list, not here.)*

---

## 8. Path to publication & the minimal publishable result

- **Minimal publishable result (define now, de-risks everything):** the **S1/P0 characterization alone** — "the inverted-hierarchy (RAM<VRAM, fabric-less Windows-Arc) regime, and the measured VidMm-eviction + recompute/refetch behavior the datacenter literature assumed away" — is a **HotOS/workshop paper even if every downstream stage fails.** You have a paper after Stage 1.
- **Artifact ladder:** S1 → HotOS/workshop position; S3+ → ATC or MLSys (measurement + mechanism, with the AE artifact); ASPLOS/EuroSys only if S2/S4 mechanism depth lands. **Not** OSDI/NSDI as framed (per v2).
- **OSS in parallel:** the lifetime-class telemetry + a roofline admission policy as upstream llama.cpp/vLLM PRs (the only credible adoption path; "merged + cited," not "install my daemon").

---

## 9. Parameters to calibrate with Uncle at G0 (assumptions until then)

1. **Uncle's role & cadence** — advisor vs co-author? gate-only review (assumed) or more? (Co-authorship changes nothing about the honesty protocol; it does change the writing/credit plan.)
2. **Your time budget** — hours/week → turns the effort estimates into real dates.
3. **Primary target** — peer-reviewed paper vs public workbooks first (the plan serves both; the bar differs).
4. **Compute beyond the dual-B70 box** — does Uncle have a CUDA machine/students for the portability arm (H6 cross-substrate), or do we lean on the within-one-box fractal proof?

---

## 10. The immediate next three moves

1. **Stand up S0:** repo + workbook scaffold + the overarching prereg (H1–H6 with honest predicted numbers) + verify the 2026 citations.
2. **Write the P0 Prediction Cards** (H1 + H3) with quantitative predictions — *before* running anything.
3. **Gate G0 with Uncle:** send him this plan + the overarching prereg + the P0 cards. Get methodology blessed (and amended) **before spending a single GPU-hour.** That is the highest-leverage hour in the whole program.
