#!/usr/bin/env python3
r"""Shim unit tests -- arena policy/swap logic against a fake engine (no GPU).

A FakeAdapter implements EngineAdapter with no-op KV moves that just count calls,
so the lifetime-class arena's decisions can be verified deterministically off-rig.

  python tests/test_shim.py          (or: PYTHONPATH=D:\work\denning python tests/test_shim.py)
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from denning.control.arena import LifetimeClassArena
from denning.engine.base import EngineAdapter, ReplicaHandle, SessionStats


class FakeAdapter:
    """A valid EngineAdapter whose KV moves are counted no-ops (off-rig testing)."""

    def __init__(self):
        self.saves = self.restores = self.evicts = 0

    def spawn_replica(self, device, port, slots, ctx) -> ReplicaHandle:
        return ReplicaHandle(device=device, port=port, slots=slots, ctx=ctx, proc=None)

    def health(self, port, timeout_s=300.0) -> bool:
        return True

    def stop(self, handle) -> None:
        pass

    def stream(self, port, prompt, n_predict, *, slot=-1, cache_prompt=False,
               temperature=0.7, label="s") -> SessionStats:
        return SessionStats(label=label, tokens=n_predict, ttft_ms=10.0,
                            tbt_median_ms=9.0, decode_tps=110.0)

    def save_kv(self, port, slot, filename) -> float:
        self.saves += 1; return 30.0

    def restore_kv(self, port, slot, filename) -> float:
        self.restores += 1; return 2.0

    def evict_slot(self, port, slot) -> None:
        self.evicts += 1


def build_trace(seed, n_hot, length, cold_frac=0.3):
    rng = random.Random(seed); trace, cold = [], 1000
    for _ in range(length):
        if rng.random() >= cold_frac:
            trace.append(rng.randint(0, n_hot - 1))
        else:
            trace.append(cold); cold += 1
    return trace


def _run(policy, swap, slots=4, hot=6, length=40, seed=0):
    fake = FakeAdapter()
    arena = LifetimeClassArena(fake, port=8240, slots=slots, policy=policy, swap=swap)
    actions = []
    for conv in build_trace(seed, hot, length):
        slot, action = arena.access(conv)
        assert 0 <= slot < slots, f"slot {slot} out of range"
        actions.append(action)
    return arena, fake, actions


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    return 0 if cond else 1


def main() -> int:
    fails = 0
    print("[arena] FakeAdapter satisfies EngineAdapter:")
    fails += check("isinstance(FakeAdapter(), EngineAdapter)", isinstance(FakeAdapter(), EngineAdapter))

    print("\n[arena] swap ON, classes policy:")
    arena, fake, _ = _run("classes", swap=True)
    s = arena.stats()
    print("   ", s)
    fails += check("accounting: hits+restores+reprefills == turns",
                   s["hits"] + s["restores"] + s["reprefills"] == s["turns"])
    fails += check("swap did real work: restores > 0 and saves > 0",
                   s["restores"] > 0 and s["saves"] > 0)
    fails += check("adapter call counts match arena stats",
                   fake.saves == s["saves"] and fake.restores == s["restores"])
    fails += check("a restored conv leaves the saved-set (no double restore)",
                   arena.restores <= arena.saves)

    print("\n[arena] swap OFF, classes policy:")
    arena0, fake0, _ = _run("classes", swap=False)
    s0 = arena0.stats()
    print("   ", s0)
    fails += check("no swap => no restores, no saves",
                   s0["restores"] == 0 and s0["saves"] == 0 and fake0.restores == 0)
    fails += check("every miss is a (re)prefill",
                   s0["reprefills"] == s0["turns"] - s0["hits"])

    print("\n[arena] swap converts misses to restores (the S1 lever):")
    on = arena.stats(); off = arena0.stats()
    print(f"    reprefills: swap-off={off['reprefills']}  swap-on={on['reprefills']}  "
          f"(swap-on restores={on['restores']})")
    fails += check("swap ON has strictly fewer re-prefills than swap OFF",
                   on["reprefills"] < off["reprefills"])

    fails += _test_daemon()

    print("\n[test_shim]", "PASS" if fails == 0 else f"FAIL ({fails})")
    return 1 if fails else 0


def _test_daemon() -> int:
    from collections import Counter

    from denning.control.admission import AdmissionController
    from denning.denningd import Daemon

    fails = 0
    print("\n[daemon] wiring over a fake engine (2 cards, sequential):")
    d = Daemon(FakeAdapter(), devices=[0, 1], slots=4, live_budget=False)
    d.start()
    res = [d.handle(c % 6, f"turn {i}", 16) for i, c in enumerate(range(16))]
    d.stop()
    admitted = [r for r in res if r["admitted"]]
    by_card = Counter(r["device"] for r in res)
    print(f"    admitted {len(admitted)}/16   routing {dict(by_card)}")
    fails += check("all 16 sessions admitted (budget ample)", len(admitted) == 16)
    fails += check("round-robin balanced 8/8 across cards", by_card[0] == 8 and by_card[1] == 8)
    served = sum(s["hits"] + s["restores"] + s["reprefills"]
                 for s in d.stats()["replicas"].values())
    fails += check("per-replica arena accounting sums to 16 turns", served == 16)
    fails += check("actions are valid", all(r["action"] in ("hit", "restore", "prefill")
                                            for r in admitted))
    conv_cards = {}
    for r in res:
        conv_cards.setdefault(r["conv"], set()).add(r["device"])
    fails += check("session affinity: each conv stays on one card",
                   all(len(cards) == 1 for cards in conv_cards.values()))
    total_hits = sum(s["hits"] for s in d.stats()["replicas"].values())
    fails += check("returning convs hit resident KV (affinity pays off)", total_hits > 0)

    print("\n[daemon] admission sheds when the live budget is squeezed:")
    d2 = Daemon(FakeAdapter(), devices=[0, 1], slots=8, live_budget=False,
                controller=AdmissionController(compute_knee=2))   # N* = 2 / card
    d2.start()
    for p in d2.ports:                       # simulate 2 sessions already in-flight per card
        d2.router.reserve(p); d2.router.reserve(p)
    rej = d2.handle(99, "one too many", 16)
    d2.stop()
    print(f"    capacity/card={d2.controller.capacity(d2.nominal_budget_gb)}  "
          f"-> admitted={rej['admitted']} ({rej.get('reason','')})")
    fails += check("session beyond N* is rejected", rej["admitted"] is False)
    fails += check("rejection counted", d2.rejected == 1)

    print("\n[daemon] concurrent handle_many (32 sessions, 16 workers, 2 cards):")
    d3 = Daemon(FakeAdapter(), devices=[0, 1], slots=8, live_budget=False)
    d3.start()
    sessions = [(i % 10, f"t{i}", 8) for i in range(32)]   # 10 convs, 32 turns
    res3 = d3.handle_many(sessions, max_workers=16)
    d3.stop()
    admitted3 = [r for r in res3 if r["admitted"]]
    served3 = sum(s["hits"] + s["restores"] + s["reprefills"]
                  for s in d3.stats()["replicas"].values())
    print(f"    {len(res3)} returned, {len(admitted3)} admitted, {d3.rejected} rejected, "
          f"{served3} arena turns")
    fails += check("no lost sessions: admitted + rejected == 32",
                   len(res3) == 32 and len(admitted3) + d3.rejected == 32)
    fails += check("arena turns == admitted (no double/lost access under threads)",
                   served3 == len(admitted3))
    cc = {}
    for r in res3:
        cc.setdefault(r["conv"], set()).add(r["device"])
    fails += check("affinity holds under concurrency", all(len(c) == 1 for c in cc.values()))
    return fails


if __name__ == "__main__":
    sys.exit(main())
