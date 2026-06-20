#!/usr/bin/env python3
r"""
I-4b closed-loop admission demo -- the payoff figure (one config per invocation).

Claim: admitting N* (budget-fit) concurrent sessions yields higher goodput-under-
SLO than admitting N > N* -- the admission controller (gating on the live VidMm
budget) keeps denning on the SLO side of the H1 cliff while the uncontrolled
config collapses.

This runs ONE config: start llama-server -np SLOTS -c (SLOTS*ctx) on Card B
(optionally under a co-tenant hog), drive SLOTS concurrent streaming sessions,
report goodput (# sessions meeting SLO: TBT_median <= 50ms AND TTFT <= 2s),
the live VidMm budget, and the server VRAM footprint. Call it across SLOTS to get
the goodput curve; the controller's N* should predict the peak/cliff.

  python experiments/i4b_closed_loop.py --slots 4 --ctx-per-slot 2048 --n-predict 128
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from h1_eviction_pilot import start_hog, card_b_env, DEFAULT_MODEL
from h1_resident_pilot import wait_health, stream_tbt, _kill
from admission_controller import read_live_budget_gb, CARD_BUDGET_GB

LLAMA_SERVER = r"D:\work\llamacpp-b9279-vulkan\llama-server.exe"
PORT = 8232
SLO_TBT_MS = 50.0
SLO_TTFT_MS = 2000.0


def start_server_np(model: str, port: int, np_slots: int, ctx_total: int) -> subprocess.Popen:
    return subprocess.Popen(
        [LLAMA_SERVER, "-m", model, "-ngl", "99", "--host", "127.0.0.1", "--port", str(port),
         "-np", str(np_slots), "-c", str(ctx_total)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=card_b_env())


def main() -> int:
    ap = argparse.ArgumentParser(description="I-4b closed-loop admission demo")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--slots", type=int, default=4)
    ap.add_argument("--ctx-per-slot", type=int, default=2048)
    ap.add_argument("--n-predict", type=int, default=128)
    ap.add_argument("--hog-gb", type=float, default=0.0)
    args = ap.parse_args()

    ctx_total = args.slots * args.ctx_per_slot
    res = {"slots": args.slots, "ctx_per_slot": args.ctx_per_slot, "ctx_total": ctx_total,
           "hog_gb": args.hog_gb}
    srv = hog = None
    try:
        srv = start_server_np(args.model, PORT, args.slots, ctx_total)
        if not wait_health(PORT, 240):
            res["error"] = "health_timeout"
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

        budget = read_live_budget_gb(0)
        res["live_budget_gb"] = budget
        res["server_footprint_gb"] = round(CARD_BUDGET_GB - budget, 2) if budget else None

        with ThreadPoolExecutor(max_workers=args.slots) as ex:
            futs = [ex.submit(stream_tbt, PORT, args.n_predict, f"s{i}") for i in range(args.slots)]
            sess = [f.result() for f in futs]

        tbts = [r.get("tbt_median_ms") for r in sess if r.get("tbt_median_ms")]
        met = [r for r in sess if r.get("tbt_median_ms") and r["tbt_median_ms"] <= SLO_TBT_MS
               and r.get("ttft_ms", 1e9) <= SLO_TTFT_MS]
        res["sessions"] = len(sess)
        res["goodput"] = len(met)
        res["tbt_median_ms"] = round(sorted(tbts)[len(tbts) // 2], 1) if tbts else None
        res["tbt_max_ms"] = round(max(tbts), 1) if tbts else None
        res["agg_decode_tps"] = round(sum(r.get("decode_tps", 0) for r in sess), 1)
    finally:
        _kill(hog); _kill(srv)

    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
