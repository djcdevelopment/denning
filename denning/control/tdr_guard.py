#!/usr/bin/env python3
r"""TDR guard -- detect Windows display-driver resets, so a run can't silently
report numbers collected across one.

Why this exists: the two-card runs of 2026-06-19/20 tripped four display-driver
TDRs (Windows System log, Event ID 4101, `igfxnd`) and the goodput numbers were
collected across two of them -- discovered only by reading the event log after the
fact (see results/two-card-TDR-contamination-20260620.md). This makes that check a
first-class part of every on-rig run: snapshot the 4101 count before, compare after;
a non-zero delta marks the result UNSAFE. It also feeds the I-1 safing watchdog a
live TDR signal (its `adapter_state == PostTDR` -> ABORT path had nothing driving it).

Pure event-log reads (no GPU load), so it runs anywhere Windows + Get-WinEvent exist;
off-Windows / no events it degrades to count 0 / None and never raises.
"""

from __future__ import annotations

import subprocess


def count_4101(start_time: str | None = None, timeout_s: float = 30.0) -> int | None:
    """Count System-log Event ID 4101 (display TDR), optionally since `start_time`
    (a string Get-WinEvent accepts, e.g. '2026-06-20 03:50:00'). None on failure."""
    filt = "@{LogName='System'; Id=4101}" if not start_time \
        else f"@{{LogName='System'; Id=4101; StartTime='{start_time}'}}"
    ps = ("$ErrorActionPreference='SilentlyContinue';"
          f" $e = Get-WinEvent -FilterHashtable {filt};"
          " if ($null -eq $e) { 0 } else { @($e).Count }")
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=timeout_s)
        out = (p.stdout or "").strip()
        return int(out) if out.isdigit() else 0
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


class TdrGuard:
    """Snapshot the TDR count, then ask whether any reset happened since."""

    def __init__(self):
        self.baseline: int | None = None

    def arm(self) -> int | None:
        self.baseline = count_4101()
        return self.baseline

    def current(self) -> int | None:
        return count_4101()

    def delta(self) -> int | None:
        cur = self.current()
        if cur is None or self.baseline is None:
            return None
        return cur - self.baseline

    def tripped(self) -> bool:
        """True iff a TDR is known to have occurred since arm() (fail-safe: a probe
        failure returns False here but clean() returns False too -- see below)."""
        d = self.delta()
        return d is not None and d > 0

    def clean(self) -> bool:
        """True ONLY if we positively confirmed zero TDRs since arm(). A probe
        failure (delta None) is NOT clean -- absence of evidence isn't evidence."""
        return self.delta() == 0
