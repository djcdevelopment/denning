#!/usr/bin/env python3
r"""Lifetime-class KV arena with swap -- denning's eviction policy (H4 + S1).

One arena governs one replica's sequence slots. It decides *what* to evict and
*what* to bring back; the EngineAdapter moves the actual KV bytes. That split is
the whole point: the policy is engine-agnostic (works over any adapter), the
mechanism is the engine's save/restore.

Two levers, in priority order (S1 found the second dominates):
  * lifetime class  -- evict the coldest class first (freq, then recency). Beats LRU
    by +32% on-rig / +365% block-grained; TTL collapses to LRU (H4).
  * swap not recompute -- on a miss for an evicted-but-saved conversation, RESTORE
    its KV (refetch) instead of re-prefilling (recompute). S1: ~29x cheaper, so swap
    captures most of the win and classes ~= LRU once swap is cheap.

`access(conv)` returns (slot, action) after having moved any bytes; the caller then
streams into `slot` with cache_prompt=True. Faithful port of the validated loop in
experiments/h4_swap_arena.py::run, restructured as policy-over-adapter.
"""

from __future__ import annotations

from denning.engine.base import EngineAdapter


class LifetimeClassArena:
    def __init__(self, adapter: EngineAdapter, port: int, slots: int,
                 policy: str = "classes", swap: bool = True):
        self.adapter = adapter
        self.port = port
        self.policy = policy          # "classes" | "lru"
        self.swap = swap
        self.conv_slot: dict = {}     # conv -> slot index (resident)
        self.slot_conv: dict = {}     # slot index -> conv (resident)
        self.last: dict = {}          # conv -> last-use clock
        self.freq: dict = {}          # conv -> access count (the lifetime-class key)
        self.saved: set = set()       # convs whose KV is on the host store
        self.free = list(range(slots))
        self.clock = 0
        self.hits = self.restores = self.reprefills = self.saves = 0

    def _fname(self, conv) -> str:
        return f"c{conv}.bin"

    def _victim_slot(self) -> int:
        cands = list(self.slot_conv)
        if self.policy == "classes":   # coldest class first: low freq, then stale
            return min(cands, key=lambda s: (self.freq[self.slot_conv[s]],
                                             self.last[self.slot_conv[s]]))
        return min(cands, key=lambda s: self.last[self.slot_conv[s]])   # lru

    def _evict(self) -> int:
        slot = self._victim_slot()
        victim = self.slot_conv[slot]
        if self.swap:                  # save before evicting so a return is a restore
            self.adapter.save_kv(self.port, slot, self._fname(victim))
            self.saved.add(victim)
            self.saves += 1
        self.adapter.evict_slot(self.port, slot)
        self.conv_slot.pop(victim, None)
        self.slot_conv.pop(slot, None)
        return slot

    def access(self, conv) -> tuple[int, str]:
        """Make `conv` resident; return (slot, action in {hit,restore,prefill}).
        Any KV movement has already happened via the adapter."""
        self.clock += 1
        self.freq[conv] = self.freq.get(conv, 0) + 1
        self.last[conv] = self.clock

        if conv in self.conv_slot:                     # HIT -- already resident
            self.hits += 1
            return self.conv_slot[conv], "hit"

        slot = self.free.pop() if self.free else self._evict()
        self.slot_conv[slot] = conv
        self.conv_slot[conv] = slot

        if self.swap and conv in self.saved:           # RESTORE (refetch)
            self.adapter.restore_kv(self.port, slot, self._fname(conv))
            self.saved.discard(conv)
            self.restores += 1
            return slot, "restore"

        self.reprefills += 1                            # cold / unsaved -> (re)prefill
        return slot, "prefill"

    def stats(self) -> dict:
        total = self.hits + self.restores + self.reprefills
        return {"policy": self.policy, "swap": self.swap, "turns": total,
                "hits": self.hits, "restores": self.restores,
                "reprefills": self.reprefills, "saves": self.saves}
