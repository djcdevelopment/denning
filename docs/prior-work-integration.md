# Prior-Work Integration — battlemage + b70tools

*denning does not start from zero. Two prior repos on the same rig already built much of the observation layer and ran extensive pilots. This document maps that work, sets the integrity split (what's already observed vs what denning will pre-register), and records the corrections the prior data forces. Source: a 3-agent read-only audit of `D:\work\b70tools` and `D:\work\battlemage` (2026-06-19).*

---

## 1. Where results live (the storage map)

| Source | Path | Format | Key fields |
|--------|------|--------|-----------|
| **b70tools telemetry** | `b70tools/runs/<name>/events.jsonl` (gitignored) or `b70tools/eval/runs/<cfg>/telemetry/events.jsonl` (+ `schema.json` sidecar) | delta-suppressed compact JSONL v1, **1 Hz**, 30 s full-snapshot heartbeat; 7 event kinds (`ms` MetricSample, `ai`, `ast`, `dr`, `seb`, `drf`, `car`) | MetricSample: `n` name, `a` adapter, `v` value, `u` typed Unit, `s` source, `o` observation_kind, `f` confidence, `t` QPC ts |
| **b70tools eval** | `b70tools/eval/runs/<model>-<quant>-<YYYYMMDD>-<HHMMSS>/` | `manifest.json` + `round-N/prompt-M.md` + `verdicts/*.json` | manifest: model/flags/per-round timings (`prompt_per_second`, `predicted_per_second`, tokens); verdict: host-mem + per-adapter VRAM gate |
| **battlemage bench** | `battlemage/bench-2026-05-24/*.jsonl` | **`llama-bench` JSONL, UTF-16LE, with a PowerShell stderr banner prepended** (parse accordingly!) | `avg_ts`/`stddev_ts` (tok/s), `n_prompt` xor `n_gen`, `tensor_split`, `type_k`/`type_v`, `model_size`; ctx + KV-quant encoded in **filename** |
| **battlemage intel_ollama** | `battlemage/intel_ollama/results/benchmarks/<id>/runs.jsonl` + `summary.md` | per-rep JSONL | `eval_tokens_per_s`, `wallclock_s`, `gpu_runner_mb`, `gpu_dedicated_top_mb` |
| **Master run index** | `b70tools/b70tools_5_28_repo_status.md` §4–5, §9–10 | md | every run + timing/throughput/thermal tables + doc index |

**Telemetry sources (b70tools collectors → what they emit):**
- `pdh_gpu_memory` → **cross-process** per-adapter `vram.local.bytes_committed` + `vram.non_local.bytes_committed` (the spill-to-shared signal Task Manager shows; LUID-bound). **The VidMm co-residency signal.**
- `dxgi_query_video_memory` → **per-process** `vram.local.budget_bytes` / `current_usage_bytes` (+ non_local).
- `vulkan_memory_budget` → per-process heap budgets; `gpu.rebar_active`, `gpu.cpu_visible_vram_bytes`.
- `igcl_power_telemetry` → voltage/freq/temp/energy/bandwidth counters (top-slot card emits some bogus values → flagged by arbitration).
- `host_memory` → `host.memory.*` and **`host.commit.*`** (the true wall — see §3).
- `d3dkmt_query_statistics` → **non-functional on Win10 19045** (`INVALID_PARAMETER`); PDH is the working cross-process path.

---

## 2. b70tools is denning's instrumentation substrate (consume, don't rebuild)

b70tools is a **passive, do-no-harm observability instrument** (zero GPU allocations, <50 MiB RSS, 1 Hz; held to 16.6 MiB / <130 ms init) built for the exact denning environment (2× Arc Pro B70, Ryzen 9 5900X, 32 GB DDR4, Win10 19045, PCIe 4.0 x8/x8, fabric-less, RAM<VRAM). It already provides:

- The cross-process VRAM/spill signal (`pdh_gpu_memory`), per-process budget (`dxgi`), host commit (`host_memory`).
- LUID/PCI-BDF **identity reconciliation** proven to survive adapter-id drift (bind on **PCI-BDF, never `vk:N`/LUID**).
- An AdapterState FSM, disagreement arbitration, and **`verdict` — a retrospective admission/validity gate** (host-RAM floor → "refuse if Shared-GPU fallback suspected"; spill ceiling; layer-split asymmetry; emits flat JSON for harness consumption).

**denning = the control plane atop this observation plane.** b70tools explicitly deferred control ("observer, not kernel"; control-plane ops out of scope). The genuine GAPS denning adds (absent from b70tools): **online prospective admission** (generalize `verdict` from post-hoc to live), **reuse-provenance lifetime classes** (entirely absent — physical metrics only), **cooperating with VidMm** (observe → arbitrate), and the **many-concurrent-agent-on-one-card** demonstration.

**Shared dependency to land first:** the b70tools **commit-headroom gate** (`inference-test-backlog.md` item 3d, identified but uncoded) — denning's admission controller must gate on commit headroom (§3).

**Scaffold denning inherits (generalize, not rebuild):** the N-session harness generalizes b70tools backlog **8c** (two-lane planner/critic, distinct `ONEAPI_DEVICE_SELECTOR`); the H1 adversarial-co-tenant test generalizes the **WoW run** (`findings-wow-realtime-inference-impact-1.md`) + adds **PresentMon** for frame-times. Frame as scaffold-to-generalize, NOT done.

---

## 3. Corrections the prior data forces (do not get these wrong)

1. **The binding wall is commit charge, not free RAM.** Observed 92% commit while physical at 60%; WDDM backs VRAM with system commit, `--no-mmap` compounds it. → Admission math gates on **commit headroom**, not the RAM/VRAM ratio.
2. **Long-context decode collapse ≠ spill.** At 25k ctx (32B): *no spill* (22.78 GB dedicated, 0.49 GB shared) yet **4.2 t/s** — root-caused to the **Vulkan attention kernel**; **SYCL did 14.5 t/s (3.5×)** at the same point. → Separate "bandwidth-spill stall" from "attention-kernel collapse"; **engine (SYCL vs Vulkan) is a first-class variable**, not an implementation detail. (Caveats: SYCL cold-load 131 s vs Vulkan 11 s; SYCL VRAM nearly invisible to PDH — 1 GB reported while 29 GB resident.)
3. **"Shared memory bar lit up" ≠ "spill is the bottleneck."** Measured directly — don't infer causation from the shared-memory counter alone.

---

## 4. Measured calibration constants (cite as prior observation; use to ground predictions)

| Config (dual B70, Vulkan, Q4 unless noted) | Prefill t/s | Decode t/s | Source |
|---|---|---|---|
| 70B layer-split | 151–188 | 11.6–11.7 | `battlemage/arc-b70-dual-70b-windows-vulkan.md`; `phase5b`/`overnight-C` |
| Qwen2.5-32B dense | 242.2 | 20.7 | `findings-dual-b70-qwen25-32b-q4-1.md` |
| **Qwen3-30B-A3B MoE** (rung-1.5) | 30.1 | **81.7** | `findings-dual-b70-qwen30b-moe-1.md` |
| Mistral-24B single card | 428.9 | 27.3 | `findings-both-cards-concurrent-mistral24b-1.md` |
| 14B single card | 903→1254 (np128→512) | 45.0 | `phase4-14b-vulkan0-scaling.jsonl` |
| Long-ctx 32B Vulkan | — | 21.5 → 4.2 @ ~25k (5× collapse) | `retrospective-bsod-fix-and-sycl-unlock-2026-06-18.md` |
| Same @ 25k, SYCL | — | 14.47 (3.5× Vulkan) | same |
| Prefill vs depth (70B) | 186 @ np4096 → 120.8 @ np16384 | — | `overnight-A-70b-fp16kv.jsonl` |

Rig facts: 32 GB/card (64 GB pooled — **not** 48), ECC off, ReBAR on, `vram.local.budget_bytes` ≈ 31.12 GiB/card idle. KV @131072 for Qwen3-30B-A3B ≈ 12.0 GiB f16 / 6.3 GiB q8 (`plan-vulkan-moe-125k-shared-memory-2026-06-18.md`).

---

## 5. Integrity split (drives the prereg)

| Hyp | Status in prior work | Prereg disposition |
|---|---|---|
| H1 VidMm eviction under co-tenancy | **mechanism observed** (spill→PCIe→collapse); game-induced involuntary eviction of a *fitting* model **untested** (no frame-times captured) | **Part A** cite mechanism; **Part B** pre-register the narrow game-induced-eviction-with-frame-pacing claim |
| H2 roofline admission on session count | contention observed; **no slots-vs-goodput curve** | **Part B** pre-register the roofline knee |
| H3 B70 constants | throughput constants **observed**; VRAM-BW GB/s, PCIe GB/s, recompute-vs-refetch **untested** | **Part A** cite constants; **Part B** pre-register BW/PCIe/recompute |
| H4 classes beat TTL | untested | **Part B** |
| H5 shared-memory cliff / 125k MoE | cliff **observed**; 125k-MoE single-card spill experiment **planned, never run** | **Part A** cite cliff; **Part B** pre-register the 125k-MoE spill experiment |
| H6 fractal portability | untested | **Part B** |

See `prereg/OVERARCHING-PREREG.md` for the split as written.
