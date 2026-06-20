# Workbook — 2026-06-19 — I-3 defense feasibility: can residency priority pin the arena?

*Before building a "pinned arena," test the documented Windows knob (D3D12 `SetResidencyPriority` + `MakeResident`). Built the repo's **first native code** (D3D12, MSVC via VS2022).*

## Built
- **`experiments/d3d12_residency_probe.cpp`** — allocates N GB on a chosen adapter at MAX|NORMAL residency priority, `MakeResident`, samples this process's LOCAL/NON_LOCAL usage + **Budget**. `cl /EHsc /O2`.

## Ran (two D3D12 processes on one B70, oversubscribing 34 GB on 31.12)
- A=MAX 18 GB + B=NORMAL 16 GB: A's Budget 31.12 → 18.64 → **15.33**.
- Control A=NORMAL 18 GB: Budget 31.12 → 16.65 → **15.33** — **identical**.
→ D3D12 residency priority has **no inter-process budget effect**; VidMm splits ~evenly (15.3/15.3) regardless of priority.

## Finding (design-shaping)
- Residency priority is an **intra-process** eviction-ordering hint, not an inter-process residency guarantee. denning cannot pin the model against a co-tenant via priority; D3D12 has no hard pin.
- → The co-tenant defense is **admission control on the live budget signal** (`QueryVideoMemoryInfo.Budget` dropped 31→15 GB in ~8 s — responsive). Points straight at **I-4**.
- Priority is still the right tool **inside** the arena: order denning's own hot/cold eviction (**H4** lifetime classes). H1 (hot set sets the penalty floor) + this (priority orders intra-process eviction) ⇒ lock the hot set MAX so cold demotes first under a shrinking budget.
- **Thesis sharpened:** don't *fight* VidMm for residency (can't) — **co-reside** (read its budget, admit beneath it, order your own eviction by class).

## Caveat
Tests budget arbitration, not physical residency under active GPU use (the probe doesn't GPU-touch the memory). Documented intra-process semantics + the control support the conclusion; a copy-bandwidth-under-pressure test (MAX vs NORMAL) is the next-step rigor.

Result: [`../results/defense-feasibility-d3d12-priority-20260619.md`](../results/defense-feasibility-d3d12-priority-20260619.md).

## Next
**I-4** — the closed-form admission controller on the live VidMm budget (+ commit headroom, + the bandwidth roofline), with intra-arena lifetime-class eviction ordering. The "arena" becomes *admit-beneath-the-budget* + *order-your-own-eviction*, not *out-pin-the-OS*.
