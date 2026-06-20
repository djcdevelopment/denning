#!/usr/bin/env python3
r"""
denning pre-flight checklist (I-1) — the one-shot "GO / NO-GO" gate.

Run BEFORE any experiment that touches the GPU. Verifies the rig is in a known-
safe launch configuration (the operator's hard rules + the cascade precursors the
watchdog will then monitor in-flight). Complements `safing_watchdog.py`:
  * preflight = one-shot launch gate (this file),
  * watchdog  = continuous in-flight monitor.

Hard rules (a FAIL blocks launch, exit != 0):
  * C: free > 100 GB         (operator: <=100 GB is a bad day / start pruning)
  * b70tools.exe present      (the in-flight instrument the watchdog consumes)
  * --model file exists       (if a model path is given)

Advisories (WARN, exit still 0):
  * C: free < 105 GB          (close to the redline)
  * commit charge < 80% start
  * physical RAM free > 8 GB start
  * D: working-drive free > 50 GB (room for recordings/outputs)
  * GPU enumerable via b70tools --enumerate

Usage:
  python ops/preflight.py
  python ops/preflight.py --model "D:\work\battlemage\models\Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf"
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

from safing_watchdog import host_memory, disk_c_free_gb, GIB

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
SYM = {PASS: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]"}


def free_gb(path: str) -> float:
    try:
        return shutil.disk_usage(path).free / GIB
    except OSError:
        return float("nan")


def check_b70_enumerate(b70_exe: str) -> tuple[str, str]:
    if not os.path.isfile(b70_exe):
        return FAIL, "b70tools.exe not found"
    try:
        p = subprocess.run([b70_exe, "--enumerate"], capture_output=True,
                           text=True, timeout=30)
        n = p.stdout.count("adapter_")
        if p.returncode == 0:
            return PASS, f"enumerated ({n} adapter refs in output)"
        return WARN, f"--enumerate rc={p.returncode}"
    except (OSError, subprocess.TimeoutExpired) as e:
        return WARN, f"enumerate failed: {e}"


def main() -> int:
    ap = argparse.ArgumentParser(description="denning pre-flight checklist (I-1)")
    ap.add_argument("--model", help="model file that must exist for this run")
    ap.add_argument("--b70-exe", default=r"D:\work\b70tools\build\b70tools.exe")
    ap.add_argument("--min-c-free-gb", type=float, default=100.0)
    args = ap.parse_args()

    rows: list[tuple[str, str, str]] = []  # (status, label, detail)

    # --- hard rule: C: free ---
    c = disk_c_free_gb()
    if c != c or c <= args.min_c_free_gb:
        rows.append((FAIL, "C: free > 100 GB (operator hard rule)", f"{c:.1f} GB"))
    elif c < 105.0:
        rows.append((WARN, "C: free headroom (>105 GB)", f"{c:.1f} GB - near redline"))
    else:
        rows.append((PASS, "C: free > 100 GB", f"{c:.1f} GB"))

    # --- host memory at launch ---
    try:
        hm = host_memory()
        cp = hm["commit_pct"]
        rows.append(((PASS if cp < 80 else WARN), "commit charge < 80% at start", f"{cp:.1f}%"))
        phys_free = hm["phys_total_gb"] - hm["phys_used_gb"]
        rows.append(((PASS if phys_free > 8 else WARN), "physical RAM free > 8 GB", f"{phys_free:.1f} GB free"))
    except OSError as e:
        rows.append((WARN, "host memory readable", str(e)))

    # --- D: working drive ---
    d = free_gb("D:\\")
    rows.append(((PASS if d > 50 else WARN), "D: working drive free > 50 GB", f"{d:.1f} GB"))

    # --- b70tools present + enumerates ---
    if os.path.isfile(args.b70_exe):
        st, detail = check_b70_enumerate(args.b70_exe)
        rows.append((PASS, "b70tools.exe present", args.b70_exe))
        rows.append((st, "GPU enumerable via b70tools", detail))
    else:
        rows.append((FAIL, "b70tools.exe present", f"missing: {args.b70_exe}"))

    # --- watchdog importable (we already imported it) ---
    rows.append((PASS, "safing_watchdog importable", "ok"))

    # --- model (optional, hard if given) ---
    if args.model:
        if os.path.isfile(args.model):
            sz = os.path.getsize(args.model) / GIB
            rows.append((PASS, "model file exists", f"{os.path.basename(args.model)} ({sz:.1f} GB)"))
        else:
            rows.append((FAIL, "model file exists", f"missing: {args.model}"))

    # --- report ---
    print("=" * 72)
    print("denning PRE-FLIGHT CHECKLIST")
    print("=" * 72)
    for st, label, detail in rows:
        print(f"  {SYM[st]}  {label:<42}  {detail}")
    print("=" * 72)
    fails = [r for r in rows if r[0] == FAIL]
    warns = [r for r in rows if r[0] == WARN]
    if fails:
        print(f"NO-GO — {len(fails)} hard check(s) failed. Resolve before launch.")
        return 1
    if warns:
        print(f"GO (with {len(warns)} advisory warning(s)). Arm the watchdog for the run.")
        return 0
    print("GO — all clear. Arm the watchdog for the run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
