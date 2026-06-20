# Workbook — 2026-06-19 — H1 core eviction pilot (built; pressure run pending operator go)

*G0 decisions: engine = **Vulkan** (PDH `non_local` reads cleanly; SYCL is blind), scope = **core eviction pilot** first. Per the decision, the harness is BUILT + baseline-validated; the induced-pressure leg waits for the operator's go. The tagged prereg card (`prereg-launch-suppositions`) is unchanged — this is the operational realization of it, a cheap first cut.*

## Built (`experiments/`)
- **`vram_hog.py`** — adversarial co-tenant. Allocates + **touches** FP16 VRAM on Card B (`xpu:1`) in steps to `--cap-gb`, holds, frees. Validated: 2 GB pulled Card B free 31.2 → 29.6 GB, released clean.
- **`h1_eviction_pilot.py`** — orchestrator. preflight (GO/NO-GO) → b70tools recording (Card B, 2 Hz, flush-every-tick) + safing watchdog (**OBSERVER-only**) → baseline `llama-bench` tg → [gated: hog → `--hog-cap-gb` → pressured tg] → stop → analyze (`b70tools verdict --json`) → result JSON. The pressure leg fires **only** with `--arm-pressure`.

## Validated (safe, no pressure)
`--baseline-only`: preflight GO; recorder + watchdog up; **baseline tg = 132.6 t/s** (matches E1 roofline d=0 = 132.8 → the orchestrator's bench is sound); clean shutdown; result JSON written. Scaffolding green.

## The science (what the armed run measures)
- baseline tg (no hog) **vs** pressured tg (hog holds N GB on Card B), with the b70tools `non_local` timeline throughout.
- **CONFIRM H1**: pressured tg collapses **AND** `non_local` rises → VidMm involuntarily demoted the serving process.
- **REFUTE H1**: tg ~unchanged / hog fails to allocate → VidMm protects the foreground compute process → pre-committed pivot (headline = roofline-admission + RAM<VRAM inversion).

## Squeeze schedule (proposed, for the go)
Qwen3-30B-A3B Q4 ≈ 17.3 GB resident on Card B (31.2 GB). To force demotion the hog must fill the card past the server's demand: ~14 GB fills it; >14 GB forces spill. Proposed first run: `--arm-pressure --hog-cap-gb 15` (just past fill), watchdog observer-only with the cascade ABORTs live (commit≥95%, phys≥29.5 GB, TDR). Bounded, one card, model fits → the watchdog catches a real cascade while a *signal-level* `non_local` rise is expected and logged.

## STATUS — **PAUSED** for operator go
The first `--arm-pressure` run is the first induced-pressure "flight" and the P0 honest-unveiling. Awaiting the go (and any change to the squeeze schedule / model).

## Manifest
`experiments/vram_hog.py` · `experiments/h1_eviction_pilot.py`. Card B, Vulkan (`GGML_VK_VISIBLE_DEVICES=1`) + `xpu:1` hog. b70tools b9279 build, driver 32.0.101.8826.
