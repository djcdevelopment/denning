# Workbook — 2026-06-19 — I-1 safing watchdog (operational foundation)

*Build → test → document. The pure-observer rig-safety layer ([`../docs/build-roadmap.md`](../docs/build-roadmap.md) I-1) that lets later increments run unattended. Unblocks H1 / I-3.*

## Why now
G0 cleared + `prereg-launch-suppositions` tagged this morning. The roadmap's per-increment loop requires *"RUN on the rig (pre-flight checklist + watchdog armed)"* — so the watchdog is the gating prerequisite before any unattended GPU experiment (H1's adversarial VRAM-hog especially). The rig has a documented loss-of-vehicle mode: the host-RAM / Shared-GPU-Memory OOM cascade previously caused a **non-POST + BIOS reflash** (per b70tools `verdict`).

## Built (`ops/`)
- **`safing_watchdog.py`** — continuous monitor. Polls commit charge + physical RAM (Win32 `GetPerformanceInfo`), C: free (operator redline), and — optionally — GPU danger via b70tools `verdict --json <dir>` exit codes + recording staleness. Classifies OK/WARN/SAFE/ABORT; structured JSONL log; loud banner; **observer by default**, `--enforce` kills the supervised PID. Stdlib + ctypes only (runs with zero GPU dependency, so it can't be taken down by the thing it watches).
- **`preflight.py`** — one-shot GO/NO-GO launch gate (C:>100 GB hard rule, commit/RAM headroom, D: room, b70tools present + enumerates, model exists).
- **`README.md`** — decision table, run pattern, log format.

## Tested (the I-1 gate: each failure mode is *caught*)
Rehearsed via `--simulate` (synthetic injection — no real danger induced):
| mode | injected | → level | rc |
|---|---|---|---|
| host_oom | commit 96% + phys 30.2 GB | ABORT | 3 |
| commit | 91% | SAFE | 2 |
| tdr | AdapterState=PostTDR | ABORT | 3 |
| spill | non_local 3.1 GB | SAFE | 2 |
| disk | C: 98 GB | SAFE | 2 |
| telemetry_loss | stale 45 s | ABORT | 3 |

All caught. **Real `--once`** read true state — commit 38.3%, phys-used 9.4 GB, **C: free 103.7 GB → WARN** (genuinely near the redline; the warn path fires on live data, not just synthetic). **`preflight`** = GO + 1 advisory (model 17.3 GB found; 2 adapters enumerated; D: 1569 GB).

## Result
I-1 build + test **DONE**. The rig can now run experiments unattended behind a pure-observer watchdog that escalates to enforcement (`taskkill`) on demand. The "data missing is detectable" requirement is met via telemetry-staleness → ABORT.

## Next
Unblocks **I-3** — the pinned arena + the **H1** adversarial-VRAM-hog eviction test (the tagged P0 prediction, make-or-break-A). H1 still needs: (a) this watchdog [done], (b) a VRAM-hog to induce DXGI-budget pressure on the compute card, (c) the arena/serving target. Build order next session: the VRAM-hog + the H1 harness, run under the watchdog.

## Manifest
`ops/safing_watchdog.py` · `ops/preflight.py` · `ops/README.md`. Validated on driver 32.0.101.8826, dual Arc Pro B70, 32 GB RAM. Python: `.venv` (stdlib only).
