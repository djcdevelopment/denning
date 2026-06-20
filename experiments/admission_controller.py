#!/usr/bin/env python3
r"""
denning closed-form admission controller (I-4a) -- the defense.

The I-3 finding: you CANNOT pin VRAM against a co-tenant (VidMm splits the budget
~evenly regardless of residency priority). So the defense is ADMISSION CONTROL on
the LIVE budget signal -- admit work only while the resident footprint fits the
budget VidMm currently grants, and order your own eviction (cold blocks first) for
whatever must spill. This module is the closed-form rule + a live budget reader,
validated against the measured H1 demotion cliff.

Rule (cost-model section 2), with model weights W (GB), per-session KV k(ctx) (GB),
and the LIVE VidMm budget B (GB):
    N*(B)        = floor((B - W) / k(ctx))      # max concurrent sessions kept resident
    admit(d)     = footprint(d) <= B            # else DEFER / shed cold blocks first

Live B is read from IDXGIAdapter3::QueryVideoMemoryInfo via the D3D12 probe
(--size-gb 0 = pure monitor). The point of I-4a: the OS hands you the admission
limit in real time; staying under it is the whole defense.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

PROBE = r"D:\work\denning\experiments\d3d12_residency_probe.exe"

# --- measured constants (this rig) ---
CARD_BUDGET_GB = 31.12      # VidMm budget, uncontended (probe, H1)
MODEL_W_GB = 17.9           # Qwen3-30B-A3B Q4 resident weights (h1r local peak 17.87)
# H1 resident hog sweep (measured): hog cap GB -> decode ratio (cliff := ratio < 0.8)
SWEEP = [(10, 0.998), (12, 0.997), (14, 0.231), (16, 0.196), (18, 0.165)]


def read_live_budget_gb(adapter: int = 0) -> float | None:
    """Live VidMm budget for `adapter` via the D3D12 probe in monitor mode."""
    try:
        p = subprocess.run([PROBE, "--adapter", str(adapter), "--size-gb", "0", "--hold-s", "1"],
                           capture_output=True, text=True, timeout=20)
        m = re.findall(r"budget ([0-9.]+)", p.stdout)
        return float(m[-1]) if m else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def n_star(budget_gb: float, weights_gb: float, kv_per_session_gb: float) -> int:
    if kv_per_session_gb <= 0:
        return 0
    return max(0, int((budget_gb - weights_gb) // kv_per_session_gb))


def admit(footprint_gb: float, budget_gb: float) -> bool:
    return footprint_gb <= budget_gb


def validate_against_sweep() -> bool:
    """Does 'admit iff weights <= live budget' predict the measured H1 cliff?"""
    print(f"{'hog GB':>6} {'eff budget':>11} {'fits?':>6} {'controller':>11} {'measured':>9} {'match':>6}")
    ok = 0
    for hog, ratio in SWEEP:
        eff = CARD_BUDGET_GB - hog           # budget left to the model under the co-tenant
        fits = MODEL_W_GB <= eff
        decision = "ADMIT" if fits else "DEFER"
        measured = "fast" if ratio >= 0.8 else "CLIFF"
        match = (fits and ratio >= 0.8) or ((not fits) and ratio < 0.8)
        ok += int(match)
        print(f"{hog:>6} {eff:>9.1f}G {str(fits):>6} {decision:>11} {measured:>9} {('Y' if match else 'N'):>6}")
    print(f"\nThe closed-form rule predicts the cliff on {ok}/{len(SWEEP)} sweep points.")
    print(f"(model {MODEL_W_GB} GB stops fitting when hog > {CARD_BUDGET_GB - MODEL_W_GB:.1f} GB "
          f"-> DEFER at cap 14, exactly the measured cliff.)")
    return ok == len(SWEEP)


def main() -> int:
    ap = argparse.ArgumentParser(description="denning closed-form admission controller (I-4a)")
    ap.add_argument("--adapter", type=int, default=0)
    ap.add_argument("--weights-gb", type=float, default=MODEL_W_GB)
    ap.add_argument("--kv-gb", type=float, default=0.1, help="per-session KV footprint (GB)")
    ap.add_argument("--no-live", action="store_true", help="skip the live budget read")
    args = ap.parse_args()

    print("=== live VidMm budget (the admission oracle) ===")
    if args.no_live:
        live = CARD_BUDGET_GB
        print(f"(using nominal {live} GB)")
    else:
        live = read_live_budget_gb(args.adapter)
        print(f"adapter {args.adapter} live budget: {live} GB")
    if live:
        print(f"N* sessions  (W={args.weights_gb} GB, KV/session={args.kv_gb} GB) = "
              f"{n_star(live, args.weights_gb, args.kv_gb)}")
        print(f"admit a {args.weights_gb} GB model? {admit(args.weights_gb, live)}")

    print("\n=== validation vs the measured H1 demotion cliff ===")
    allmatch = validate_against_sweep()
    print("\nI-4a result:", "RULE VALIDATED" if allmatch else "MISMATCH -- investigate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
