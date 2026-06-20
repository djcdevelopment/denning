# Workbook — 2026-06-19 — I-4a closed-form admission controller (validated)

*The I-3 finding (no hard pin) makes admission control THE defense. Built + validated the closed-form rule against the measured H1 cliff.*

## Built
- **`experiments/admission_controller.py`** — the rule `N*=floor((B−W)/k)`, `admit iff footprint ≤ B`, fed by the **live VidMm budget** (read via the D3D12 probe monitor mode, `--size-gb 0`).

## Ran
- Live budget read: **31.12 GB**. `N* = 132` sessions (W=17.9, k=0.1).
- Validation vs the H1 sweep: **5/5**. ADMIT at cap 10/12 (fast), DEFER at cap 14/16/18 (cliff). The model (17.9) stops fitting when the co-tenant exceeds 13.2 GB → DEFER at cap 14, exactly the measured cliff.

## Finding
The closed-form rule + the live budget oracle is a **correct admission predictor (5/5)**. Closes the loop: can't pin (I-3) → admit beneath the live budget (I-4a) → order own eviction by class (H4). The OS hands you the limit in real time.

## Caveat
Retro-validation + a live read; the closed-**loop** demo (actively shed under a *live* co-tenant to stay off the cliff) is I-4b.

Result: [`../results/I4a-admission-controller-20260619.md`](../results/I4a-admission-controller-20260619.md).

## Next
**I-4b** closed-loop: N sessions under a live co-tenant, controller gates on the live budget, goodput stays SLO-side of the cliff vs the uncontrolled (H1) collapse — the payoff figure.
