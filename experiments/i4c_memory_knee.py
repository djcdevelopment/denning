#!/usr/bin/env python3
r"""
I-4c: the MEMORY-bound admission knee (closes I-4b's gap).

I-4b's knee was COMPUTE-bound (footprint stayed 0 — the serving engine cliffs past
~8 concurrent sequences before VRAM is even pressured). Here we make MEMORY the
binding constraint: a FIXED small N (below the compute knee) but LARGE per-session
KV, with b70tools recording the REAL footprint (PDH `gpu.adapter.vram.{local,
non_local}.bytes_committed`) — the D3D12 probe's Budget did not reflect Vulkan VRAM.

Sweep ctx to find where the KV oversubscribes the card (dedicated saturates,
non_local spill rises, goodput collapses from spill not compute), and check that the
budget rule (footprint ≤ live budget) predicts the cliff — the memory analog of I-4a.

  python experiments/i4c_memory_knee.py --slots 4 --ctx-per-slot 16384
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from h1_eviction_pilot import start_recorder, analyze, start_hog, DEFAULT_MODEL
from h1_resident_pilot import wait_health, stream_tbt, _kill
from i4b_closed_loop import start_server_np, PORT, SLO_TBT_MS, SLO_TTFT_MS


def main() -> int:
    ap = argparse.ArgumentParser(description="I-4c memory-bound admission knee")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--slots", type=int, default=4)
    ap.add_argument("--ctx-per-slot", type=int, default=16384)
    ap.add_argument("--n-predict", type=int, default=96)
    ap.add_argument("--hog-gb", type=float, default=0.0, help="co-tenant VRAM (GB) to shrink the budget")
    args = ap.parse_args()

    ctx_total = args.slots * args.ctx_per_slot
    ts = int(time.time())
    out_dir = rf"D:\work\denning\results\raw\i4c-{ts}"
    res = {"slots": args.slots, "ctx_per_slot": args.ctx_per_slot, "ctx_total": ctx_total,
           "hog_gb": args.hog_gb}

    rec = srv = hog = None
    try:
        rec = start_recorder(out_dir)
        time.sleep(1.5)
        srv = start_server_np(args.model, PORT, args.slots, ctx_total)
        if not wait_health(PORT, 300):
            res["error"] = "health_timeout"
            _kill(srv); time.sleep(1.0); _kill(rec)
            res["analysis"] = analyze(out_dir)
            print(json.dumps(res)); return 2
        stream_tbt(PORT, 16, "warmup")
        if args.hog_gb > 0:
            hog = start_hog(args.hog_gb, 150)
            t0 = time.time()
            while time.time() - t0 < 60:
                ln = hog.stdout.readline()
                if not ln:
                    if hog.poll() is not None:
                        break
                    continue
                if "HOLDING" in ln:
                    break
            time.sleep(2.0)
        with ThreadPoolExecutor(max_workers=args.slots) as ex:
            futs = [ex.submit(stream_tbt, PORT, args.n_predict, f"s{i}") for i in range(args.slots)]
            sess = [f.result() for f in futs]
        tbts = [r.get("tbt_median_ms") for r in sess if r.get("tbt_median_ms")]
        met = [r for r in sess if r.get("tbt_median_ms") and r["tbt_median_ms"] <= SLO_TBT_MS
               and r.get("ttft_ms", 1e9) <= SLO_TTFT_MS]
        res["sessions"] = len(sess)
        res["goodput"] = len(met)
        res["tbt_median_ms"] = round(sorted(tbts)[len(tbts) // 2], 1) if tbts else None
        res["agg_decode_tps"] = round(sum(r.get("decode_tps", 0) for r in sess), 1)
    finally:
        _kill(hog)
        _kill(srv)
        time.sleep(1.2)
        _kill(rec)

    res["analysis"] = analyze(out_dir)   # REAL footprint: local_peak / nonlocal_peak (GB)
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
