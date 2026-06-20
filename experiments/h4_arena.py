#!/usr/bin/env python3
r"""
H4 ARENA (ON-RIG) -- lifetime-class vs LRU eviction over a real llama-server slot cache.

The denning arena = a router managing M llama-server slots as the resident set. A
cache HIT (a conversation's KV resident in its slot) -> a cheap turn (~40 ms); a MISS
(evicted) -> the conversation's long prefix re-prefills -> the real R1 refetch stall
(measured ~2.8 s for a ~3.5k-token prefix). The eviction policy decides which slot to
reclaim on a miss:
  classes : evict the lowest-reuse (coldest) conversation -- lifetime-class / provenance
  lru     : evict the least-recently-used slot -- recency

Workload: a few HOT long-running sessions + a stream of COLD one-off sessions (scan
pressure) -- the classic case where recency thrashes the hot set. Metric: per-turn
TTFT = server-reported prefill_ms; goodput-under-SLO = turns with TTFT <= SLO. One
policy per invocation (fresh server); run both with the same --seed to compare.

  python experiments/h4_arena.py --policy classes --seed 0
  python experiments/h4_arena.py --policy lru     --seed 0
"""

import argparse
import json
import random
import sys
import urllib.request

from h1_eviction_pilot import DEFAULT_MODEL
from h1_resident_pilot import wait_health, _kill
from i4b_closed_loop import start_server_np, PORT

FILLER = "The denning project studies KV residency and admission control on Arc GPUs. "


def ctx_for(conv_id, approx_tokens=3500):
    return f"Conversation {conv_id} system context. " + FILLER * (approx_tokens // 14)


def post(prompt, id_slot):
    body = json.dumps({"prompt": prompt, "n_predict": 1, "cache_prompt": True,
                       "id_slot": id_slot, "temperature": 0}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/completion", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        o = json.load(r)
    return o.get("timings", {}).get("prompt_ms", 0.0)


def build_trace(seed, n_hot, length, cold_frac=0.3):
    rng = random.Random(seed)
    trace, cold_id = [], 1000
    for _ in range(length):
        if rng.random() >= cold_frac:
            trace.append(rng.randint(0, n_hot - 1))   # a hot session
        else:
            trace.append(cold_id); cold_id += 1       # a fresh cold one-off (scan)
    return trace


def run(trace, M, policy, slo_ms):
    slot_conv, conv_slot, last, freq = {}, {}, {}, {}
    clock = goodput = misses = 0
    total_ms = 0.0
    for cid in trace:
        clock += 1
        freq[cid] = freq.get(cid, 0) + 1
        last[cid] = clock
        if cid in conv_slot:                          # HIT
            slot = conv_slot[cid]
        else:                                         # MISS -> choose a victim slot
            if len(slot_conv) < M:
                slot = len(slot_conv)
            else:
                cands = list(slot_conv)
                if policy == "classes":               # evict coldest (lowest reuse), tie LRU
                    slot = min(cands, key=lambda s: (freq[slot_conv[s]], last[slot_conv[s]]))
                else:                                  # LRU: evict least-recently-used
                    slot = min(cands, key=lambda s: last[slot_conv[s]])
                conv_slot.pop(slot_conv[slot], None)
            slot_conv[slot] = cid
            conv_slot[cid] = slot
            misses += 1
        ms = post(ctx_for(cid) + f" Turn {clock}?", slot)
        total_ms += ms
        if ms <= slo_ms:
            goodput += 1
    return {"policy": policy, "turns": len(trace), "goodput": goodput, "misses": misses,
            "total_prefill_s": round(total_ms / 1000, 1)}


def main():
    ap = argparse.ArgumentParser(description="H4 on-rig arena (lifetime-class vs LRU)")
    ap.add_argument("--policy", choices=["classes", "lru"], required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--slots", type=int, default=6)
    ap.add_argument("--hot", type=int, default=4)
    ap.add_argument("--length", type=int, default=50)
    ap.add_argument("--slo-ms", type=int, default=2000)
    args = ap.parse_args()

    trace = build_trace(args.seed, args.hot, args.length)
    srv = start_server_np(DEFAULT_MODEL, PORT, args.slots, args.slots * 4096)
    try:
        if not wait_health(PORT, 240):
            print(json.dumps({"error": "health_timeout"})); return 2
        res = run(trace, args.slots, args.policy, args.slo_ms)
    finally:
        _kill(srv)
    res.update(seed=args.seed, slots=args.slots, hot=args.hot, slo_ms=args.slo_ms)
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
