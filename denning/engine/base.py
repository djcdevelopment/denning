#!/usr/bin/env python3
"""The EngineAdapter contract -- denning's entire engine-specific surface.

This is the boundary from docs/denning-as-shim.md §4. The control plane above it
(budget-reader, admission controller, replica-router, lifetime-class KV arena +
swap manager) is engine-agnostic and calls ONLY these methods. To support a new
engine (vLLM-XPU on Linux, ExLlamaV3 on NVIDIA/Windows), implement this protocol;
nothing else changes.

The seam that makes denning a co-residency control plane and not a load balancer
is `save_kv` / `restore_kv` / `evict_slot` -- the KV-residency primitives. S1
measured restore (refetch) at ~29x cheaper than re-prefill (recompute) on real
bytes, which is why the arena swaps instead of recomputing on a miss.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass
class ReplicaHandle:
    """One engine replica bound to one card (replica-per-card; no cross-card pool,
    because R3 showed P2P is host-bounced at 0.47x -- pooling doesn't pay here)."""
    device: int           # GPU index (e.g. GGML_VK_VISIBLE_DEVICES)
    port: int             # loopback port the replica serves on
    slots: int            # concurrent sequence slots (-np)
    ctx: int              # total context across all slots (-c)
    proc: object = None   # the OS process handle (opaque to callers)


@dataclass
class SessionStats:
    """Per-session decode telemetry -- the input to admission/goodput accounting."""
    label: str
    tokens: int
    ttft_ms: Optional[float] = None
    tbt_median_ms: Optional[float] = None
    tbt_p95_ms: Optional[float] = None
    decode_tps: Optional[float] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.tokens >= 2

    def meets_slo(self, tbt_ms: float, ttft_ms: float) -> bool:
        """The two-card goodput SLO (TBT_median <= tbt_ms AND TTFT <= ttft_ms)."""
        return (self.ok and self.tbt_median_ms is not None
                and self.tbt_median_ms <= tbt_ms
                and (self.ttft_ms if self.ttft_ms is not None else 1e9) <= ttft_ms)


@runtime_checkable
class EngineAdapter(Protocol):
    """The thin per-engine driver. Implementations: denning.engine.llamacpp."""

    # --- lifecycle ---------------------------------------------------------
    def spawn_replica(self, device: int, port: int, slots: int, ctx: int) -> ReplicaHandle:
        """Start one engine replica pinned to `device`, serving `slots` sequences
        over `ctx` total context. Returns immediately; caller waits on health()."""
        ...

    def health(self, port: int, timeout_s: float = 300.0) -> bool:
        """Block until the replica answers healthy, or timeout."""
        ...

    def stop(self, handle: ReplicaHandle) -> None:
        """Terminate a replica (idempotent)."""
        ...

    # --- serving -----------------------------------------------------------
    def stream(self, port: int, prompt: str, n_predict: int, *, slot: int = -1,
               cache_prompt: bool = False, temperature: float = 0.7,
               label: str = "s") -> SessionStats:
        """Stream a completion; derive TTFT/TBT/decode-tps from token timestamps.
        `slot >= 0` pins to a sequence slot; `cache_prompt` reuses resident KV."""
        ...

    # --- the KV-residency seam (this is what makes it denning) --------------
    def save_kv(self, port: int, slot: int, filename: str) -> float:
        """Persist a slot's KV to the host-backed store. Returns wall-clock ms."""
        ...

    def restore_kv(self, port: int, slot: int, filename: str) -> float:
        """Load KV back into a slot (refetch, not recompute). Returns wall-clock ms."""
        ...

    def evict_slot(self, port: int, slot: int) -> None:
        """Free a slot's resident KV (after save, if it should survive eviction)."""
        ...
