# Result — Defense feasibility: D3D12 residency priority does NOT protect against a co-tenant (2026-06-19)

*I-3 defense probe. Before building a "pinned arena," test whether the documented Windows residency knob (D3D12 `SetResidencyPriority` MAXIMUM + `MakeResident`) can keep a fitting allocation resident when a co-tenant oversubscribes the card. Harness: [`../experiments/d3d12_residency_probe.cpp`](../experiments/d3d12_residency_probe.cpp) (native D3D12, MSVC). Two processes on one B70 (adapter 0, LUID `00011e35` — the H1 card).*

## Setup
Two D3D12 processes on the same card (budget 31.12 GB):
- **A = "arena"** — 18 GB, **MAX** residency priority + `MakeResident`.
- **B = "aggressor"** — 16 GB, **NORMAL** priority.

Together 34 GB > 31.12 → oversubscription. Question: does A's MAX priority give it a larger budget / protect it?

## Result — priority has NO inter-process effect
A's `QueryVideoMemoryInfo` **Budget** (GB) over time, MAX vs NORMAL (control):
| A priority | t=0 | t=8 | t=16 | t=24 |
|---|---|---|---|---|
| **MAX** | 31.12 | 18.64 | 15.33 | 15.33 |
| **NORMAL** (control) | 31.12 | 16.65 | 15.33 | 15.33 |

**Identical.** When the co-tenant appears, VidMm splits the budget ~evenly (**15.3 / 15.3 GB**) regardless of A's priority. The MAX-priority "arena" got no larger budget — and ended up *more* over-budget (18 vs 15.3 = 2.7 GB over) than the smaller aggressor.

## Reading — the right tool for the right job
- **D3D12 residency priority is an *intra-process* eviction-ordering hint, not an *inter-process* residency guarantee.** It tells VidMm "if you must evict MY resources, evict MY low-priority ones last" — it does **not** give a process a larger share of the card versus another process. (Matches the documented semantics; the control confirms it empirically on this Arc/Win10 driver.)
- **So denning cannot defend the model from a co-tenant by pinning/priority.** D3D12 also offers no hard "lock" (unlike `VirtualLock` for CPU pages). **The arena-as-hard-pin against a co-tenant is not feasible** via documented APIs on this stack — a genuine, design-shaping finding.
- **The defense must be ADMISSION CONTROL** — keep denning's total demand under the OS-reported budget. And the signal is **live and responsive**: `QueryVideoMemoryInfo.Budget` dropped **31 → 15 GB within ~8 s** of the co-tenant appearing. That is exactly the input the **I-4 controller** gates on (cost-model §2: `N* = min(bandwidth, commit, live VidMm budget)`).
- **Priority is still useful — INSIDE the arena.** For ordering denning's *own* blocks' eviction (keep the hot working set, shed cold blocks first), residency priority / lifetime-classes are the mechanism — exactly **H4** (typed lifetime classes). Combined with the H1 finding (the *hot* working set sets the penalty floor): lock denning's hot set at MAX priority so that when VidMm shrinks denning's budget, the **cold** blocks demote first.

## What it means for the build
- **No hard pin against co-tenants** → the defense is the **closed-form admission controller (I-4)** on the live budget signal, not a pinned arena that out-prioritizes the OS.
- **Intra-arena**: MAX priority on hot blocks + lifetime-class eviction ordering (H4) so denning sheds cold state first under its (shrinking) budget.
- **Thesis sharpening:** you don't *fight* VidMm for residency (you can't) — you **co-reside**: read its budget signal, admission-control beneath it, and order your own eviction by lifetime class. This is precisely "co-residency with an adversarial OS memory manager," now grounded in why.

## Caveats (honest)
- The probe tests **budget arbitration** (what VidMm tells each process), not physical residency under active GPU use — it doesn't GPU-touch the memory. The budget is the actionable admission signal, and the documented intra-process priority semantics predict this result; a GPU-touch bandwidth test (copy-queue under pressure, MAX vs NORMAL) would confirm the physical consequence — next-step rigor.
- Single driver / two-process; the even split may vary with more tenants or asymmetric sizes.

## Manifest
`experiments/d3d12_residency_probe.cpp` (`cl /EHsc /O2`; `ID3D12Device1::SetResidencyPriority` + `MakeResident` + `IDXGIAdapter3::QueryVideoMemoryInfo`). Card B / adapter 0 LUID `00011e35`. Raw: `results/raw/probe-*.txt` (gitignored). driver 32.0.101.8826.
