#!/usr/bin/env python3
r"""Closed-form admission controller -- denning's defense (I-4a + I-4b).

Since you cannot pin against a co-tenant, you admit beneath the live budget. The
admission limit has two terms, and N* is their minimum:

    N*_memory(B) = floor((B - W) / k(ctx))   # I-4a: how many KV sets fit the live budget B
    N*_compute   = COMPUTE_KNEE              # I-4b: closed-loop goodput knee (~8 here)
    N*           = min(N*_compute, N*_memory)

Admit a new session iff (a) the model weights fit the live budget at all, and
(b) we are below N*. Memory binds under a co-tenant / large context (I-4a, H1);
compute binds when memory is plentiful (I-4b). The controller takes the min.

The constants are this rig's measurements; pass your own to retarget. The
`validate_h1_sweep` self-test replays the measured H1 demotion cliff and checks the
rule predicts it (5/5) -- the I-4a result, now a library invariant.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- measured on this rig (experiments/admission_controller.py, I-4a/b) ---
CARD_BUDGET_GB = 31.12          # uncontended VidMm budget
MODEL_W_GB = 17.9               # Qwen3-30B-A3B Q4 resident weights
COMPUTE_KNEE = 8                # I-4b closed-loop goodput knee (compute-concurrency term)

# H1 resident hog sweep (measured): hog cap GB -> decode ratio (cliff := ratio < 0.8)
H1_SWEEP = [(10, 0.998), (12, 0.997), (14, 0.231), (16, 0.196), (18, 0.165)]


def n_star_memory(budget_gb: float, weights_gb: float, kv_per_session_gb: float) -> int:
    """How many resident KV sets fit beneath the live budget (the I-4a memory term)."""
    if kv_per_session_gb <= 0:
        return 0
    return max(0, int((budget_gb - weights_gb) // kv_per_session_gb))


@dataclass
class AdmissionController:
    weights_gb: float = MODEL_W_GB
    kv_per_session_gb: float = 0.1
    compute_knee: int = COMPUTE_KNEE

    def capacity(self, live_budget_gb: float) -> int:
        """N* = min(compute-concurrency, memory-budget) on the LIVE budget."""
        if self.weights_gb > live_budget_gb:          # model itself doesn't fit
            return 0
        return max(0, min(self.compute_knee,
                          n_star_memory(live_budget_gb, self.weights_gb, self.kv_per_session_gb)))

    def admit(self, resident_sessions: int, live_budget_gb: float) -> bool:
        """Admit one more session iff it stays at/below N* for the live budget."""
        return resident_sessions < self.capacity(live_budget_gb)

    def fits(self, footprint_gb: float, live_budget_gb: float) -> bool:
        """The raw I-4a predicate: a footprint is admissible iff it fits the budget."""
        return footprint_gb <= live_budget_gb


def validate_h1_sweep(weights_gb: float = MODEL_W_GB, verbose: bool = False) -> tuple[int, int]:
    """Does 'admit iff weights <= live budget' predict the measured H1 cliff? (I-4a)"""
    ok = 0
    if verbose:
        print(f"  {'hog GB':>6} {'eff budget':>11} {'decision':>9} {'measured':>9} {'match':>6}")
    for hog, ratio in H1_SWEEP:
        eff = CARD_BUDGET_GB - hog
        fits = weights_gb <= eff
        decision = "ADMIT" if fits else "DEFER"
        measured = "fast" if ratio >= 0.8 else "CLIFF"
        match = (fits and ratio >= 0.8) or ((not fits) and ratio < 0.8)
        ok += int(match)
        if verbose:
            print(f"  {hog:>6} {eff:>9.1f}G {decision:>9} {measured:>9} {('Y' if match else 'N'):>6}")
    return ok, len(H1_SWEEP)
