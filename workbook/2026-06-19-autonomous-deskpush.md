# Workbook — 2026-06-19 — Autonomous desk push toward G0

*Operator said "go as far as you can without me." This is the desk frontier — everything that doesn't need the operator's honest priors, the advisor's review, or the physical rig. Stopped cleanly at the G0 wall.*

## Done (this session, no GPU-hour)
- **Cost model** (`docs/cost-model.md`) — the analytical spine; R1 (refetch ≫ recompute → recompute is capacity-only), R2 (compression wins iff **contended `B_dq` > `B_pcie·r/(r−1)`** ≈ 13–26 GB/s — the whole bet in one number), R3 (card→card ≤ ½ PCIe), admission knee `N* = min(bandwidth, commit)`, commit-charge feasibility region, lifetime-class objective vs Bélády-MIN. Six corollaries → hypotheses.
- **Design consolidated + simplified** (cost-model §6/§7) — pinned deterministic arena; closed-form controller (complexity relocated to classification + OS-boundary); scheduling-dependent `B_dq` (VidSch co-scheduling sibling to VidMm co-residency); **scope = bounding, not optimizing**; compression-depth + bit-checks deferred.
- **E1 Prediction Card** (`prereg/E1-materialization-crossover.md`) — DRAFT, untagged; predictions derived from the cost model; contended-`B_dq` headline; fidelity gate; engine-instrumentation note; pre-committed pivot.
- **Citations web-verified** (agent) — all real, none hallucinated; **6 corrections applied** to `related-work/related-work.md`: Continuum = ICLR'26 *workshop*; KTransformers AMX *recommended-not-required* (DRAM argument stands); MoE-ERAS = "…*Selection*", ISCA'24 wksp; llama.cpp #20757 = *Issue*; **vLLM #27408 = B60-SIGABRT, not B70-TP (#41663 is the TP fault)**; **Denning PFF ≠ 1968 paper** (split: working-set 1968 / PFF 1970s) — fixed in README too. Added **CacheGen (SIGCOMM'24)** as the direct compression-arm prior art. Positioning one-liners vs KVBM/Symphony/kvcached/Continuum added.
- **Density docs** (Uncle's list): `docs/assumptions.md` (P5 — ranked; **D = the scariest: is reuse-provenance predictable?**), `docs/evaluation-matrix.md` (P4 — full RQ×workload×baseline×metric×ablation×gate table; flags H6 as the thin one), contribution sentence (P2, in README + cost-model).

## Verification highlights (for positioning)
- **KVBM is the closest incumbent** — but CUDA/fabric/datacenter, no closed-form admission, no VidMm co-residency. Our niche holds.
- **FluxMoE *decouples* experts** (arXiv 2604.02715, real) — the opposite of our *unify*; a contrast cite, not a threat.
- No single incumbent combines closed-form admission + VidMm co-residency + reuse-provenance classes on a fabric-less RAM<VRAM Windows/Arc box.

## The G0 wall (stopped here — needs the operator + advisor + rig)
- **Cannot do G0:** it needs *your* honest priors on the predictions, the advisor's review, and the 4 G0 parameters (uncle's role/cadence, hours/week, paper-vs-workbook, CUDA box?). I drafted predictions as starting points; **I did not tag them** — tagging is the integrity commitment and must be yours.
- **Cannot run any GPU-hour:** roadmap guardrail ("no GPU before G0") + the experiments need the physical dual-B70 rig. So I-1→I-4 are blocked on you.
- **Plumbing dry-run deferred (honestly):** a true capture→verdict→predicted-vs-actual dry-run needs the analysis pipeline, which is harness code best built post-G0; a fully-synthetic worked example adds little.

## Next (when you're back)
G0 with Uncle → finalize Part-B + E1 priors → tag `prereg-launch-suppositions` + `prereg-E1` → **I-1 safing watchdog** → **I-2 E1 run**. The desk half of Uncle's critical path is done; the repo is a clean, reviewed base.
