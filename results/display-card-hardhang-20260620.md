# Incident — display-card serving HARD-HANGS the rig; safe cap is 0 (2026-06-20)

*Escalation of [`two-card-TDR-contamination-20260620`](two-card-TDR-contamination-20260620.md).
A device-0 (display card) concurrency sweep did not produce a recoverable TDR — it
**locked the entire system** (UI + mouse frozen), the display driver never recovered,
and the operator had to **hard power-cycle** after ~15 minutes. This supersedes the
"asymmetric cap" plan: on this rig the display card cannot serve inference at all.*

## What was run
`python -m denning.denningd --sweep --sweep-cards 1 --max-cap 8` — ramp the display
card (device 0) **solo** from 1 concurrent session upward under the TDR guard. The
intent was to find the highest safe concurrency; the assumption (wrong) was that
crossing the limit would be a *recoverable* TDR the guard could catch.

## What happened (the data)
**Sweep durable log** (`results/raw/display-cap-sweep.jsonl`, fsync'd per step — survived the reboot):
```
{"event":"sweep_start","max_cap":8,"sweep_cards":1,"dry":false}
{"display_cap":1,"d0_admitted":1,"d0_slo_met":0,"d0_tbt_median_ms":null,"tdr":false,"tdr_delta":0}
```
- At **cap=1** (a *single* session) the display card admitted it but produced **no valid tokens** (`tbt=null`, SLO not met) — already broken.
- At **cap=2** the box **hard-hung** — no row was ever written.

**Windows System log:**
| time | event | meaning |
|---|---|---|
| 3:59:52 / 4:00:25 AM | 4101 `igfxnd` ×2 | the *earlier* `--serve --cards 2` run — TDRs that **recovered** |
| (sweep hang) | **no 4101** | the driver **never recovered** — a hard hang logs no recovery event |
| 4:50:32 AM | 6008 | "previous shutdown was unexpected" (the operator's forced power-off) |
| 5:08:26 AM | 41 Kernel-Power | "rebooted without cleanly shutting down" |

No BugCheck (1001) → not a BSOD with a dump; a true unresponsive hang, consistent with
the operator's account (mouse locked, 15 min dead, manual reboot).

## Findings
1. **The display card cannot serve inference on this rig.** Not "cap it low" — *one*
   session broke and *two* hard-hung the machine. The safe concurrency is **0**.
2. **The failure mode is system-fatal, not graceful.** Earlier device-0 loads produced
   *recoverable* TDRs (monitor blanks, returns). This one produced an unrecoverable hard
   hang requiring a power-cycle. The same operating region can do either — which makes it
   categorically unsafe, because the bad outcome is loss-of-machine.
3. **The safety harness was blind to it.** The TDR guard / watchdog `--watch-tdr` key on
   Event ID **4101**, which is logged on *recovery*. A hard hang never recovers, so **no
   4101 is ever written** and the guard cannot fire. You cannot instrument your way to
   safe display-card serving when the failure mode produces no signal until after it is
   catastrophic.
4. **Plausible aggravator (honest caveat):** the sweep ran ~30 min after the same display
   card had TDR'd twice (3:59/4:00). The driver may have been in a fragile post-TDR state,
   turning what might otherwise have been another recoverable TDR into a hard hang. We are
   **not** testing that hypothesis — probing device 0 is over. The policy is categorical.

## Consequence for the thesis
This sharpens — and partly corrects — the multi-card story. On a fabric-less consumer
box where one GPU drives the desktop, that GPU is **not a degraded-but-usable serving
participant; it is unavailable for serving** (the failure mode is a system hang). So:

> **The box's safe serving capacity = (non-display cards) × per-card N\*.**
> On this 2-card rig that is **one card** (Card B / device 1). There is no safe "2× by
> replication" here — the display card is reserved for the display, full stop. Real
> multi-card scaling on this substrate needs **headless** cards (none driving a display).

The retracted `two-card-goodput` and provisional `two-card-scaling` numbers are not just
contaminated — the configuration that produced them is **unsafe to reproduce**. The clean
two-card result will not exist on this hardware; the honest claim is single-card serving
+ the *threat model* (the display GPU is an OS-arbitrated co-tenant you cannot serve on).

## Code response (safe by default now)
- `denningd` default **`display_cap=0`** → the display card (device 0) **serves nothing**;
  it is never spawned or routed to. Only headless cards serve. (`display_device=None`
  means "no display card present, serve all" — for fake-engine tests only.)
- `--serve` reports `serving_devices` + `display_card_excluded` so it's never ambiguous.
- `--sweep` **refuses** to touch device 0 (prints the known result) unless
  `--force-display-unsafe` — which should never be used on this rig.
- Verified off-rig: `tests/test_shim.py` PASS incl. "default excludes the display card";
  `--sweep` prints the refusal; `--dry-run` still demonstrates routing via `display_device=None`.

## Standing rule
**Never serve inference on the display card on this rig. Serve on Card B (device 1) only.**
On-rig GPU work resumes only on explicit, narrow operator direction, never on device 0.
