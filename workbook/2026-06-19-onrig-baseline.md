# Workbook — 2026-06-19 — First real on-rig run

Operator authorized running the experiment + tagging as my work. Probed the box: **E1 cannot run** (no `torch`/torch-xpu; no `icpx`/`cl`/`cmake`/`ninja` — no compute or build toolchain; only `vulkaninfo` + the prebuilt `b70tools.exe` present). So I ran **what genuinely executes**: the b70tools instrument.

**Done (real, not fabricated):**
- `b70tools --enumerate` + `run --ticks 20` + `summarize` → confirmed 2× Arc Pro B70, driver 32.0.101.8826, per-card 31.87 GiB DVM / 31.12 GiB budget / 15.96 GiB SSM; **resolved the "48 GB" = DVM+SSM**; Card B idle at 0% = headless compute card.
- **Telemetry-validity smoke test PASSED** (Uncle's pre-E1 gate) — signals live + PassiveSafe.
- Captured a real idle baseline (`results/raw/idle-baseline-20260619/events.jsonl`) + wrote `results/idle-baseline-20260619.md`.

**Did NOT (honestly blocked):**
- E1 (materialization-cost crossover) — needs a compute stack. No numbers invented.
- No prereg tag (E1 not run).

**Next:** to run E1, the operator greenlights a toolchain install (torch-xpu *or* oneAPI+cmake/ninja), **pinned + caches redirected to D:** (C: at the ~100 GB redline; toolchain version is a frozen-config variable). Then: tag E1 predictions (as my work) → run E1 on Card B.
