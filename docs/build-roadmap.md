# Build Roadmap — incremental build → test → document → publish

*The operative execution order. Instantiates the staged methodology in [`research-program-plan.md`](research-program-plan.md) §3 with the 4-lens resequencing (test cheap/bankable first, risk last) and the simplified core from [`cost-model.md`](cost-model.md) §6–§7. Bounds-first: each increment is the smallest unit that yields a documented, publishable result. No new moving part enters until the bounds require it.*

## The per-increment loop (every increment, no exceptions)

`PREREG (prediction card, git-tagged, BEFORE data)` → `BUILD` → `RUN on the rig (pre-flight checklist + watchdog armed)` → `RESULTS doc + manifest + figure` → `WORKBOOK entry` → `ADVISOR gate` → feeds a `PUBLISHABLE unit`.

Division of labor: I scaffold harnesses, draft prereg cards, write the cost-model math and the results/analysis + figures; the GPU runs happen on the rig (your hands, or a session at the box) and feed back numbers I document. Honesty rule holds throughout: **predictions are tagged before data; a refuted prediction is a success.**

---

## Phase 0 — Desk (no GPU-hour). *In progress.*

- **Done:** cost model (the equations), design substrate (§6: arena + closed-form controller), scope (§7: bounds-not-optimum; compression/bit-checks deferred), contribution sentence.
- **Next (desk):** (1) the **E1 Prediction Card** — derive predicted `L*`, the contended-`B_dq` threshold (~13–26 GB/s), the decompression-fidelity gate, and the engine-instrumentation note; (2) the **pre-G0 plumbing dry-run** — run capture → `verdict --json` → predicted-vs-actual on *existing* prior data (WoW / 70B-spill JSONL), producing a clearly **non-binding** worked-example results doc that de-risks the analysis apparatus.
- **Gate G0 (advisor):** ratify methodology + the prereg numbers + the resequencing + baselines (incl. **verdict-as-oracle**) + scope cuts + venue/HotOS; settle the 4 G0 parameters; **tag `prereg-launch-suppositions`**. **No GPU-hour before G0.**

## I-1 — Operational foundation (safing watchdog + rehearsal)
- **Build:** pure-observer safing watchdog consuming b70tools signals (AdapterState→PostTDR/Lost = abort; `verdict` spill-ceiling / commit > 90% = safing); pre-flight checklist tooling.
- **Test:** failure-mode rehearsal — induce a controlled spill, observe/simulate a TDR, kill telemetry mid-run; confirm each is *caught* and that "data missing" is detectable. **Gate:** watchdog catches each before it becomes loss-of-vehicle.
- **Document:** validated runbook + watchdog-log format; workbook entry.
- **Publishes to:** methods/repro appendix. (Prerequisite that lets every later increment run unattended safely.)

## I-2 — E1: materialization-cost crossover (the physics de-risk; the headline)
- **Build:** the three primitives (PCIe-x8 transfer bench; dequant-kernel bench per scheme; prefill bench) + the **scheduling axis** (copy-engine vs compute-engine, separate queues, HAGS on/off) + the **card→card** 4th primitive. Python/torch-xpu prototype for shape → SYCL/Vulkan port for citable numbers.
- **Test:** the E1 Prediction Card. Confirm/refute cost-model **R1** (refetch ≫ recompute), **R2** (compression wins iff *contended* `B_dq` > threshold), **R3** (card→card ≤ ~½ PCIe), and the scheduling-dependence. **Isolated → under-load (contended `B_dq` is the headline figure).** **Gate:** predictions hold, or the deviations are characterized.
- **Document:** the crossover scatterplot(s) isolated-vs-contended; predicted-vs-actual; the measured constants (the `[MEASURE]` set → values).
- **Publishes to:** **HotOS position-paper core figure.** I-1 + I-2 + the cost model = the **minimal publishable result** (a paper even if everything downstream fails).

**Gate G1 (advisor):** review E1; proceed/pivot. → draft + submit the HotOS position paper.

## I-3 — Pinned deterministic arena (the substrate) + H1 lock-respect
- **Build:** fixed-size, max-residency, uniform-block arena with internal rotation, on one card (D3D12 `MakeResident`/`SetResidencyPriority`).
- **Test:** the H1 Prediction Card — run the adversarial desktop VRAM-hog against the *locked* arena; measure whether VidMm involuntarily evicts it; PresentMon for the frame-pacing half (on Vulkan, where PDH sees). **Gate:** does the lock hold / is the eviction premise real? (If not → demote co-management, per the pre-committed pivot.)
- **Document:** the lock-respect / VidMm-co-residency result; workbook.
- **Publishes to:** the VidMm co-management section of the full paper.

## I-4 — Closed-form controller + lifetime-class contract + admission (the spine)
- **Build:** the thin closed-form controller (equations → admit / defer / rotate) + the lifetime-class classifier + N-session admission, over the arena.
- **Test:** **H4 classes-ON/OFF ablation** (make-or-break — typed contract vs per-request TTL vs the verdict-as-oracle baseline) + **H2′** the goodput knee `N* = min(bandwidth, commit)`. **Primary metric: goodput-under-SLO per GB of system RAM** (the north star). **Gate:** classes beat the baselines by the pre-registered margin, or narrow to admission-only.
- **Document:** the ablation + the `N*` knee + the goodput-per-GB-system-RAM curves.
- **Publishes to:** **ATC/MLSys full-paper core.**

**Gate G2 (advisor):** review the spine; assemble + submit the full paper.

## I-5 (conditional) — Asymmetric two-card feed
- Only if E1's **C3** (card→card) number justifies it. **Build:** Card-1-feeds-Card-2 split (prefill / draft / control on Card 1). **Test:** asymmetric vs single-card replica on goodput-per-GB-system-RAM. **Publishes to:** multi-card extension.

## I-6 (stretch / deferred) — H6 fractal portability, compression depth, bit-checks
- Parked per §7. Enter only if the bounds say a lever is worth it.

---

## Publishing along the way
- **HotOS position** assembles from I-1 + I-2 (the inverted-substrate crossover, isolated vs contended). Offensive, not defensive — bank it early for community feedback.
- **ATC/MLSys full** assembles from I-3 + I-4 (arena + closed-form admission + the classes ablation + the `N*` knee), with the AE artifact.
- **OSS + artifact-evaluation bundle** (b70tools traces + the harness) in parallel — gated on the license decision + a rig-identity field-scrub.
- Re-run the **absorption web-check** at G0, G1, G2 and pre-submission.

## Guardrails (so it stays simple)
- **Program abort criteria** (numbers set at G0): if both the eviction premise (H1) and the compression win (E1/R2) fail → ship the I-1/I-2 characterization and stop.
- **No new moving part** until E1's bounds require it. Deferred levers (compression depth, bit-checks, asymmetric feed) stay deferred.
- **Find the envelope first.** The deliverable is the feasibility *bound*, with the simplest system that reveals it.

## Immediate next 3 desk actions
1. Draft the **E1 Prediction Card** (predictions derived from `cost-model.md`).
2. Run the **pre-G0 plumbing dry-run** on existing data → non-binding worked example.
3. **G0** with Uncle → tag the prereg → I-1.
