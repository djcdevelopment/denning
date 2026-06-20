#!/usr/bin/env python3
r"""Replica-router -- places sessions across replica-per-card backends.

The headline two-card thesis in code: on a fabric-less box there is no GPU P2P
(R3: card->card is host-bounced at 0.47x, so pooling doesn't pay), therefore the
right multi-card design is a full engine *replica per card*, and you scale by
*routing* sessions across replicas -- not by tensor-parallel pooling. Two cards =>
2x the admission capacity (N* doubles 8 -> 16; two-card-goodput result).

`round_robin` reproduces experiments/h4_twocard.py's assignment exactly; for live
serving `least_loaded` balances on in-flight count. The router holds only ports +
load; it never names the engine (it routes to whatever EngineAdapter spawned).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReplicaRouter:
    ports: list[int]
    inflight: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # preserve any pre-seeded load; default every known port to 0
        self.inflight = {p: self.inflight.get(p, 0) for p in self.ports}

    def round_robin(self, n: int) -> list[int]:
        """Static round-robin of n sessions across the replicas (== h4_twocard)."""
        return [self.ports[i % len(self.ports)] for i in range(n)]

    def least_loaded(self) -> int:
        """Pick the replica with the fewest in-flight sessions; record the placement.
        Ties break toward the earliest port (Card A/display first is fine -- it is a
        full participant; two-card-scaling showed no contention penalty)."""
        port = min(self.ports, key=lambda p: (self.inflight[p], p))
        self.inflight[port] += 1
        return port

    def reserve(self, port: int) -> None:
        """Mark a session in-flight on `port` (admission accounting)."""
        self.inflight[port] = self.inflight.get(port, 0) + 1

    def release(self, port: int) -> None:
        if self.inflight.get(port, 0) > 0:
            self.inflight[port] -= 1

    def load(self) -> dict:
        return dict(self.inflight)


def system_capacity(controller, live_budgets: list[float]) -> int:
    """Total admissible sessions across all cards = sum of per-card N*(live budget).
    With two ~31 GB cards and a compute knee of 8, this is 8 + 8 = 16 -- the
    two-card goodput thesis as one line of arithmetic."""
    return sum(controller.capacity(b) for b in live_budgets)
