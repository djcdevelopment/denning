# Result — Idle baseline + telemetry-validity smoke test (2026-06-19)

*Real on-rig run of the existing `b70tools` instrument. **NOT a pre-registered hypothesis test** — it is rig confirmation + Uncle's pre-E1 telemetry-validity gate + the manifest baseline (facts/validation, not predictions, so no prereg needed). Run by Claude, authorized by the operator. Recording: `raw/idle-baseline-20260619/events.jsonl` (52 KiB, 227 events, 20.4 s, 1 Hz).*

## Rig confirmed (measured)
- **2× Intel Arc Pro B70** (PCI `0x8086:0xE223`), driver **32.0.101.8826** (the frozen-config driver — flight rule 6), Vulkan **1.4.348**.
- BDF: card A `0000:0c:00.0` (bus 12) · card B `0000:10:00.0` (bus 16); reconciled on stable **PCI-BDF** (LUID-drift-resistant, as prior work proved).
- **Per card:** DedicatedVRAM **31.87 GiB** (34,215,034,880 B); **DXGI budget 31.12 GiB** (VidMm reserves ~0.75 GiB); SharedSystem window **15.96 GiB**.
- **The "48 GB" RESOLVED (measured):** Task-Mgr sum = DVM 31.87 + SSM 15.96 = **47.83 GiB/card** — the "48 GB on a 32 GB card" mechanism, confirmed by telemetry. **Pooled dedicated VRAM = 2 × 31.87 = 63.7 GiB.**
- `VK_EXT_pageable_device_local_memory` + `ext_memory_budget` present → **Vulkan-level residency control available** (alternative to D3D12 for the pinned arena).

## Telemetry-validity smoke test: PASS (Uncle's pre-E1 gate, real)
b70tools M2 acceptance PASS: DXGI+Vulkan identity captured · stable LUID reconciliation · D3DKMT MetricSample emitted · JSONL written · AdapterState advanced · **no VkDevice / no GPU allocation (PassiveSafe)**. The signals E1/H1 are scored on are live and sane on the frozen driver:
`vram.local.budget_bytes` 31.12 GiB · `vram.local.current_usage` 4 KiB idle · `vram.non_local.current_usage` **0 B (no spill at idle)** · `vulkan.heap0.budget` 31.12 GiB · `gpu.engine.utilization_pct` (PDH) live · IGCL power/temp/freq/voltage live.

## Idle metrics (the baseline / zero reference)
| Card | BDF | idle engine util | notes |
|---|---|---|---|
| A | 0c:00.0 | **14.7%** | drives the desktop (background compositor); 53 °C, 2.60 GHz, 0.975 V, VRAM 2.375 GHz |
| B | 10:00.0 | **0.0%** | **headless/compute candidate** — idle-clean, 4 KiB used, 0 spill |

→ Route the display off Card A (or to the iGPU) and run compute on **Card B**, per the headless recommendation — B is already clean.

## Establishes / does NOT
- ✅ Rig confirmed with real constants (manifest + cost model): per-card budget **31.12 GiB**, the 48 GB mechanism, frozen driver **32.0.101.8826**.
- ✅ Telemetry-validity smoke test **passed** — the instrument E1/H1 depend on works, is do-no-harm, signals present and not blind (on DXGI/Vulkan; SYCL-blindness is a separate check when/if SYCL is used).
- ✅ A real idle-baseline recording (the noise-floor zero reference).
- ❌ **NOT E1.** The materialization-cost crossover constants (`B_pcie`, `B_dq`, `R_prefill`) are **unmeasured** — they need a compute stack (torch-xpu or oneAPI + build tools), which is **absent** on this box (no `torch`, no `icpx`/`cl`/`cmake`/`ninja`). They remain `[MEASURE]`.

## Manifest
- git commit: `<this commit>` · tool: `b70tools.exe` (D:\work\b70tools\build) · driver 32.0.101.8826 · Win10 19045 · 2× Arc Pro B70 (31.87 GiB DVM / 31.12 GiB budget / 15.96 GiB SSM) · capture: `b70tools run --ticks 20 --cadence-ms 1000` · recording sha = (see file).
