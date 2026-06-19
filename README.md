# denning

*Treating an LLM's context (KV-cache) and MoE experts as an OS-managed resource on fabric-less, OS-arbitrated GPUs.*

**Named for Peter J. Denning** — the working-set model (CACM 1968) and the page-fault-frequency load-control tradition that followed (1970s). This project reincarnates that idea for KV/expert residency on a GPU: admit work to the resident set only while it fits the bandwidth roofline; suspend before you thrash.

## Thesis (one sentence)

On a fabric-less, RAM-inverted, OS-arbitrated GPU box (Windows/VidMm, PCIe-only Intel Arc, RAM < VRAM), correct LLM-state management is **bandwidth-roofline admission control + co-residency with an adversarial OS memory manager**, with reuse-provenance **lifetime classes** as the single control signal — demonstrated on the one workload the box is genuinely good at: **many concurrent agent KV sessions on a single card under desktop co-tenancy.**

**Contribution (one sentence):** *On memory-inverted, fabric-less GPUs the materialization decision inverts from the datacenter answer under compute contention, and closed-form admission control on this cost model — over a pinned deterministic arena, not heuristic paging — is sufficient to operate at the feasibility bound.* (North star above = motivation; this = the claim.)

**Goal: map the feasibility envelope (the bounds), with the simplest system that reveals it.** Compression depth and bit-checks are deferred levers — see `docs/cost-model.md` §7.

## Status: **S0 — research setup** (pre-registration in progress; no results yet)

Next gate: **G0** — the advisor reviews methodology + pre-registration **before any GPU-hour is spent.**

## The one rule

**Predictions are committed (git-tagged) before any data is collected.** See [`prereg/`](prereg/). A refuted prediction is a *success of the method*. Results ([`results/`](results/)) are committed *after* the matching prereg is tagged, and open with a predicted-vs-actual table. The git history is the integrity proof — it is physically impossible to retrofit a prediction to a result.

## Repository map

| Path | What |
|------|------|
| [`docs/`](docs/) | technical plan (original + v2 green/red re-review) + the research-program (process) plan |
| [`prereg/`](prereg/) | **the honesty engine** — overarching hypotheses (H1–H6) + per-experiment Prediction Cards |
| [`results/`](results/) | results, committed only *after* the matching prereg is tagged |
| [`workbook/`](workbook/) | dated public lab notebook |
| [`experiments/`](experiments/) | measurement harnesses (P0 first) |
| [`related-work/`](related-work/) | citation tracker with verification status |
| [`REPRODUCE.md`](REPRODUCE.md) | the per-result reproducibility standard |

## Hardware target

Dual **Intel Arc Pro B70** (Battlemage, 32 GB each = 64 GB VRAM, ~608 GB/s, FLOP-modest ~22.9 TFLOPS), **32 GB system RAM (RAM < VRAM)**, **PCIe-only** (no NVLink/Xe-Link; no Windows GPU P2P), Windows 10. Engine: **llama.cpp + SYCL/Vulkan, `--split-mode layer`** (the only working Windows-Arc multi-GPU path).

## License

TBD — decide at G0.
