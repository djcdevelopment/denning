#!/usr/bin/env python3
r"""denningd -- the co-residency control loop over an unmodified engine (S-shim-2).

Wires the four control-plane pieces onto an EngineAdapter:

    client session
        |  route (round-robin across replica-per-card)            [router]
        v
    admission on the LIVE VidMm budget: admit iff in-flight <= N* [budget + admission]
        |  (reject/queue if the OS shrank the budget under a co-tenant)
        v
    lifetime-class KV arena per replica: hit / restore / prefill  [arena]
        |  (the adapter moves the KV bytes; the arena picks what)
        v
    adapter.stream(port, slot) -> SessionStats                    [engine]

The engine underneath is unmodified (one llama-server replica per card today). This
file names no engine -- only EngineAdapter -- so vLLM-XPU / ExLlamaV3 drop in by
swapping the adapter. Programmatic API now (`Daemon.handle`); an OpenAI-compatible
HTTP front is a thin wrapper on top (S-shim-2, next).

  python -m denning.denningd --dry-run                  # no GPU: wiring over a fake engine
  python -m denning.denningd --serve --cards 2 --n 16   # on-rig: real replicas, N sessions
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from denning.control import budget as budgetmod
from denning.control.admission import CARD_BUDGET_GB, AdmissionController
from denning.control.arena import LifetimeClassArena
from denning.control.router import ReplicaRouter
from denning.engine.base import EngineAdapter


@dataclass
class Replica:
    device: int
    port: int
    handle: object
    arena: LifetimeClassArena


class Daemon:
    def __init__(self, adapter: EngineAdapter, devices, base_port: int = 8240,
                 slots: int = 8, ctx: int = 2048, policy: str = "classes",
                 swap: bool = True, controller: AdmissionController = None,
                 live_budget: bool = True, nominal_budget_gb: float = CARD_BUDGET_GB):
        self.adapter = adapter
        self.devices = list(devices)
        self.base_port = base_port
        self.slots = slots
        self.ctx = ctx
        self.policy = policy
        self.swap = swap
        self.controller = controller or AdmissionController()
        self.live_budget = live_budget
        self.nominal_budget_gb = nominal_budget_gb
        self.ports = [base_port + d for d in self.devices]
        self._port_device = {base_port + d: d for d in self.devices}
        self.router = ReplicaRouter(self.ports)
        self.replicas: dict = {}
        self.conv_card: dict = {}        # conv -> device (session affinity)
        self.rejected = 0
        self._rr = 0

    # --- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        for d in self.devices:
            port = self.base_port + d
            h = self.adapter.spawn_replica(d, port, self.slots, self.slots * self.ctx)
            if not self.adapter.health(port, 300):
                raise RuntimeError(f"replica on device {d} (port {port}) unhealthy")
            self.adapter.stream(port, "warmup", 8, slot=0, label="warmup")
            self.replicas[d] = Replica(
                device=d, port=port, handle=h,
                arena=LifetimeClassArena(self.adapter, port, self.slots, self.policy, self.swap))

    def stop(self) -> None:
        for rep in self.replicas.values():
            self.adapter.stop(rep.handle)

    # --- control loop ------------------------------------------------------
    def _route(self, conv) -> int:
        """Session affinity: a conversation returns to the card holding its KV
        (resident or saved), so multi-turn convs hit/restore instead of re-prefilling.
        New conversations are round-robined across the replicas."""
        if conv in self.conv_card:
            port = self.base_port + self.conv_card[conv]
        else:
            port = self.ports[self._rr % len(self.ports)]
            self._rr += 1
            self.conv_card[conv] = self._port_device[port]
        self.router.reserve(port)
        return port

    def _budget(self, device: int) -> float:
        if self.live_budget:
            b = budgetmod.read_live_budget_gb(device)
            if b is not None:
                return b
        return self.nominal_budget_gb

    def handle(self, conv, prompt: str, n_predict: int = 64) -> dict:
        port = self._route(conv)
        device = self._port_device[port]
        budget = self._budget(device)
        cap = self.controller.capacity(budget)
        if self.router.inflight[port] > cap:        # over N* for the live budget -> shed
            self.router.release(port)
            self.rejected += 1
            return {"conv": conv, "admitted": False, "device": device, "port": port,
                    "budget_gb": round(budget, 2), "capacity": cap,
                    "reason": "over N* for live budget"}
        try:
            rep = self.replicas[device]
            slot, action = rep.arena.access(conv)
            stats = self.adapter.stream(port, prompt, n_predict, slot=slot,
                                        cache_prompt=True, label=f"conv{conv}")
            return {"conv": conv, "admitted": True, "device": device, "port": port,
                    "slot": slot, "action": action, "budget_gb": round(budget, 2),
                    "capacity": cap, "ttft_ms": stats.ttft_ms,
                    "tbt_median_ms": stats.tbt_median_ms, "decode_tps": stats.decode_tps}
        finally:
            self.router.release(port)

    def handle_many(self, sessions, max_workers: int = None) -> list:
        """Serve (conv, prompt, n_predict) tuples concurrently across the replicas."""
        mw = max_workers or max(1, len(sessions))
        with ThreadPoolExecutor(max_workers=mw) as ex:
            futs = [ex.submit(self.handle, c, p, n) for (c, p, n) in sessions]
            return [f.result() for f in futs]

    def stats(self) -> dict:
        return {"devices": self.devices, "rejected": self.rejected,
                "router_load": self.router.load(),
                "replicas": {d: rep.arena.stats() for d, rep in self.replicas.items()}}


# --- CLI -------------------------------------------------------------------
def _dry_run() -> int:
    """Wire the daemon over a fake engine (no GPU) and serve a tiny round-robin batch."""
    from tests.test_shim import FakeAdapter
    d = Daemon(FakeAdapter(), devices=[0, 1], slots=4, live_budget=False,
               nominal_budget_gb=CARD_BUDGET_GB)
    d.start()
    out = [d.handle(c, f"turn for conv {c}", 16) for c in [1, 2, 1, 3, 2, 4]]
    d.stop()
    for r in out:
        print(f"  conv {r['conv']}: card {r['device']} slot {r.get('slot')} "
              f"{r.get('action'):>7}  admitted={r['admitted']}")
    print("\n  stats:", json.dumps(d.stats()))
    print("\n[dry-run] daemon wiring OK")
    return 0


def _serve(cards: int, n: int) -> int:
    from denning.engine.llamacpp import LlamaCppAdapter
    devices = [1] if cards == 1 else [0, 1]
    prompt = ("Explain virtual memory, demand paging, the TLB, and page replacement "
              "in a few precise paragraphs.")
    d = Daemon(LlamaCppAdapter(), devices=devices, slots=8, ctx=2048,
               policy="classes", swap=True, live_budget=True)
    d.start()
    try:
        sessions = [(i % (n // 2 + 1), prompt, 64) for i in range(n)]   # some shared convs
        res = d.handle_many(sessions)
    finally:
        d.stop()
    admitted = [r for r in res if r["admitted"]]
    met = [r for r in admitted if (r.get("tbt_median_ms") or 1e9) <= 50.0]
    print(json.dumps({"cards": cards, "n": n, "admitted": len(admitted),
                      "slo_met": len(met), "rejected": d.rejected,
                      "stats": d.stats()}, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="denningd -- co-residency control loop (S-shim-2)")
    ap.add_argument("--dry-run", action="store_true", help="no-GPU wiring over a fake engine")
    ap.add_argument("--serve", action="store_true", help="on-rig: real replicas")
    ap.add_argument("--cards", type=int, choices=[1, 2], default=2)
    ap.add_argument("--n", type=int, default=16)
    args = ap.parse_args()
    if args.serve:
        return _serve(args.cards, args.n)
    return _dry_run()


if __name__ == "__main__":
    sys.exit(main())
