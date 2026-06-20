"""denning control plane -- the engine-agnostic half (talks only to EngineAdapter).

  budget.py    -- live VidMm budget reader (the admission oracle; drops 31->15 under a co-tenant)
  admission.py -- closed-form admit on the live budget (N* = min(compute, memory))
  router.py    -- replica-per-card placement (no cross-card pool; R3 says it doesn't pay)

Next: denningd wires these + the lifetime-class KV arena over the adapter (S-shim-2).
"""

from denning.control.admission import AdmissionController, n_star_memory, validate_h1_sweep
from denning.control.router import ReplicaRouter

__all__ = ["AdmissionController", "n_star_memory", "validate_h1_sweep", "ReplicaRouter"]
