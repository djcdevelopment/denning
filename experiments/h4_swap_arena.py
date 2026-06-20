#!/usr/bin/env python3
r"""
S1 swap arena -- restore-on-miss (REFETCH) instead of re-prefill (RECOMPUTE).

The on-rig H4 arena paid a cache miss as a re-prefill (recompute, ~2.4 s for a 3.5k
prefix). The swap probe showed the same KV restores from disk in ~84 ms (refetch) --
R1 on real bytes. This arena swaps: on eviction it SAVEs the victim's KV
(`/slots?action=save`); on a miss it RESTOREs the bytes (`action=restore`) instead of
recomputing, then the turn is a cheap hit. Compares goodput-under-SLO with swap ON vs
OFF (same workload/policy), and classes vs LRU under swap.

  python experiments/h4_swap_arena.py --policy classes --swap on  --seed 0
  python experiments/h4_swap_arena.py --policy classes --swap off --seed 0
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request

from h1_eviction_pilot import DEFAULT_MODEL, card_b_env
from h1_resident_pilot import wait_health, _kill

PORT = 8234
LLAMA_SERVER = r"D:\work\llamacpp-b9279-vulkan\llama-server.exe"
SLOT_DIR = r"D:\tmp\slots"
FILLER = "The denning project studies KV residency and admission control on Arc GPUs. "


def ctx_for(cid):
    return f"Conversation {cid} system context. " + FILLER * 250   # ~3.5k tokens


def start_server(slots, ctx):
    os.makedirs(SLOT_DIR, exist_ok=True)
    return subprocess.Popen(
        [LLAMA_SERVER, "-m", DEFAULT_MODEL, "-ngl", "99", "--host", "127.0.0.1",
         "--port", str(PORT), "-np", str(slots), "-c", str(ctx), "--slot-save-path", SLOT_DIR],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=card_b_env())


def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as r:
        o = json.load(r)
    return o, (time.perf_counter() - t0) * 1000


def turn_ms(prompt, slot):
    o, _ = post("/completion", {"prompt": prompt, "n_predict": 1, "cache_prompt": True,
                                "id_slot": slot, "temperature": 0})
    return o.get("timings", {}).get("prompt_ms", 0.0)


def build_trace(seed, n_hot, length, cold_frac=0.3):
    rng = random.Random(seed); trace, cold = [], 1000
    for _ in range(length):
        if rng.random() >= cold_frac:
            trace.append(rng.randint(0, n_hot - 1))
        else:
            trace.append(cold); cold += 1
    return trace


def run(trace, M, policy, swap, slo_ms):
    slot_conv, conv_slot, last, freq, saved = {}, {}, {}, {}, set()
    clock = goodput = hits = restores = reprefills = 0
    total = 0.0
    for cid in trace:
        clock += 1
        freq[cid] = freq.get(cid, 0) + 1
        last[cid] = clock
        ttft = 0.0
        if cid in conv_slot:                                   # HIT
            hits += 1
            ttft = turn_ms(ctx_for(cid) + f" Turn {clock}?", conv_slot[cid])
        else:                                                  # MISS
            if len(slot_conv) < M:
                slot = len(slot_conv)
            else:
                cands = list(slot_conv)
                if policy == "classes":
                    slot = min(cands, key=lambda s: (freq[slot_conv[s]], last[slot_conv[s]]))
                else:
                    slot = min(cands, key=lambda s: last[slot_conv[s]])
                victim = slot_conv[slot]
                if swap:                                       # save victim before evicting
                    post(f"/slots/{slot}?action=save", {"filename": f"c{victim}.bin"})
                    saved.add(victim)
                conv_slot.pop(victim, None)
            slot_conv[slot] = cid; conv_slot[cid] = slot
            if swap and cid in saved:                          # RESTORE (refetch) + cheap turn
                _, rwall = post(f"/slots/{slot}?action=restore", {"filename": f"c{cid}.bin"})
                ttft = rwall + turn_ms(ctx_for(cid) + f" Turn {clock}?", slot)
                restores += 1
            else:                                              # cold / no-swap -> (re)prefill
                ttft = turn_ms(ctx_for(cid) + f" Turn {clock}?", slot)
                reprefills += 1
        total += ttft
        if ttft <= slo_ms:
            goodput += 1
    return {"policy": policy, "swap": swap, "goodput": goodput, "turns": len(trace),
            "hits": hits, "restores": restores, "reprefills": reprefills,
            "total_ttft_s": round(total / 1000, 1)}


def main():
    ap = argparse.ArgumentParser(description="S1 swap arena (restore-on-miss vs re-prefill)")
    ap.add_argument("--policy", choices=["classes", "lru"], default="classes")
    ap.add_argument("--swap", choices=["on", "off"], default="on")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--slots", type=int, default=4)
    ap.add_argument("--hot", type=int, default=6)
    ap.add_argument("--length", type=int, default=40)
    ap.add_argument("--slo-ms", type=int, default=2000)
    args = ap.parse_args()

    trace = build_trace(args.seed, args.hot, args.length)
    srv = start_server(args.slots, args.slots * 4096)
    try:
        if not wait_health(PORT, 240):
            print(json.dumps({"error": "health_timeout"})); return 2
        res = run(trace, args.slots, args.policy, args.swap == "on", args.slo_ms)
    finally:
        _kill(srv)
    res.update(seed=args.seed, slots=args.slots, hot=args.hot)
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
