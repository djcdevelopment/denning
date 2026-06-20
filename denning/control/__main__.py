#!/usr/bin/env python3
r"""Control-plane self-test: `python -m denning.control` (no GPU load).

Checks the engine-agnostic invariants the control plane must hold:
  1. admission predicts the measured H1 demotion cliff (I-4a, 5/5)
  2. capacity composes 8 -> 16 across two cards (the two-card goodput thesis)
  3. the router balances sessions across replica-per-card backends
  4. (on-rig, informational) the live VidMm budget is readable
"""

from __future__ import annotations

import sys
from collections import Counter

from denning.control import budget as budgetmod
from denning.control.admission import AdmissionController, validate_h1_sweep
from denning.control.router import ReplicaRouter, system_capacity


def main() -> int:
    fails = 0

    print("[1] admission predicts the H1 cliff (I-4a):")
    ok, tot = validate_h1_sweep(verbose=True)
    print(f"    -> {ok}/{tot}")
    fails += (ok != tot)

    print("\n[2] capacity composition (two-card thesis):")
    ctrl = AdmissionController(kv_per_session_gb=0.1)   # memory term 132 here; compute knee 8 binds
    cap1 = ctrl.capacity(31.12)
    cap2 = system_capacity(ctrl, [31.12, 31.12])
    print(f"    one card N*={cap1}   two cards N*={cap2}   (expect 8 -> 16)")
    fails += not (cap1 == 8 and cap2 == 16)
    # and the memory term really does bind when a co-tenant shrinks the budget:
    squeezed = ctrl.capacity(18.0)                      # 18 GB live: only ~0.1 GB over weights
    print(f"    under co-tenant (live 18.0 GB) N*={squeezed}  (memory term now binds)")
    fails += not (squeezed < cap1)

    print("\n[3] router balance across replica-per-card:")
    rr = Counter(ReplicaRouter([8240, 8241]).round_robin(16))
    print(f"    round-robin 16 -> {dict(rr)}")
    fails += not (rr[8240] == 8 and rr[8241] == 8)
    r2 = ReplicaRouter([8240, 8241])
    ll = Counter(r2.least_loaded() for _ in range(16))
    print(f"    least-loaded 16 -> {dict(ll)}")
    fails += not (ll[8240] == 8 and ll[8241] == 8)

    print("\n[4] live VidMm budget (on-rig; informational):")
    for a in (0, 1):
        b = budgetmod.read_live_budget_gb(a)
        print(f"    adapter {a}: {b} GB" + ("" if b is not None else "  (probe unavailable)"))

    print("\n[control] SELFTEST", "PASS" if fails == 0 else f"FAIL ({fails})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
