# Result — S-shim-2: denningd, the co-residency control loop (2026-06-20)

*The control plane now exists as a runnable thing. `denningd` wires the four
engine-agnostic pieces onto the `EngineAdapter` from [S-shim-1](S-shim-1-adapter-20260620.md):
budget-aware admission → replica-per-card routing → lifetime-class KV arena → the
engine's stream. One unmodified engine underneath; denning is everything above it.*

## What shipped
- [`../denning/control/arena.py`](../denning/control/arena.py) — `LifetimeClassArena` (H4 + S1). Policy decides *what* to evict/restore (lifetime class > recency; swap-not-recompute); the adapter moves the bytes. Engine-agnostic by construction.
- [`../denning/denningd.py`](../denning/denningd.py) — `Daemon`: the control loop. `handle(conv, prompt)` routes (session affinity), admits on the live VidMm budget (`in-flight ≤ N*`), runs the per-replica arena (hit/restore/prefill), and streams via the adapter. `handle_many` serves concurrently across cards.
- [`../denning/control/router.py`](../denning/control/router.py) — added `reserve()` so admission can gate concurrent in-flight sessions.
- [`../tests/test_shim.py`](../tests/test_shim.py) — 18 assertions against a `FakeAdapter` (a valid `EngineAdapter` with counted no-op KV moves) — the whole shim verified off-rig.

## Verified (no GPU — `python tests/test_shim.py` → PASS, 18/18)
- **Arena**: accounting holds; swap turns misses into restores (22→17 re-prefills, 5 restores — the S1 lever); swap-off → all re-prefills, zero saves; adapter call-counts match arena stats.
- **Daemon**: 16 sessions admitted, **round-robin balanced 8/8** across two cards; per-replica arena sums to 16 turns; **session affinity** holds (each conv stays on one card) and **returning convs hit resident KV**; admission **sheds beyond N\*** when the live budget is squeezed (capacity 2/card → rejection counted).

## A bug that only surfaced once the pieces were wired together
The two-card experiments round-robined *fresh* sessions, so they never exercised a
conversation's *second* turn. Wiring router+arena into `denningd` exposed it: plain
round-robin sent conv 2's turn-2 to the *other* card, missing its resident KV and
paying a full re-prefill. The fix is **session affinity** — a conversation returns
to the card holding its KV (resident or saved-then-restored). Before/after on the
dry-run, conv 2's second turn: `prefill` → **`hit`**. The arena's whole value (KV
residency) is only realized if routing and residency agree on placement; the daemon
is where that contract lives.

## Status of the shim
| piece | state |
|---|---|
| `EngineAdapter` + llama.cpp adapter | ✅ on-rig (S-shim-1) |
| budget / admission / router | ✅ no-GPU verified |
| lifetime-class arena + swap | ✅ no-GPU verified |
| `denningd` control loop + affinity | ✅ no-GPU verified |
| `denningd --serve` on two real cards | ⏳ next on-rig run (loads the display card) |
| OpenAI-compatible HTTP front | ⏳ thin wrapper on `handle` |
| vLLM-XPU / ExLlamaV3 adapters | ⏳ S-shim-3 (the engine-agnostic proof) |

## Reproduce
```
python tests/test_shim.py                       # no GPU: 18/18 PASS
python -m denning.denningd --dry-run            # no GPU: wiring over a fake engine
python -m denning.denningd --serve --cards 2 --n 16   # on-rig: real replica per card
```
(run from `D:\work\denning`, or `PYTHONPATH=D:\work\denning`).
