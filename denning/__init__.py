"""denning -- co-residency control plane for LLM state on an OS-arbitrated GPU.

denning is NOT an inference engine. It is the control plane that sits above one:
budget-reader -> admission -> replica-router -> lifetime-class KV arena/swap,
talking to an unmodified engine through a thin per-engine adapter
(`denning.engine.base.EngineAdapter`). See docs/denning-as-shim.md.
"""

__version__ = "0.0.1"
