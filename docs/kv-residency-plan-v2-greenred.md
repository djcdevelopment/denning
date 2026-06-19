# v2 — Green/Red Re-Review (2026-06-19)

*Adjudicated output of an 8-agent green-team/red-team workflow (run `wf_2dcb17a3-60a`) over the REFINED project (hardware-concrete, MoE@128K, MLA ladder, llama.cpp substrate). Companion to [the original plan](kv-residency-comanagement-research-plan.md). Facts dated 2025–2026 / specific issue & arXiv numbers were web-surfaced by agents and **must be independently verified** before citing; several post-date the assistant's training cutoff.*

---

## Verdict: NET STRONGER than the original — contingent on 3 cuts + 1 re-center

The chair sided with **stronger-if-disciplined** (a judgment, not an average). Independently verified during the run: the MLA ~4 GB-at-128K math; ktransformers' 382 GB-DRAM + Intel-AMX requirement (inapplicable to a 16–18 GB-RAM box); real dual-B70 benchmarks (row-split SYCL-segfaults, layer-split ~4% *negative* for fitting models, decode bandwidth-bound & constant in context length); **B70 silicon = 608 GB/s GDDR6 (not 456), 22.94 TFLOPS FP32 / 367 INT8 TOPS (FLOP-modest)**; DeepSeek-V4 still 9.62 GiB KV at 1M; and that **no LLM-serving system co-manages against WDDM/VidMm** (uncontested).

**Three concrete gains over the original:** (1) one generative principle ("spend abundant on-card resources to avoid crossing the scarce bus") now *predicts* the whole design instead of five disconnected pillars; (2) the **RAM<VRAM inversion** is a genuinely under-studied regime no incumbent's assumptions cover; (3) a **within-one-box fractal portability proof** (same lifetime-class contract across VRAM→DRAM→NVMe→C:-disk) answers the original RQ5 gate more cheaply than a flaky cross-vendor substrate swap.

## The 1 re-center

**Anchor the headline on *many concurrent agent sessions on one card under desktop co-tenancy*, not single-agent + MLA.** The MLA self-undercut is real: rung-1 MLA → ~4 GB KV → ~6% of a 32 GB card → zero contention → trips the plan's OWN P0 headroom gate. Residency pressure is real at N-session co-tenancy and at the frontier (DeepSeek-V4 9.6 GiB at 1M), not at single-agent-short-context. Re-ground the admission claim on **session count, not context length** (sparse attention flattens per-step KV bandwidth across context).

## The 3 cuts

1. **DROP expert-residency as a standalone 6th wedge.** Occupied: FluxMoE (arXiv 2604.02715 — *decouples* experts, the opposite framing), MoE-ERAS, KTransformers (SOSP'25), MoE-Infinity, llama.cpp #20757 (tiered GPU/RAM/SSD expert cache w/ LRU/SLRU/LFU + admission-on-2nd-access, in our own engine). Keep ONLY as "one lifetime-class contract over both KV & experts, on a VidMm + RAM-inverted substrate" generalization-evidence.
2. **RETIRE frontier rung-2 (200B+) as a serving target → roofline stress test only.** ktransformers owns it but needs 382 GB DRAM + AMX → inapplicable here. Don't compete on MoE-engine throughput.
3. **DELETE the OS-for-KV framing.** Symphony (HotOS'25, "KVFS") and vAttention (ASPLOS'25, removing paging) pre-claimed/undermined it. Lead with VidMm substrate + roofline + RAM-inversion.

## The 4 tensions, resolved

| Tension | Resolution |
|---|---|
| **MLA self-undercut** | Red lands a real (non-fatal) blow. MLA demoted: contribution → *workload-feasibility enabler*. Relocate headroom to N-session co-tenancy. KV residency persists at frontier & N-session; dies only at single-agent-short. |
| **ktransformers / occupied niche** | Niche narrowed (Windows/VidMm + RAM-inversion, not "PCIe-only" broadly), but ktransformers' 382 GB-DRAM+AMX design is inapplicable & unborrowable here → cite as unbeatable-on-its-regime; retire rung-2 to stress test. |
| **32 GB-RAM vestigial DRAM tier** | Genuinely novel (both teams agree) but cuts both ways: weakens "evict idle KV to host hub" (can't evict 32 GB into 16 GB), strengthens recompute + roofline. Re-cast DRAM as thin spill-staging; **recompute-on-GPU = primary reclaim**; name "inverted-tier cascade" as a first-class eval axis. |
| **llama.cpp-as-substrate** | Red's sharpest finding: GGML allocator is **budget-blind** (#15120/#18946) → *no KV manager to hook*. VidMm contribution is a **from-scratch D3D12 residency backend**; custom harness is **mandatory**, P1 is the true risk. Net-fine & clarifying (more obviously non-absorbable). Engine choice right (only working Windows-Arc multi-GPU path); **pin/freeze the SYCL build** (3–4× version/quant throughput swings, #22413/#21517). |

## Updated wedge map

- **W1 (reinforced, on probation till P0):** VidMm/WDDM co-management — D3D12 residency backend mapping lifetime classes → `SetResidencyPriority`, reacting to `QueryVideoMemoryInfo` budget shrink via budget-change events (never per-step polling). Uncontested. *Involuntary-eviction premise unproven until P0 fires.*
- **W2 (ELEVATED to headline):** bandwidth-roofline admission control + recompute-vs-refetch cost model, re-grounded on concurrent-session count. Non-absorbable (NVLink labs: refetch always wins → never discovered the inversion).
- **W3 (novel, NAMED):** the RAM<VRAM inverted-tier cascade — host DRAM as scarce transit window, recompute as primary reclaim.
- **W4 (the spine, KEPT):** reuse-provenance lifetime-class contract; classes-ON/OFF ablation (must-run); fractal across tiers = within-one-box RQ5 proof.
- **W5 (DEMOTED → generalization-evidence):** KV+expert under one contract (cite FluxMoE/MoE-ERAS/KTransformers; claim only unify-on-OS-arbitrated-RAM-inverted-substrate).
- **W6 (DROPPED → stress test):** frontier rung-2 offload.
- **W7 (KEPT):** decode-stall-attributable-to-VidMm + per-class miss-ratio + ghost-list recompute-avoided regret telemetry.

## Corrections to the conversation's assumptions

- **B70 = 608 GB/s** (not 456) → steeper, more legible cliff (~19× vs PCIe).
- **B70 is FLOP-modest (22.94 TFLOPS)** → "recompute-beats-refetch / spend FLOPs to dodge the bus" may **invert back** to the datacenter answer on this silicon. MEASURE it; a negative result is the contribution.
- **llama.cpp has no KV manager / budget-blind allocator** → D3D12 residency backend is from-scratch; P1 is the real risk, not a plug-in.
- **32 GB RAM partially invalidates the DRAM-hub eviction story** → recompute is the primary reclaim path.

## Next move — P0 two-sided honesty test (BEFORE any D3D12 code)

One experiment on the real dual-B70 Windows box, instrumented llama.cpp (pinned SYCL build, `--split-mode layer`), settling 3 kill-gates + the 2 most-contested red claims:
- **(a) VidMm gate:** N concurrent/paused agent sessions on one 32 GB card (Qwen3-Coder-30B-A3B replica) → resident demand near the DXGI budget → launch adversarial desktop VRAM-hog → **measure whether VidMm involuntarily demotes the serving process's KV heaps + the decode-stall** (settles RQ1).
- **(b) recompute-inversion gate:** measure the **recompute-vs-refetch break-even** across prefix lengths on B70's 22.94 TFLOPS / 608 GB/s ratio (settles RQ4).

Every outcome informative; if a premise fails, that failure is publishable and the headline re-centers on N-session admission. **Do NOT write D3D12 residency-backend code until P0 says the problem is real.**

## Kill criteria (v2)

1. **P0 VidMm gate:** if VidMm does *not* involuntarily evict a foreground serving process's KV under an adversarial VRAM-hog (Microsoft's path is cooperative offer/reclaim) → drop co-management, stand on roofline-admission + RAM-inversion, or abandon if thin.
2. **P0 headroom gate:** if even at N concurrent sessions idle/reusable KV is a tiny fraction of resident → ~0 headroom → abandon (single-agent-MLA already fails this).
3. **P0 recompute-inversion gate:** if on-GPU recompute does not beat PCIe refetch on B70 → report bounded negative result; remove "spend FLOPs to dodge the bus" from load-bearing claims.
4. **Classes-ON/OFF gate:** if typed classes don't beat per-request TTL/per-block priority at rung-1.5 replica w/ N sessions under co-tenancy → narrow to co-management+admission or drop.
5. **6th-wedge gate:** if KV+expert unification can't be stated in a form FluxMoE/MoE-ERAS/KTransformers/#20757 can't → cut to generalization-evidence only.
6. **Substrate-noise gate:** if SYCL/Vulkan baseline can't be pinned tightly (3–4× swings) → single-digit-% policy deltas uninterpretable; fix the floor first.
7. **Absorption gate:** if anyone ships WDDM/VidMm co-management OR a published roofline-admission result on Windows-Arc before submission → pivot to residual open sub-problem or stop. (Web-confirmed empty as of June 2026.)

## Venue

Weak-reject at OSDI/NSDI as framed (can't supply OS-mechanism depth once VidMm is honestly demoted). **ATC / MLSys** for the built measurement-and-mechanism artifact; **HotOS** first for the position/early-result version ("Designing Inference for the Inverted Hierarchy" / "Don't Page Active KV"). Reserve ASPLOS/EuroSys for residency-mechanism depth only if P1 lands strongly.
