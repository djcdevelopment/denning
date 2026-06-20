#!/usr/bin/env python3
r"""
H4 policy SIMULATION -- typed lifetime classes vs recency (TTL/LRU) eviction.

*** NOT the on-rig confirmatory H4. *** The tagged H4 prediction is about on-rig
goodput, which needs denning's own KV arena (operator-gated, scoped after I-3).
This is EXPLORATORY: does a lifetime-class-aware eviction policy (protect high-reuse
provenance -- system/shared-prefix blocks) beat a recency baseline (LRU/TTL) when
the workload has reuse-provenance structure and the arena is overloaded?

Lifetime classes encode reuse provenance:
  SYSTEM (system prompt / tool defs / shared prefix) -- referenced every turn, big, reused
  DOC    (retrieved context)                          -- referenced intermittently, medium
  TURN   (the current turn's tokens)                  -- referenced once, small, no reuse
classes-ON evicts TURN before DOC before SYSTEM (protect high reuse). LRU/TTL evicts
the least-recently-used block regardless of provenance -- so under cross-session
interleaving it evicts a SYSTEM block about to be reused, forcing a costly refetch.

SLO-relevant metric: a refetch of the big reused SYSTEM block is THE long stall
(R1: refetch >> recompute). So we measure the SYSTEM-block hit rate = the fraction
of session-turns served without that SLO-violating refetch ("goodput-under-SLO").
Many random reps; reports the delta + 95% CI against the pre-registered >=20% bar.

  python experiments/h4_lifetime_sim.py --reps 40
"""

from __future__ import annotations

import argparse
import random
import statistics

SYSTEM, DOC, TURN = "SYSTEM", "DOC", "TURN"
CLASS_RANK = {TURN: 0, DOC: 1, SYSTEM: 2}   # evict lowest rank first (protect SYSTEM)
SIZE = {SYSTEM: 4, DOC: 2, TURN: 1}


def run_workload(seed, N, T, n_docs, cap, policy):
    rng = random.Random(seed)
    blocks = {}
    for s in range(N):
        blocks[(s, "sys")] = {"cls": SYSTEM, "size": SIZE[SYSTEM], "last": -1}
        for d in range(n_docs):
            blocks[(s, "doc", d)] = {"cls": DOC, "size": SIZE[DOC], "last": -1}

    resident = {}
    res_size = 0
    sys_hits = sys_accesses = total_stall = 0
    clock = 0

    def pick_victim(needed):
        cand = [b for b in resident if b not in needed]
        if not cand:
            return None
        if policy == "classes":
            return min(cand, key=lambda b: (CLASS_RANK[blocks[b]["cls"]], blocks[b]["last"]))
        return min(cand, key=lambda b: blocks[b]["last"])   # LRU / TTL recency

    for t in range(T):
        for s in range(N):
            clock += 1
            tb = (s, "turn", t)
            blocks[tb] = {"cls": TURN, "size": SIZE[TURN], "last": -1}
            needed = {(s, "sys"), tb}
            for d in rng.sample(range(n_docs), rng.randint(1, n_docs)):
                needed.add((s, "doc", d))

            # SLO metric: was the big reused SYSTEM block resident (no costly refetch)?
            sys_accesses += 1
            if t > 0 and (s, "sys") in resident:    # t>0: skip the unavoidable cold miss
                sys_hits += 1

            for bid in needed:
                blocks[bid]["last"] = clock
                if bid in resident:
                    continue
                total_stall += blocks[bid]["size"]
                while res_size + blocks[bid]["size"] > cap:
                    v = pick_victim(needed)
                    if v is None:
                        break
                    res_size -= resident.pop(v)
                resident[bid] = blocks[bid]["size"]
                res_size += blocks[bid]["size"]

    return sys_hits, sys_accesses - N, total_stall   # denom excludes the N cold misses


def main() -> int:
    ap = argparse.ArgumentParser(description="H4 lifetime-class eviction simulation")
    ap.add_argument("--reps", type=int, default=40)
    ap.add_argument("--N", type=int, default=8)
    ap.add_argument("--T", type=int, default=25)
    ap.add_argument("--docs", type=int, default=4)
    ap.add_argument("--caps", default="36,48,64,80", help="arena capacities (overload spectrum)")
    args = ap.parse_args()

    wss = args.N * (SIZE[SYSTEM] + args.docs * SIZE[DOC])
    print("H4 SIMULATION (exploratory; NOT the on-rig confirmatory run)")
    print(f"N={args.N} sessions, T={args.T} turns, {args.docs} docs/session, reps={args.reps}")
    print(f"full working set ~= {wss} units; SYSTEM floor = {args.N * SIZE[SYSTEM]} units")
    print(f"metric: SYSTEM-block hit rate (no SLO-violating refetch of the big reused block)\n")
    print(f"{'cap':>4} {'classes-ON':>11} {'LRU/TTL':>9} {'gain (95% CI)':>18} {'relative':>10} {'verdict':>13}")

    for cap in [int(c) for c in args.caps.split(",")]:
        on_rate, lru_rate, ppdiff = [], [], []
        for r in range(args.reps):
            hc, denom, _ = run_workload(r, args.N, args.T, args.docs, cap, "classes")
            hl, _, _ = run_workload(r, args.N, args.T, args.docs, cap, "lru")
            rc, rl = hc / denom, hl / denom
            on_rate.append(rc); lru_rate.append(rl); ppdiff.append(rc - rl)
        mc, ml = statistics.mean(on_rate), statistics.mean(lru_rate)
        mpp = statistics.mean(ppdiff)
        ci = 1.96 * (statistics.stdev(ppdiff) if len(ppdiff) > 1 else 0.0) / (len(ppdiff) ** 0.5)
        rel = f"{(mc - ml) / ml * 100:.0f}% rel" if ml > 0.02 else "LRU~0"
        meets = mpp >= 0.20 and (mpp - ci) > 0
        verdict = "MEETS >=20pp" if meets else ("CI>0" if (mpp - ci) > 0 else "inconclusive")
        print(f"{cap:>4} {mc * 100:>10.1f}% {ml * 100:>8.1f}% {mpp * 100:>+8.1f}pp +/-{ci * 100:>4.1f}  "
              f"{rel:>10} {verdict:>13}")

    print("\n(SYSTEM-hit rate = session-turns whose reused SYSTEM block stayed resident, "
          "i.e. no long refetch stall. classes-ON protects SYSTEM by lifetime class; "
          "LRU/TTL evicts by recency only. Assumes agent workloads have high-reuse "
          "shared prefixes -- realistic for system prompts / tool defs / RAG context.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
