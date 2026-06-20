#!/usr/bin/env python3
r"""
N-session goodput across 1 vs 2 cards (replica per card) -- the SLO-flavored 2x.

A llama-server replica per card (Card A = device 0 / display, Card B = device 1 /
compute); N concurrent streaming sessions round-robined across the cards; goodput =
sessions meeting the SLO (TBT_median <= 50ms AND TTFT <= 2s). Single card should knee
at N*~8 (per the I-4b result); two cards should knee at ~2x that, serving twice the
SLO-meeting sessions -- the headline thesis in its goodput form.

  python experiments/h4_twocard.py --cards 1 --n 8
  python experiments/h4_twocard.py --cards 2 --n 16
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from h1_eviction_pilot import DEFAULT_MODEL
from h1_resident_pilot import wait_health, stream_tbt, _kill

LLAMA_SERVER = r"D:\work\llamacpp-b9279-vulkan\llama-server.exe"
PORTS = {0: 8240, 1: 8241}   # device -> port (0 = Card A/display, 1 = Card B/compute)
SLO_TBT_MS = 50.0
SLO_TTFT_MS = 2000.0


def start_server(device, port, slots, ctx_total):
    e = dict(os.environ)
    e["GGML_VK_VISIBLE_DEVICES"] = str(device)
    return subprocess.Popen(
        [LLAMA_SERVER, "-m", DEFAULT_MODEL, "-ngl", "99", "--host", "127.0.0.1",
         "--port", str(port), "-np", str(slots), "-c", str(slots * ctx_total)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=e)


def main():
    ap = argparse.ArgumentParser(description="1- vs 2-card N-session goodput")
    ap.add_argument("--cards", type=int, choices=[1, 2], default=2)
    ap.add_argument("--n", type=int, default=16, help="total concurrent sessions")
    ap.add_argument("--slots", type=int, default=12, help="slots per card")
    ap.add_argument("--ctx", type=int, default=2048)
    ap.add_argument("--n-predict", type=int, default=128)
    args = ap.parse_args()

    devices = [1] if args.cards == 1 else [0, 1]   # 1-card uses Card B (compute)
    servers, ports = [], []
    res = {"cards": args.cards, "n": args.n}
    try:
        for d in devices:
            p = PORTS[d]; ports.append(p)
            servers.append(start_server(d, p, args.slots, args.ctx))
        for p in ports:
            if not wait_health(p, 300):
                res["error"] = f"health timeout {p}"; print(json.dumps(res)); return 2
        for p in ports:
            stream_tbt(p, 16, "warmup")

        assign = [ports[i % len(ports)] for i in range(args.n)]   # round-robin across cards
        with ThreadPoolExecutor(max_workers=args.n) as ex:
            futs = [ex.submit(stream_tbt, assign[i], args.n_predict, f"s{i}") for i in range(args.n)]
            sess = [f.result() for f in futs]

        tbts = [r.get("tbt_median_ms") for r in sess if r.get("tbt_median_ms")]
        met = [r for r in sess if r.get("tbt_median_ms") and r["tbt_median_ms"] <= SLO_TBT_MS
               and r.get("ttft_ms", 1e9) <= SLO_TTFT_MS]
        res.update(goodput=len(met), sessions=len(sess),
                   tbt_median_ms=round(sorted(tbts)[len(tbts) // 2], 1) if tbts else None,
                   agg_decode_tps=round(sum(r.get("decode_tps", 0) for r in sess), 1))
    finally:
        for s in servers:
            _kill(s)
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
