# Result — Safety harness: asymmetric caps + TDR guard + watchdog detector (2026-06-20)

*Built off-rig in response to the display-driver TDR incident
([`two-card-TDR-contamination-20260620`](two-card-TDR-contamination-20260620.md)).
Two layers: **prevent** the display card from reaching the reset threshold
(asymmetric admission), and **detect** any reset so a run can never silently report
numbers collected across one (TDR guard + watchdog). No GPU load was used to build or
verify this — pure logic + read-only event-log queries.*

## What shipped
- [`../denning/control/tdr_guard.py`](../denning/control/tdr_guard.py) — `count_4101()` (read Windows Event ID 4101, the `igfxnd` display-TDR) + `TdrGuard` (arm → `clean()`/`tripped()` on the delta). **Fail-safe:** a probe failure is *not* `clean()` — absence of evidence is not evidence of safety.
- [`../denning/denningd.py`](../denning/denningd.py) — **asymmetric per-device caps**: the display card (device 0) is clamped to `display_cap` (default **2**) concurrent sessions; headless cards run at the full admission knee. `--serve` now arms the TDR guard around the run, launches the watchdog, and tags the result `tdr_clean` / `UNSAFE` (exit 4 on a reset).
- [`../ops/safing_watchdog.py`](../ops/safing_watchdog.py) — `--watch-tdr`: the watchdog now has a *live* TDR detector feeding its existing `adapter_state == PostTDR → ABORT` path (previously that path had nothing driving it).

## Verified (no GPU — `python tests/test_shim.py` → 25/25 PASS)
- **Asymmetric caps**: at equal in-flight load, the display card (dev 0, cap 2) **sheds** the next session while the compute card (dev 1, uncapped) **admits** it. `device_caps == (2, None)`.
- **TDR guard**: no new reset → `clean`; a new reset → `tripped`, not `clean`; probe failure → **not** `clean` (no false assurance).
- **Watchdog rehearsal** (`--simulate tdr`): classifies **ABORT** (exit 3) via `AdapterState=PostTDR`. The `--watch-tdr` reader imports cleanly and a real `count_4101()` returns the live count.

## Rig context the build surfaced
The live read returned **114** lifetime TDRs (all `igfxnd`, 2026-05-26 → 06-20); only the 4 most recent are denning's, ~110 predate it. This box resets its display driver *routinely* under GPU load — so on this hardware a display-card reset is the expected failure mode, not an edge case. The asymmetric default (`display_cap=2`) and the mandatory guard follow directly.

## The safe envelope going forward
A two-card on-rig run is now bounded by construction:
```
python -m denning.denningd --serve --cards 2 --n 16 --display-cap 2
# arms TdrGuard, launches the watchdog (--watch-tdr), clamps device 0 to 2,
# and prints tdr_clean:true | UNSAFE. Exit 4 if any 4101 fired during the run.
```
This is the run to do when the operator is ready — heavy on Card B, light on the
display card, watched, and self-invalidating if it ever crosses a reset. The clean
number it produces *replaces* the retracted symmetric `two-card-goodput`.

## Finding the safe display cap (the sweep)
`cap=2` is a conservative guess, not a measurement — we have no TDR-free data on the
display card under load. The sweep ramps device-0 concurrency under the guard and stops
at the first reset; the last clean cap is the safe headroom. **Crash-durable:** each step
is fsync'd to `results/raw/display-cap-sweep.jsonl` *before* the next, because the ceiling
step is expected to reset the display (and may blank the app) — the data survives it.
```
python -m denning.denningd --sweep --sweep-cards 1 --max-cap 8     # display card SOLO (cleanest)
python -m denning.denningd --sweep --dry-run                        # no GPU: verify the ramp
```
Solo (device 0 only) isolates the display card's threshold from Card B. Costs ~1 display
reset by design (the step that crosses the ceiling). Per-step output: `display_cap`,
`d0_slo_met`, `d0_tbt_median_ms`, `tdr`, `tdr_delta`.

## Process fix
The original two-card runs executed **without** the watchdog (it was only wired into
the H1 hog experiments). Rule, now enforced by `--serve`'s defaults: **no display-card
load without the watchdog armed and a TDR pre/post check.**
