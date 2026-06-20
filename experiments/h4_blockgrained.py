#!/usr/bin/env python3
r"""
H4 block-grained refinement -- typed lifetime classes vs LRU vs TTL, with REAL costs.

Upgrades the abstract H4 sim two ways:
  (1) BLOCK-GRAINED typed provenance -- SYSTEM / DOC / TURN tiers *within* a context,
      evicted per block (not whole-conversation).
  (2) The cost of a cache miss = re-prefilling that block, priced at the REAL prefill
      rate measured live on this rig (ms/token), not an abstract unit.
Compares classes (typed) vs LRU (recency) vs TTL (time-window) on goodput-under-SLO
across the overload spectrum.

Honest scope: still a SIMULATION of the eviction policy -- llama-server's prefix cache
is contiguous, so true arbitrary-block eviction isn't realizable on-rig -- but the
per-block costs are MEASURED, not assumed. (per-block static priority == classes in
this model, so it is omitted as redundant.)

  python experiments/h4_blockgrained.py --reps 20
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import urllib.request

from h1_eviction_pilot import DEFAULT_MODEL
from h1_resident_pilot import wait_health, _kill
from i4b_closed_loop import start_server_np, PORT

FILLER = "The denning project studies KV residency and admission control on Arc GPUs under Windows VidMm. "

# block type -> tokens (realistic agent context) and eviction rank (evict lowest first)
TOKENS = {"SYSTEM": 3000, "DOC": 800, "TURN": 150}
RANK = {"TURN": 0, "DOC": 1, "SYSTEM": 2}


def prefill_ms(prompt):
    body = json.dumps({"prompt": prompt, "n_predict": 1, "cache_prompt": False,
                       "temperature": 0}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/completion", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        o = json.load(r)
    t = o.get("timings", {})
    return t.get("prompt_n", 0), t.get("prompt_ms", 0.0)


def measure_rate():
    """Least-squares ms/token from real cold prefills at 3 sizes."""
    pts = [prefill_ms(FILLER * (tok // 16)) for tok in (1000, 2000, 4000)]
    k = len(pts)
    sx = sum(n for n, _ in pts); sy = sum(ms for _, ms in pts)
    sxx = sum(n * n for n, _ in pts); sxy = sum(n * ms for n, ms in pts)
    slope = (k * sxy - sx * sy) / (k * sxx - sx * sx)
    return slope, pts


def run(seed, N, T, n_docs, cap_tokens, policy, rate, slo_ms, ttl):
    rng = random.Random(seed)
    blocks = {}
    def reg(bid, cls):
        blocks[bid] = {"cls": cls, "tok": TOKENS[cls], "last": -1}
    for s in range(N):
        reg((s, "sys"), "SYSTEM")
        for d in range(n_docs):
            reg((s, "doc", d), "DOC")

    resident, res_tok, clock, goodput, turns = {}, 0, 0, 0, 0

    def victim(needed):
        cand = [b for b in resident if b not in needed]
        if not cand:
            return None
        if policy == "classes":
            return min(cand, key=lambda b: (RANK[blocks[b]["cls"]], blocks[b]["last"]))
        if policy == "ttl":
            expired = [b for b in cand if clock - blocks[b]["last"] > ttl]
            pool = expired if expired else cand
            return min(pool, key=lambda b: blocks[b]["last"])
        return min(cand, key=lambda b: blocks[b]["last"])   # lru

    for t in range(T):
        for s in range(N):
            clock += 1
            tb = (s, "turn", t); reg(tb, "TURN")
            needed = {(s, "sys"), tb}
            for d in rng.sample(range(n_docs), rng.randint(1, n_docs)):
                needed.add((s, "doc", d))
            refetch_ms = 0.0
            for bid in needed:
                blocks[bid]["last"] = clock
                if bid in resident:
                    continue
                refetch_ms += blocks[bid]["tok"] * rate
                while res_tok + blocks[bid]["tok"] > cap_tokens:
                    v = victim(needed)
                    if v is None:
                        break
                    res_tok -= resident.pop(v)
                resident[bid] = blocks[bid]["tok"]; res_tok += blocks[bid]["tok"]
            turns += 1
            if refetch_ms <= slo_ms:
                goodput += 1
    return goodput, turns


def main():
    ap = argparse.ArgumentParser(description="H4 block-grained (classes vs LRU vs TTL, real costs)")
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--N", type=int, default=6)
    ap.add_argument("--T", type=int, default=20)
    ap.add_argument("--docs", type=int, default=3)
    ap.add_argument("--caps", default="12000,16000,20000,26000,32000")
    ap.add_argument("--slo-ms", type=int, default=2000)
    ap.add_argument("--ttl", type=int, default=6)
    args = ap.parse_args()

    srv = start_server_np(DEFAULT_MODEL, PORT, 1, 8192)
    try:
        if not wait_health(PORT, 240):
            print(json.dumps({"error": "health_timeout"})); return 2
        rate, pts = measure_rate()
    finally:
        _kill(srv)

    print(f"measured prefill rate: {rate:.3f} ms/token  (points n,ms: {pts})")
    print(f"block re-prefill cost @ rate: SYSTEM {TOKENS['SYSTEM']*rate:.0f} ms, "
          f"DOC {TOKENS['DOC']*rate:.0f} ms, TURN {TOKENS['TURN']*rate:.0f} ms; SLO {args.slo_ms} ms")
    print(f"full working set = {args.N*(TOKENS['SYSTEM']+args.docs*TOKENS['DOC'])} tokens, "
          f"N={args.N} sessions, reps={args.reps}\n")
    print(f"{'cap_tok':>8} {'classes':>9} {'lru':>7} {'ttl':>7} {'cls>lru':>9} {'cls>ttl':>9}")

    denom = args.N * args.T
    for cap in [int(c) for c in args.caps.split(",")]:
        g = {"classes": [], "lru": [], "ttl": []}
        for r in range(args.reps):
            for pol in g:
                g[pol].append(run(r, args.N, args.T, args.docs, cap, pol, rate, args.slo_ms, args.ttl)[0])
        m = {p: statistics.mean(g[p]) / denom for p in g}
        vl = (m["classes"] - m["lru"]) / m["lru"] * 100 if m["lru"] > 0.01 else float("inf")
        vt = (m["classes"] - m["ttl"]) / m["ttl"] * 100 if m["ttl"] > 0.01 else float("inf")
        vl_s = f"{vl:+.0f}%" if vl != float("inf") else "LRU~0"
        vt_s = f"{vt:+.0f}%" if vt != float("inf") else "TTL~0"
        print(f"{cap:>8} {m['classes']*100:>8.1f}% {m['lru']*100:>6.1f}% {m['ttl']*100:>6.1f}% "
              f"{vl_s:>9} {vt_s:>9}")
    print("\n(goodput = turns whose total re-prefill stall <= SLO, priced at the measured "
          "rate. classes protects SYSTEM>DOC>TURN by type; lru by recency; ttl evicts "
          "blocks idle > ttl turns then oldest. Block-grained policy SIM, real per-block costs.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
