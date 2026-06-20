# Operational Safety Runbook

*Flight-operations doc for the denning rig (added from the NASA-mission-sim lens, 4-lens review 2026-06-19). The science plan (`prereg/`) governs WHAT we measure; this governs WHETHER it is safe to run, HOW to abort, and HOW to know a run is valid. The rig has a documented **loss-of-vehicle history** (BSOD under load, a shared-memory cascade with audible symptoms and 20-min hangs that once threatened BIOS-reflash recovery) — treat every run as a flight.*

## Prime directives
1. **You can't fix what you can't see.** No run yields a citable result unless its recording contains the signal the prediction is scored on (see blind-spot table §4).
2. **Install the abort before you test the thruster.** The pure-observer safing watchdog **exists and is rehearsed** ([`../ops/safing_watchdog.py`](../ops/safing_watchdog.py) — built + all-six-modes tested 2026-06-19) and must be **armed** before the adversarial-VRAM-hog (H1) run. Pre-flight via [`../ops/preflight.py`](../ops/preflight.py). See [`../ops/README.md`](../ops/README.md).
3. **Abort ≠ refutation.** An aborted/failed run is marked **VOID** and re-run after safing — it is an operational event, not a scientific result. A *refuted prediction* is a scientific success (different thing).

## 1. Pre-flight checklist & GO/NO-GO (complete + log to the workbook before EVERY run)

> Automated by [`../ops/preflight.py`](../ops/preflight.py) (C: > 100 GB, commit/RAM headroom, D: room, b70tools present + enumerates, `--model` exists → GO / NO-GO). Run it first; the manual items below (driver/build/sha pins, display routing) still need an operator eye.

- [ ] Intel Arc driver == pinned frozen value (e.g. `32.0.101.8826` — confirm against the campaign manifest)
- [ ] SYCL/Vulkan backend build hash == frozen; llama.cpp commit == frozen
- [ ] Model file sha256 verified against manifest
- [ ] Caches/models on **D:** confirmed; **C: free > 100 GB** (the redline)
- [ ] b70tools telemetry RUNNING and emitting — heartbeat seen AND the specific signal THIS hypothesis is scored on confirmed present (not in a §4 blind spot)
- [ ] Display routing recorded (iGPU vs which card); compute card headless if possible
- [ ] Commit headroom GREEN at idle (`host.commit.*` well under the wall — commit, not free RAM, is the ceiling)
- [ ] Idle GPU clocks/thermals recorded (drift baseline)
- [ ] Prior run archived; recovery runbook (this doc) open; safing watchdog armed (once it exists)
- [ ] **Operator GO / NO-GO logged with timestamp**

## 2. Malfunction procedures (one per known failure mode)

| Failure mode | Symptom | Detection signal | ABORT criterion | Safing steps | Recovery / RTS | Run disposition |
|---|---|---|---|---|---|---|
| **BSOD under load (0xD1 / mode-set-under-load)** | hard crash | n/a (post-mortem: minidump) | n/a (already down) | power-cycle; do NOT re-launch same config until cause re-confirmed | re-run the *exact* crash conditions at small scale to confirm the fix (BSOD-fix discipline) before trusting | VOID |
| **Secure-desktop switch under load** (Win+Shift+S, Ctrl+Alt+Del) | freeze/instability when the secure desktop activates mid-inference | operator-observed; watchdog no-progress | do not perform secure-desktop actions during a run; if it happens, treat as potential corruption | stop workload, capture final snapshot, verify GPU state via b70tools `adapters`/`verdict` | VOID if it occurred during measurement |
| **Shared-memory cascade** | audio chop; prompt hanging >>expected (20-min); free RAM collapsing | PDH `vram.non_local` climbing past the `verdict` spill ceiling; `host.commit.*` toward the wall | non_local over ceiling for > N s, OR commit > 90% | stop workload immediately (before it walks toward non-POST); capture snapshot | reduce ctx/KV-quant/`-fit off`/model size so it fits dedicated VRAM; re-verify with `verdict` | VOID |
| **TDR / device-loss / re-enumeration** | hang then recovery, or device lost | b70tools AdapterState → `PostTDR` / `Lost` / `Reenumerating`; epoch boundary event | any transition into PostTDR/Lost | safe-stop workload; let re-enum settle; confirm identity via PCI-BDF (LUID drifts) | restart from clean state; check driver unchanged | VOID |
| **Commit-charge exhaustion** | allocation failures despite "free" RAM | `host.commit.*` > 90% (the TRUE wall; free physical RAM reads safe) | commit > 90% sustained | stop workload; close background commit hogs; `--no-mmap` off | re-plan working set to fit commit headroom | VOID |

## 3. Unattended / overnight-run standard

Any unattended run MUST:
- (a) have b70tools recording to **D:** with the 30 s heartbeat **confirmed before walk-away**;
- (b) emit a **separate watchdog log** timestamping the last-progress signal (tokens decoded or telemetry heartbeat) so a hang is distinguishable from a slow run and **time-of-death is known**;
- (c) have an **external watchdog action** — [`../ops/safing_watchdog.py`](../ops/safing_watchdog.py) `--enforce --child-pid <PID>` (commit / RAM / `non_local` / TDR / telemetry-staleness → SAFE/ABORT → `taskkill`), so a hung box does not sit at the non-POST edge until morning. *(Rehearsed 2026-06-19: all six failure modes caught via `--simulate`; telemetry-staleness → ABORT satisfies "time-of-death is known".)*;
- (d) define success/failure so the operator can decide **VALID / VOID / RE-RUN from the recording alone.**

*Cautionary tale: prior overnight `c65536`/`c131072` runs produced empty result files — unattended runs already fail silently and leave nothing diagnosable. This standard exists to fix exactly that.*

## 4. Telemetry coverage & known blind spots

**Rule:** do not run an experiment whose load-bearing signal is in a blind spot without a compensating instrument.

| Signal | Observable via | Blind spot / caveat |
|---|---|---|
| Per-process VRAM budget/usage | `dxgi_query_video_memory` | per-process only; reads ~KiB for the workload (weights invisible) |
| Cross-process VRAM incl. **shared/spill** | `pdh_gpu_memory` (Dedicated + Shared) | **nearly blind under SYCL/Level-Zero** (1 GB reported while 29 GB resident) — H1 on SYCL flies its primary gauge unplugged |
| System-wide per-adapter VRAM | `d3dkmt_query_statistics` | **non-functional on Win10 19045** (`INVALID_PARAMETER`) — use PDH |
| Host RAM / **commit** | `host_memory` (`host.commit.*`) | the true wall is commit, not free RAM |
| Engine util / power / thermals | `pdh_gpu_engine`, `igcl_power_telemetry` | top-slot card emits some bogus voltage/freq/activity (flagged by arbitration) |
| **Game frame-pacing** (H1's co-tenancy half) | PresentMon (NOT b70tools) | **not currently captured** — the prior WoW run recorded no frame-times; H1's frame-pacing half is unmeasurable without it |

**Consequence routed to USER-DECIDES:** H1's eviction signal (PDH non_local) is blind under SYCL while the cross-notes say "run on SYCL where it wins" → decide H1's engine (lean Vulkan, where PDH reads cleanly) and require PresentMon for the frame-pacing half. See the decision list.
