#!/usr/bin/env python3
r"""
denning safing watchdog (I-1) — pure-observer rig-safety supervisor.

WHY THIS EXISTS
---------------
On this rig the host-memory / Shared-GPU-Memory OOM cascade has previously
driven a non-POST + BIOS reflash ("loss of vehicle"). b70tools' `verdict`
documents the same: the smoking gun is host-RAM exhaustion + per-card
`non_local` (Shared GPU Memory) commit. Before denning runs any experiment
unattended, a watchdog must catch the danger *before* it becomes unrecoverable.

WHAT IT DOES
------------
Polls, every `--interval` seconds, the signals that precede a cascade:
  * commit charge %        (GetPerformanceInfo CommitTotal/CommitLimit) — the
                            binding host wall (prior finding A4: commit, not
                            free RAM, is what binds).
  * physical RAM used GB   (GetPerformanceInfo PhysicalTotal/Available).
  * C: free GB             (operator rule: 65 GB comfortable floor, 20 GB hard floor).
  * GPU danger (optional)  via b70tools `verdict --json <dir>`:
                            exit 2 (broken: non_local>2GB etc.) => SAFE,
                            exit 3 (insufficient data) => treated as staleness.
  * telemetry staleness    (b70tools recording stopped advancing) — so a dead
                            instrument is detectable, not silent.

It classifies each tick into OK / WARN / SAFE / ABORT and:
  * always logs a structured JSONL watchdog-log line,
  * prints a loud banner on SAFE/ABORT,
  * (only with `--enforce`) terminates the supervised child to safe the rig.

Default is PURE OBSERVER (log + alert, never kill). Enforcement is opt-in.

REHEARSAL (the I-1 gate: each failure mode is *caught*)
-------------------------------------------------------
`--simulate {host_oom,commit,tdr,spill,disk,telemetry_loss}` injects ONE
synthetic reading (flagged synthetic) and prints the decision — so every abort
path is verified without inducing the real, dangerous condition.

Examples
--------
  # one real sample, print + exit code (0 ok / 1 warn / 2 safe / 3 abort):
  python ops/safing_watchdog.py --once

  # rehearse each failure mode (safe; no real danger):
  python ops/safing_watchdog.py --simulate commit
  python ops/safing_watchdog.py --simulate tdr

  # continuous, observer-only, logging to a file, consuming a b70tools recording:
  python ops/safing_watchdog.py --interval 1 --log run.watchdog.jsonl \
        --b70-dir D:\work\b70tools\out\run-XXXX

  # continuous + ENFORCE: kill the experiment (PID) if the rig enters SAFE/ABORT:
  python ops/safing_watchdog.py --enforce --child-pid 12345 --log run.watchdog.jsonl
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes

GIB = 1024 ** 3

# Optional live display-TDR detector (feeds the PostTDR -> ABORT path below).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from denning.control.tdr_guard import count_4101
except Exception:       # safety tool: never fail to start over a missing import
    count_4101 = None

# ---- decision levels (ordered) ------------------------------------------------
OK, WARN, SAFE, ABORT = "OK", "WARN", "SAFE", "ABORT"
_RANK = {OK: 0, WARN: 1, SAFE: 2, ABORT: 3}
_EXIT = {OK: 0, WARN: 1, SAFE: 2, ABORT: 3}


def worst(a: str, b: str) -> str:
    return a if _RANK[a] >= _RANK[b] else b


# ---- default thresholds (mirrors b70tools verdict + operator rules) -----------
class Thresholds:
    # host RAM used (GB) — recalibrated 2026-06-21: a resident 17GB model legitimately puts
    # phys ~28GB on this 32GB box, and mmap'd model pages are clean/reclaimable, so phys is a
    # SECONDARY backstop near true exhaustion; commit% (below) is the binding signal (finding A4).
    phys_warn_gb = 30.0
    phys_safe_gb = 31.0
    phys_abort_gb = 31.6
    # commit charge (%) — build-roadmap I-1: commit > 90% = safing
    commit_warn_pct = 85.0
    commit_safe_pct = 90.0
    commit_abort_pct = 95.0
    # C: free (GB) — operator rule (2026-06-21): 65 GB is the comfortable floor (WARN);
    # 20 GB is the hard floor where Windows starts choking (SAFE). Models/large files live on D:.
    disk_c_warn_gb = 65.0
    disk_c_safe_gb = 20.0
    # per-card Shared-GPU-Memory non_local (GB) — verdict's hard safety floor
    nonlocal_safe_gb = 2.0
    # telemetry staleness (s) — no fresh b70tools sample => instrument lost
    stale_warn_s = 8.0
    stale_abort_s = 30.0


# ---- Win32 host-memory readings ----------------------------------------------
class PERFORMANCE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("CommitTotal", ctypes.c_size_t),
        ("CommitLimit", ctypes.c_size_t),
        ("CommitPeak", ctypes.c_size_t),
        ("PhysicalTotal", ctypes.c_size_t),
        ("PhysicalAvailable", ctypes.c_size_t),
        ("SystemCache", ctypes.c_size_t),
        ("KernelTotal", ctypes.c_size_t),
        ("KernelPaged", ctypes.c_size_t),
        ("KernelNonpaged", ctypes.c_size_t),
        ("PageSize", ctypes.c_size_t),
        ("HandleCount", wintypes.DWORD),
        ("ProcessCount", wintypes.DWORD),
        ("ThreadCount", wintypes.DWORD),
    ]


def host_memory() -> dict:
    """Commit + physical from GetPerformanceInfo (pages -> GiB)."""
    pi = PERFORMANCE_INFORMATION()
    pi.cb = ctypes.sizeof(pi)
    if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(pi), pi.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    page = pi.PageSize
    commit_total_gb = pi.CommitTotal * page / GIB
    commit_limit_gb = pi.CommitLimit * page / GIB
    phys_total_gb = pi.PhysicalTotal * page / GIB
    phys_avail_gb = pi.PhysicalAvailable * page / GIB
    return {
        "commit_used_gb": round(commit_total_gb, 2),
        "commit_limit_gb": round(commit_limit_gb, 2),
        "commit_pct": round(100.0 * pi.CommitTotal / max(pi.CommitLimit, 1), 1),
        "phys_total_gb": round(phys_total_gb, 2),
        "phys_used_gb": round(phys_total_gb - phys_avail_gb, 2),
    }


def disk_c_free_gb() -> float:
    try:
        return round(shutil.disk_usage("C:\\").free / GIB, 1)
    except OSError:
        return float("nan")


# ---- optional GPU danger via b70tools verdict --------------------------------
def b70_verdict(b70_exe: str, rec_dir: str, timeout_s: float = 15.0) -> dict:
    """Run `b70tools verdict --json <dir>`; map its documented exit codes.

    0 healthy | 2 broken (non_local>floor etc.) | 3 insufficient-data.
    """
    out = {"ran": False, "rc": None, "nonlocal_gb": None, "raw": None}
    try:
        p = subprocess.run(
            [b70_exe, "verdict", "--json", rec_dir],
            capture_output=True, text=True, timeout=timeout_s,
        )
        out["ran"] = True
        out["rc"] = p.returncode
        txt = (p.stdout or "").strip()
        if txt:
            try:
                j = json.loads(txt.splitlines()[-1])
                out["raw"] = j
                for k in ("max_per_card_nonlocal_gb", "nonlocal_gb", "max_nonlocal_gb"):
                    if isinstance(j, dict) and k in j:
                        out["nonlocal_gb"] = j[k]
                        break
            except (ValueError, IndexError):
                pass
    except (subprocess.TimeoutExpired, OSError) as e:
        out["error"] = str(e)
    return out


def rec_age_s(rec_dir: str) -> float | None:
    """Seconds since the b70tools recording last advanced (staleness)."""
    newest = None
    try:
        for name in os.listdir(rec_dir):
            if name.endswith(".jsonl") or name == "events.jsonl":
                m = os.path.getmtime(os.path.join(rec_dir, name))
                newest = m if newest is None else max(newest, m)
    except OSError:
        return None
    if newest is None:
        return None
    return max(0.0, time.time() - newest)


# ---- the decision function (pure; unit-testable with synthetic readings) ------
def evaluate(r: dict, t: Thresholds) -> tuple[str, list[str]]:
    level, reasons = OK, []

    def bump(new, why):
        nonlocal level
        level = worst(level, new)
        reasons.append(f"{new}: {why}")

    cp = r.get("commit_pct")
    if cp is not None:
        if cp >= t.commit_abort_pct:
            bump(ABORT, f"commit {cp:.1f}% >= {t.commit_abort_pct}%")
        elif cp >= t.commit_safe_pct:
            bump(SAFE, f"commit {cp:.1f}% >= {t.commit_safe_pct}%")
        elif cp >= t.commit_warn_pct:
            bump(WARN, f"commit {cp:.1f}% >= {t.commit_warn_pct}%")

    pu = r.get("phys_used_gb")
    if pu is not None:
        if pu >= t.phys_abort_gb:
            bump(ABORT, f"phys-used {pu:.1f}GB >= {t.phys_abort_gb}GB")
        elif pu >= t.phys_safe_gb:
            bump(SAFE, f"phys-used {pu:.1f}GB >= {t.phys_safe_gb}GB")
        elif pu >= t.phys_warn_gb:
            bump(WARN, f"phys-used {pu:.1f}GB >= {t.phys_warn_gb}GB")

    dc = r.get("disk_c_free_gb")
    if dc is not None and dc == dc:  # not NaN
        if dc < t.disk_c_safe_gb:
            bump(SAFE, f"C: free {dc:.0f}GB < {t.disk_c_safe_gb:.0f}GB (operator redline)")
        elif dc < t.disk_c_warn_gb:
            bump(WARN, f"C: free {dc:.0f}GB < {t.disk_c_warn_gb:.0f}GB")

    nl = r.get("nonlocal_gb")
    if nl is not None:
        if nl >= t.nonlocal_safe_gb:
            bump(SAFE, f"Shared-GPU-Memory non_local {nl:.1f}GB >= {t.nonlocal_safe_gb}GB")

    if r.get("adapter_state") in ("PostTDR", "Lost"):
        bump(ABORT, f"AdapterState={r['adapter_state']} (TDR / device lost)")

    if r.get("verdict_rc") == 2:
        bump(SAFE, "b70tools verdict=broken (rc=2)")

    age = r.get("telemetry_age_s")
    if age is not None:
        if age >= t.stale_abort_s:
            bump(ABORT, f"telemetry stale {age:.0f}s >= {t.stale_abort_s}s (instrument lost)")
        elif age >= t.stale_warn_s:
            bump(WARN, f"telemetry stale {age:.0f}s >= {t.stale_warn_s}s")

    return level, reasons


# ---- reading assembly ---------------------------------------------------------
def take_reading(args, t: Thresholds) -> dict:
    r = {"ts": round(time.time(), 3)}
    try:
        r.update(host_memory())
    except OSError as e:
        r["host_error"] = str(e)
    r["disk_c_free_gb"] = disk_c_free_gb()

    if getattr(args, "watch_tdr", False) and count_4101 is not None:
        c = count_4101()
        if c is not None:
            b = getattr(args, "_tdr_baseline", None)
            if b is None:
                args._tdr_baseline = b = c      # baseline on the first tick
            r["tdr_count"] = c
            r["tdr_baseline"] = b
            if c > b:                            # a new display reset since arming
                r["adapter_state"] = "PostTDR"   # -> evaluate() bumps ABORT

    if args.b70_dir:
        v = b70_verdict(args.b70_exe, args.b70_dir)
        r["verdict_rc"] = v.get("rc")
        if v.get("nonlocal_gb") is not None:
            r["nonlocal_gb"] = v["nonlocal_gb"]
        age = rec_age_s(args.b70_dir)
        if age is not None:
            r["telemetry_age_s"] = round(age, 1)
    return r


SYNTH = {
    "host_oom": {"phys_used_gb": 30.2, "commit_pct": 96.0},
    "commit": {"commit_pct": 91.0},
    "tdr": {"adapter_state": "PostTDR"},
    "spill": {"nonlocal_gb": 3.1},
    "disk": {"disk_c_free_gb": 98.0},
    "telemetry_loss": {"telemetry_age_s": 45.0},
}


def banner(level: str, reasons: list[str]) -> None:
    bar = "=" * 64
    sys.stderr.write(f"\n{bar}\n[denning watchdog] *** {level} ***\n")
    for why in reasons:
        sys.stderr.write(f"  - {why}\n")
    sys.stderr.write(f"{bar}\n")
    sys.stderr.flush()


def enforce_kill(pid: int) -> bool:
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, text=True, timeout=10)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def emit_log(path: str | None, record: dict) -> None:
    line = json.dumps(record, separators=(",", ":"))
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="denning safing watchdog (I-1)")
    ap.add_argument("--interval", type=float, default=1.0, help="poll seconds (continuous mode)")
    ap.add_argument("--once", action="store_true", help="single sample, print, exit")
    ap.add_argument("--simulate", choices=sorted(SYNTH), help="inject one synthetic reading and decide")
    ap.add_argument("--log", help="append structured JSONL watchdog-log here")
    ap.add_argument("--watch-tdr", action="store_true",
                    help="poll Windows Event ID 4101; a new display TDR since arming => ABORT")
    ap.add_argument("--b70-dir", help="b70tools recording dir to consult via `verdict`")
    ap.add_argument("--b70-exe", default=r"D:\work\b70tools\build\b70tools.exe")
    ap.add_argument("--enforce", action="store_true", help="kill --child-pid on SAFE/ABORT (default: observe only)")
    ap.add_argument("--child-pid", type=int, help="PID to terminate when enforcing")
    ap.add_argument("--enforce-at", choices=[SAFE, ABORT], default=SAFE, help="min level that triggers a kill")
    args = ap.parse_args()
    t = Thresholds()

    def handle(r: dict) -> str:
        level, reasons = evaluate(r, t)
        rec = {**r, "level": level, "reasons": reasons}
        emit_log(args.log, rec)
        print(json.dumps(rec, separators=(",", ":")))
        if _RANK[level] >= _RANK[WARN]:
            banner(level, reasons)
        if args.enforce and args.child_pid and _RANK[level] >= _RANK[args.enforce_at]:
            killed = enforce_kill(args.child_pid)
            banner(level, [f"ENFORCED: taskkill PID {args.child_pid} -> {'ok' if killed else 'FAILED'}"])
        return level

    if args.simulate:
        r = take_reading(args, t)
        r.update(SYNTH[args.simulate])
        r["synthetic"] = args.simulate
        return _EXIT[handle(r)]

    if args.once:
        return _EXIT[handle(take_reading(args, t))]

    # continuous
    sys.stderr.write(f"[denning watchdog] armed (interval={args.interval}s, "
                     f"enforce={'ON @'+args.enforce_at if args.enforce else 'off'}). Ctrl-C to stop.\n")
    try:
        while True:
            level = handle(take_reading(args, t))
            if level == ABORT and args.enforce:
                return _EXIT[ABORT]
            time.sleep(args.interval)
    except KeyboardInterrupt:
        sys.stderr.write("\n[denning watchdog] stopped.\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
