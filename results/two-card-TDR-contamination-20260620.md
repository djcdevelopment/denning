# Integrity notice — two-card results collected across display-driver TDRs (2026-06-20)

*Forensic correction, filed under the project's pre-registration / honest-unveiling
discipline. The symmetric two-card configuration — a full Qwen3-30B-A3B replica plus
concurrent decode on **both** cards, including device 0, which drives the monitor —
**reproducibly trips a WDDM display-driver reset (TDR)**. Some headline two-card
numbers were measured across these resets and must not be reported as clean. This
is the failure being disclosed, not buried; the failure is itself a finding.*

## The evidence (Windows System log, Event ID 4101 — `igfxnd` display TDR)
Four resets, in two clusters, each cluster a two-card session:

| # | TimeCreated | Event | Driver |
|---|---|---|---|
| 1 | 2026-06-19 23:45:59 | 4101 "stopped responding and has successfully recovered" | igfxnd |
| 2 | 2026-06-19 23:48:18 | 4101 | igfxnd |
| 3 | 2026-06-20 03:59:52 | 4101 | igfxnd |
| 4 | 2026-06-20 04:00:25 | 4101 | igfxnd |

Query: `Get-WinEvent -FilterHashtable @{LogName='System'; Id=4101}`. `igfxnd` = the
Intel Arc (Battlemage) display kernel driver. A 4101 means the GPU hung, Windows
timed it out, killed the graphics context, and reinitialized the display stack —
the monitor blanks and recovers, the desktop compositor (dwm) and any GPU-accelerated
app lose their surfaces. Observed live on cluster 2 (operator watching): video froze,
monitor blanked then returned, the Claude desktop app blanked and needed a restart;
audio (GPU-independent) never dropped.

## Rig TDR history (context — this is a chronically TDR-prone box)
The full System log holds **114** Event-ID-4101 TDRs, **all driver `igfxnd`**, spanning
**2026-05-26 → 2026-06-20** (~25 days). Only **4 are in the last 7 days** (our two-card
runs above); the other **~110 predate the denning two-card work** (the 05/26–06/13
pilot era — battlemage/b70tools GPU experiments on this same rig). So the display
driver on this Windows+Arc box resets *frequently* under GPU load, independent of
denning. That doesn't excuse running across one — it means the opposite: on this
hardware the display card is a **known, repeatedly-demonstrated** TDR liability, and
any run that loads it must assume a reset is likely, not hypothetical. (The `TdrGuard`
is delta-based — it counts resets *during a run* — so the 114 lifetime baseline is
irrelevant to its verdict.)

## Correlation to the runs (git commit times, same machine)
- `two-card-scaling` committed **23:29:28**; `two-card-goodput` committed **23:50:42**.
  The goodput run (`h4_twocard.py`, 16 concurrent streaming sessions across both cards)
  therefore executed in (23:29:28, 23:50:42) — and **both cluster-1 TDRs (23:45:59,
  23:48:18) fall inside that window.**
- Tonight's `denningd --serve --cards 2 --n 16` ran ~03:59; **both cluster-2 TDRs
  (03:59:52, 04:00:25) are that run.**

## Disposition of each result
| result | verdict | reason |
|---|---|---|
| [`two-card-goodput-20260619`](two-card-goodput-20260619.md) (N\*=8→16, 16/16 SLO) | **CONTAMINATED — retract as a clean measurement** | 2 TDRs during its run window; numbers were collected across display-driver resets |
| [`two-card-scaling-20260619`](two-card-scaling-20260619.md) (1.96× aggregate decode) | **PROVISIONAL** | `llama-bench`, committed 23:29:28 — *before* the first logged TDR (23:45:59); no 4101 in its window, but it ran one concurrency-step below the load now known to TDR. Re-confirm under monitoring before relying on it. |
| `denningd --serve --cards 2` (tonight: 14/16 SLO, 8.84 ms, 1559 t/s) | **CONTAMINATED — do not report** | 2 TDRs during the run |

The single-card results are unaffected (one card, no display-card co-tenancy at load):
`two-card` claims aside, every I-/H-/S- result on Card B stands, and the S-shim-1/2
adapter + daemon verifications on **one** card are clean.

## The finding inside the failure
This is not merely noise to discard. **Symmetric replication across the display card
reliably trips a display-driver TDR** (4 events / 2 independent sessions). On this
substrate the display card is not a degraded-but-usable participant — past a load
threshold it is a *hard* limit: pushing it takes down the desktop. That is the H1
threat at its extreme, with denning as the aggressor. It is the strongest possible
evidence for the rule the project already suspected: **multi-card serving must be
asymmetric** — heavy on the headless compute card (Card B), with the display card
(Card A) capped well below its raw throughput to leave the compositor reserved
compute/VRAM headroom. "Two cards = 2× by symmetric replication" is **false on a
machine where one card drives the display.**

## Correction plan
1. **[done]** File this notice; banner the affected result docs; flag the claims in `E1-SUMMARY.md`.
2. **Re-run two-card ASYMMETRICALLY, under the I-1 safing watchdog**, with per-device N\* caps (Card B heavy; Card A a small reserved-headroom cap), watching Event-ID-4101 count = 0 as a pass condition. That becomes the *clean* two-card result.
3. **Re-characterize the two-card thesis** from the clean asymmetric data: the honest claim is likely "~1.x× with the display card as a *bounded* second participant," not a clean 2×.
4. **Update the paper** (`hotos-denning.md`) — the TDR becomes the motivating threat for asymmetric replication, and the headline two-card number is replaced with the clean, watchdog-verified one.

## Process failure that allowed it
The two-card runs were executed **without the I-1 safing watchdog** (it was built for
the H1 hog experiments and not wired into `h4_twocard.py` or `denningd --serve`). The
watchdog polls the live budget and would have flagged the approach to the reset
threshold. Rule going forward: **no on-rig run that loads the display card without the
watchdog active and a 4101-count post-check.**
