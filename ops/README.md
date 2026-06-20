# ops/ — operational foundation (I-1)

The pure-observer rig-safety layer that lets denning experiments run unattended
without risking loss-of-vehicle. Two tools:

| Tool | Role | When |
|---|---|---|
| [`preflight.py`](preflight.py) | one-shot GO / NO-GO launch gate | before each GPU run |
| [`safing_watchdog.py`](safing_watchdog.py) | continuous in-flight safety monitor | armed during each GPU run |

## Why
On this rig the host-RAM / Shared-GPU-Memory OOM cascade has previously driven a
**non-POST + BIOS reflash** (loss of vehicle). b70tools' `verdict` encodes the
same smoking guns (host-RAM exhaustion + per-card `non_local` commit). These
tools catch the precursors *before* they become unrecoverable. See also
[`../docs/operational-safety-runbook.md`](../docs/operational-safety-runbook.md).

## Standard run pattern
```powershell
$py = "D:\work\denning\.venv\Scripts\python.exe"
# 1. GO / NO-GO
& $py D:\work\denning\ops\preflight.py --model <model.gguf>
# 2. arm the watchdog (observer-only), logging, consuming a b70tools recording
& $py D:\work\denning\ops\safing_watchdog.py --log run.watchdog.jsonl --b70-dir <b70-out-dir>
# 3. (optional) ENFORCE: kill the experiment PID if the rig enters SAFE/ABORT
& $py D:\work\denning\ops\safing_watchdog.py --enforce --child-pid <PID> --log run.watchdog.jsonl
```

## Safing decision table (`safing_watchdog.py`)
| signal | source | WARN | SAFE | ABORT |
|---|---|---|---|---|
| commit charge % | `GetPerformanceInfo` | ≥85 | ≥90 | ≥95 |
| physical RAM used GB | `GetPerformanceInfo` | ≥23 | ≥26 | ≥29.5 |
| C: free GB | `shutil` | <105 | <100 | — |
| Shared-GPU-Mem `non_local` GB | b70tools `verdict` | — | ≥2.0 | — |
| AdapterState | b70tools | — | — | PostTDR / Lost |
| b70tools `verdict` rc | b70tools | — | rc=2 (broken) | — |
| telemetry staleness s | recording mtime | ≥8 | — | ≥30 |

The tick escalates to the **worst** signal. **Default is observer-only** (log +
loud banner, never kills); `--enforce` adds a `taskkill` of `--child-pid` at
`--enforce-at` (SAFE or ABORT). Process exit code = level (OK 0 / WARN 1 / SAFE 2
/ ABORT 3). Thresholds mirror b70tools `verdict` (`max_host_used_gb=26`,
`max_per_card_nonlocal_gb=2`) + the operator's C:-100 GB rule; override in the
`Thresholds` class.

## Rehearsal (the I-1 gate — each abort path verified, no real danger)
```powershell
& $py safing_watchdog.py --simulate {host_oom|commit|tdr|spill|disk|telemetry_loss}
```

## watchdog-log format (JSONL, one object per tick)
```json
{"ts":1781914101.3,"commit_used_gb":23.3,"commit_pct":38.3,"phys_used_gb":9.4,
 "disk_c_free_gb":103.7,"level":"WARN","reasons":["WARN: C: free 104GB < 105GB"]}
```

## Validated
2026-06-19, live rig: all 6 failure modes caught via `--simulate`; real `--once`
= WARN (C: 103.7 GB, near redline); `preflight` = GO + 1 advisory. **Stdlib +
ctypes only** — the watchdog itself has no torch/GPU dependency, so it can never
be taken down by the thing it is watching.
