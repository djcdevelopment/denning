#!/usr/bin/env python3
r"""Live VidMm budget reader -- denning's admission oracle.

The I-3 finding: you cannot pin VRAM against a co-tenant (VidMm splits the budget
~evenly regardless of D3D12 residency priority). The defense is to *read* the
budget the OS currently grants and admit beneath it. `QueryVideoMemoryInfo.Budget`
drops 31->15 GB the instant a co-tenant appears; that live number is the whole
signal the admission controller runs on.

Thin extraction of experiments/admission_controller.py::read_live_budget_gb -- it
shells out to the compiled D3D12 probe in monitor mode (--size-gb 0, allocates
nothing). Off-rig (no probe) it returns None and the caller falls back to nominal.
"""

from __future__ import annotations

import re
import subprocess

DEFAULT_PROBE = r"D:\work\denning\experiments\d3d12_residency_probe.exe"
CARD_BUDGET_GB = 31.12   # uncontended nominal (probe, H1) -- fallback only


def read_live_budget_gb(adapter: int = 0, probe: str = DEFAULT_PROBE) -> float | None:
    """Live VidMm budget (GB) for `adapter`, or None if the probe is unavailable."""
    try:
        p = subprocess.run([probe, "--adapter", str(adapter), "--size-gb", "0", "--hold-s", "1"],
                           capture_output=True, text=True, timeout=20)
        m = re.findall(r"budget ([0-9.]+)", p.stdout)
        return float(m[-1]) if m else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def budget_or_nominal(adapter: int = 0, probe: str = DEFAULT_PROBE) -> float:
    """Live budget if readable, else the nominal uncontended budget."""
    b = read_live_budget_gb(adapter, probe)
    return b if b is not None else CARD_BUDGET_GB
