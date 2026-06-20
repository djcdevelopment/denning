# Workbook — 2026-06-19 — I-3 resident-server eviction + hog sweep

*The stricter "evict-already-resident" H1 + the demotion-threshold sweep. Same go ("proceed the build and test"), same safety envelope (watchdog observer, bounded hog).*

## Built
- **`experiments/h1_resident_pilot.py`** — persistent `llama-server` (model brought **fully resident first**), streaming `/completion` TBT via urllib, hog applied **after** residency → evict-already-resident. Reuses the pilot's recorder/watchdog/hog/analyze helpers.

## Ran
- **Baseline-only validated:** server resident (`local` 17.9 GB), decode 119 t/s, TBT 8.5 ms.
- **Resident eviction (hog 15):** decode 117.8 → 22.9 t/s (**0.194×, 5×**), TBT 8.5 → 43.4 ms, TTFT 113 → 911 ms, `non_local` → 2.20 GB. → **H1-SUPPORTED-resident** (stronger than the pilot's 2×).
- **Hog sweep 10/12/14/16/18:** clean demotion cliff at the budget crossover (~cap 13). Below: ratio ~1.0 (control — hog harmless). At/above: 0.231 / 0.196 / 0.165, `non_local` 0.24 / 2.70 / 4.87 GB (scales ~linearly with oversubscription).

## Findings
1. **Hot-resident eviction is WORSE than load-under-contention** (5× vs 2×) — VidMm bounces hot decode-path bytes over PCIe.
2. **Sharp cliff at the VRAM-budget crossover**; below it the hog is harmless (the control isolates oversubscription as the cause).
3. **Spill scales ~linearly** with oversubscription; **decode penalty saturates (~0.2×)** once the hot path is bounced (more cold spill doesn't matter).
4. **Honest:** at cap 14 decode collapsed but the coarse PDH gauge missed the small/brief spill → decode-penalty is the sensitive indicator at the margin; `non_local` registers clearly only ≥2 GB.

Result doc: [`../results/H1-resident-sweep-20260619.md`](../results/H1-resident-sweep-20260619.md).

## Next
The **pinned arena** — lock the hot working set resident so eviction lands on cold blocks → re-run this exact sweep and show the cliff defended (then the I-4 controller admits work to stay left of the residual cliff).
