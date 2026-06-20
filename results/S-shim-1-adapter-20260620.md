# Result — S-shim-1: the EngineAdapter exists in code (2026-06-20)

*The forward-path build from the paper's §5 "Forward path" bullet and [`../docs/denning-as-shim.md`](../docs/denning-as-shim.md): extract denning's entire engine-specific surface into one adapter, so the control plane (budget-reader, admission, router, lifetime-class arena) can be written against `EngineAdapter` and never name a specific engine. Harness → library.*

## What shipped
- [`../denning/engine/base.py`](../denning/engine/base.py) — the `EngineAdapter` protocol + `ReplicaHandle` / `SessionStats`. The whole engine-specific contract: `spawn_replica / health / stop`, `stream`, and the KV-residency seam `save_kv / restore_kv / evict_slot`.
- [`../denning/engine/llamacpp.py`](../denning/engine/llamacpp.py) — `LlamaCppAdapter`, consolidating the primitives proven in `experiments/h4_twocard.py` (replica-per-card spawn + stream) and `experiments/h4_swap_arena.py` (slot save/restore = the S1 seam). The only engine-specific code in denning.

## Verified
**Dry-run (no GPU):** import graph clean, `LlamaCppAdapter` satisfies `EngineAdapter` (`runtime_checkable`), binary + model + slot-dir all resolve.

**Smoke (on-rig, Card B / device 1, Qwen3-30B-A3B-Q4, 2 slots, ctx 8192):** every adapter method exercised against a live `llama-server`, spawn→stream→save→evict→restore→stream→stop:

| step | value |
|---|---|
| health | true |
| cold stream | 105.5 t/s decode, **TTFT 296.9 ms** (fresh prefill) |
| `save_kv` | 31.3 ms |
| `evict_slot` | ok (erase) |
| `restore_kv` | 2.0 ms |
| warm stream (post-restore) | 107.5 t/s, **TTFT 10.4 ms** |

The warm TTFT collapses **~28×** (296.9 → 10.4 ms): after `restore_kv` the prefix is resident again, so the turn is a cheap hit — R1/S1 confirmed *through the adapter abstraction*, not the experiment script. (Absolute `restore_ms` is tiny here because the smoke prompt is short; the S1 magnitude — 84 ms restore vs 2422 ms re-prefill — is on a 3.5k-token prefix. This run proves the wiring, not the bandwidth.)

## Why it matters
The engine layer is commodity (§8 of the paper); the contribution is the control plane above it. S-shim-1 makes the boundary real in code: the next pieces — `denningd` (budget-reader poll + admission queue + replica-router + arena/swap manager, S-shim-2) — get built against `EngineAdapter`, and a `vllm_xpu.py` / `exllamav3.py` sibling is all it takes to retarget the engine (S-shim-3, also the engine-/vendor-agnosticism proof).

## Reproduce
```
python -m denning.engine.llamacpp --dry-run                 # no GPU
python -m denning.engine.llamacpp --smoke --device 1        # on-rig
```
(run from `D:\work\denning`, or set `PYTHONPATH=D:\work\denning`). driver 32.0.101.8826.
