"""Engine adapters -- the ONLY engine-specific code in denning.

Everything above the adapter (budget-reader, admission, router, KV arena) is
engine-agnostic and depends only on `base.EngineAdapter`. Today: llama.cpp
(Windows/Vulkan). Next: vLLM-XPU (Linux), ExLlamaV3 (NVIDIA/Windows).
"""

from denning.engine.base import EngineAdapter, ReplicaHandle, SessionStats

__all__ = ["EngineAdapter", "ReplicaHandle", "SessionStats"]
