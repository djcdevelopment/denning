# Pre-registration — thermal-window regression battery (2026-06-21)

Tagged BEFORE any battery data lands (discipline: a refuted prediction is a
success of the method, not a failure of the rig).

**Rig.** 2x Intel Arc Pro B70 32GB, headless (Vulkan dev **1,2**) + RTX 2070
Super display (dev **0**, never served). Ryzen 9 5900X / X570 AORUS Ultra /
32GB DDR4-3800 **1:1** (FCLK 1900) 16-19-19-39. B70s **x8/x8 PCIe 4.0**
(to be confirmed *under load* in A1 — idle reads downtrain to x1). Engine
llama.cpp Vulkan b9279. Model Qwen3-30B-A3B-Instruct-2507-Q4_K_M (17.3 GB).
denning git HEAD 155c3b2.

## Grid
A per-card noise floor + PCIe-width-under-load; B KV-size scaling
(prefill/decode × f16/q8, depth → 125k); C1 restore-vs-re-prefill TTFT;
D1 own-config tuning (FA/batch/threads); perplexity q8-vs-f16 KV; E dual-card
concurrency A/B + thermal soak.

## Predictions (with refutation criteria)
- **P1 — decode cliff.** tg t/s falls monotonically with depth; by 64k, decode
  ≤ ⅓ of its d=0 value. *Refuted if* tg@64k > ½ of tg@0.
- **P2 — prefill resilience.** pp t/s degrades far less steeply than tg with
  depth — prefill stays usable where decode collapses.
- **P3 — q8 capacity win.** q8 KV reaches 125k single-card; f16 OOMs before
  ~72k single-card. *Refuted if* f16 reaches 125k, or q8 OOMs < 125k.
- **P4 — q8 decode cost.** q8 tg within ~15% of f16 tg at equal depth.
  *Refuted if* q8 is >25% slower than f16.
- **P5 — per-card symmetry.** B70 #1 and #2 within ±5% on pp/tg. A >10% gap ⇒
  bad slot/thermal — HALT and report.

## Halt-for-operator conditions (otherwise continue autonomously)
Any prediction refuted by >2× its stated margin; any TDR (Event 4101); watchdog
SAFE/ABORT; a card OOM where the VRAM math said it should fit; per-card
asymmetry >10% (P5).
