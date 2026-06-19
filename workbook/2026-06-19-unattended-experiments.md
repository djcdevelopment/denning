# Workbook — 2026-06-19 — Unattended experiment run

*Operator stepped away ~1–2 h ("keep moving where you can"). Ran the bounded/fitting on-rig experiments — one GPU run at a time, no spill edge, no adversarial, no oversubscription. All real, committed, nothing fabricated.*

## Results banked (this window)
- **q8-KV roofline + isolation:** q8 KV is **2–4× SLOWER** at depth, not faster → isolated to the **Vulkan flash-attention kernel** (f16+FA ≈ q8+FA, both ~4× slower than f16-no-FA). FA is a *pessimization* on Vulkan/Arc; the default attention path wins; quantized KV is a capacity-vs-speed trap. **Corrected prediction = a real finding.**
- **MoE-vs-dense:** MoE (3B active) **decodes 5.7× faster** than dense 32B (130 vs 23 t/s) at equal total size → the active-params bandwidth thesis confirmed; validates the MoE choice for this hardware.
- **Extended N-session (1→32):** aggregate decode peaks ~**B=8** then non-monotonic; **run-to-run variance ~20–30%** → `N*` ≈ 8 at small ctx but **noise-limited** (validates the measurement-discipline concern). Prefill plateaus ~896.
- *(Earlier this session: R1/R2/R3 confirmed; decode roofline + cliff; rig + telemetry-validity; torch-xpu toolchain installed, C: protected.)*

## State for your return
The **cost-model core (R1/R2/R3) + the admission roofline** are empirically confirmed; the q8/FA-kernel, MoE-vs-dense, and N-session findings are documented. **`results/E1-SUMMARY.md` is the one-page picture.** Repo clean + pushed.

## Why I stopped the chain here (honest)
Further **single-run** experiments are now **noise-limited** (batched-bench swings 20–30% run-to-run) → the next measurements need the **averaged/pinned protocol** (N reps + noise floor), which is a deliberate, post-G0, operator-led step — not something to chase noisily while unattended. The remaining **high-value** work is **operator-gated**: G0 + tagging, H1 (watchdog first), the asymmetric build. I stopped rather than manufacture low-marginal runs.

## Next (you)
**G0 with Uncle** → lock the priors → tag → **I-1 watchdog** → **H1**. Optional refinements I can run when you're back: dequant-under-N-decode, the SYCL-vs-Vulkan cliff comparison (via ipex-llm/ollama), a llama.cpp-matched dequant kernel, and the **averaged N-session sweep** to pin `N*` through the noise.
