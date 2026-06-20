# denning as a shim around an engine

*2026-06-20. Written after re-verifying vLLM's Intel-Arc status on the web (§1). The conclusion of that re-check: denning is **not** an inference engine and should never become one. It is the **co-residency control plane** that sits above an engine — any engine — and does the one thing neither llama.cpp nor vLLM/llm-scaler does: arbitrate KV residency against an adversarial desktop OS. This doc sketches that shim.*

---

## 1. What the web re-check changed (and didn't)

Re-verified 2026-06-20 (sources at bottom). The landscape moved since ipex-llm was archived:

- **vLLM now officially runs on the Arc Pro B70.** Intel `llm-scaler-vllm:0.14.0-b8.2` (Apr 2026) lists official B70 support; single- *and* dual-card (2× B70, 64 GB) are tested. ipex-llm was archived 2026-01-28; the XPU backend is now upstreamed into mainline PyTorch, and **llm-scaler** (a Docker-ized vLLM) is the supported path.
- **Multi-GPU works — TP, PP, and DP.** llm-scaler exposes tensor-parallel (`-tp 2/4`), pipeline-parallel (`--pipeline-parallel-size`), and data-parallel ("multiple independent vLLM server instances, each with its own copy of the model on separate GPUs" — i.e. **replica-per-card, which is exactly our two-card result**). Puget benchmarked 4× B70 TP=4: Llama-3.1-8B 35→70 t/s (1.99×), and 27B/35B models that only fit at TP=4 reaching 122 t/s at 8 concurrent users.

Three facts make this **vindicate** denning rather than obsolete it:

1. **The P2P fault we hit (#41663) wasn't fixed — it was avoided.** Intel's own multi-GPU vLLM "routes inter-GPU communication through host RAM rather than direct PCIe peer-to-peer transfers" with `CCL_TOPO_P2P_ACCESS=0` **to avoid bus errors.** That is our R3 finding (no P2P on these cards; card→card is host-bounced at 0.47×) confirmed by Intel's shipping config. TP=2 across two B70s pays the host-RAM all-reduce tax on every layer; replica-per-card (what denning routes) doesn't.
2. **None of it runs on native Windows.** vLLM has no Windows support and no roadmap; the official answer is WSL2 (a Linux VM). denning's entire setting — WDDM/VidMm evicting foreground inference, the live `QueryVideoMemoryInfo.Budget` dropping 31→15 GB under the desktop co-tenant, the display card as a co-tenant you can't pin against — is a **native-Windows-desktop** phenomenon that the Linux/Docker stack never sees.
3. **The engines assume static residency.** vLLM and llm-scaler admit on a fixed VRAM budget and never expect a co-tenant to claw memory back mid-serve. Admission on the *live* budget, lifetime-class eviction order, and cheap KV swap — the denning contributions — are exactly the gap they leave open.

**So:** the part of denning that "feels like rebuilding vLLM" (replica-per-card serving) *is* a commodity now — good, stop building it. The part that's novel (co-residency control under an adversarial OS) is orthogonal to the engine and is the whole contribution. That argues for making denning a **shim**: keep the control plane, rent the tensor math.

---

## 2. The boundary: control plane vs. engine

```
                         ┌──────────────────────────────────────────────┐
   client sessions  ───▶ │                  denning                     │
   (N agents)            │            (co-residency shim)                │
                         │                                              │
                         │  ┌────────────┐   live budget    ┌─────────┐ │
                         │  │ budget-    │◀─────────────────│ VidMm   │ │   ← Windows
                         │  │ reader     │  QueryVideoMemory│ (WDDM)  │ │     desktop OS
                         │  └─────┬──────┘  Info.Budget     └─────────┘ │     (the co-tenant)
                         │        ▼                                     │
                         │  ┌────────────┐   admit / queue / reject     │
                         │  │ admission  │   N* = min(compute, mem,     │
                         │  │ controller │           live budget)       │
                         │  └─────┬──────┘                              │
                         │        ▼                                     │
                         │  ┌────────────┐   place on a card            │
                         │  │ replica-   │   (no cross-card pool;        │
                         │  │ router     │    R3 says P2P doesn't pay)   │
                         │  └─────┬──────┘                              │
                         │        ▼                                     │
                         │  ┌────────────┐   evict by lifetime class,   │
                         │  │ KV arena / │   swap KV host↔card           │
                         │  │ swap mgr   │   (restore 84ms ≫ 29× < re-   │
                         │  └─────┬──────┘    prefill)                   │
                         │        ▼                                     │
                         │  ┌────────────────────────────────────────┐ │
                         │  │ engine adapter (thin, per-engine)       │ │
                         │  └───┬──────────────────┬─────────────────┘ │
                         └──────┼──────────────────┼───────────────────┘
                                ▼                  ▼
                        ┌───────────────┐  ┌───────────────┐
                        │ llama-server  │  │ vLLM-XPU /    │   ← unmodified engines,
                        │ (Win/Vulkan)  │  │ llm-scaler    │     one replica per card
                        │  Card A,B     │  │ (Linux/WSL2)  │
                        └───────────────┘  └───────────────┘
```

denning owns **policy**; the engine owns **tensor math + the KV bytes**. The boundary is the engine adapter — everything left of it is engine-agnostic and is what we've already measured.

---

## 3. The five components — each already validated by an experiment

| Component | What it does | Already proven by | Engine-specific? |
|---|---|---|---|
| **budget-reader** | Polls per-adapter live VidMm budget; detects the co-tenant clawback (31→15 GB) | H1 + I-4a (budget oracle predicts the eviction cliff 5/5) | No — `IDXGIAdapter3::QueryVideoMemoryInfo`, pure Windows/DXGI |
| **admission controller** | Admit iff footprint ≤ live budget **and** concurrency ≤ compute knee; else queue/reject | I-4a/b/c (`N* = min(compute≈8, memory, live-budget)`; closed-loop knee, over-admit → goodput 0) | No — works on byte/slot counts |
| **replica-router** | Places a session on a card; **no cross-card pooling** (R3: P2P host-bounced, doesn't pay) | two-card scaling (1.96× raw) + two-card goodput (N\* 8→16) | No — just picks a backend URL |
| **KV arena / swap mgr** | Orders eviction by lifetime class; swaps KV host↔card on cheap restore | H4 (+32% on-rig, +365% block-grained, TTL≡LRU) + S1 (restore 29× < re-prefill; swap dominates the policy lever) | **Boundary** — needs the engine's save/restore primitive |
| **engine adapter** | Thin per-engine driver exposing {spawn replica, save KV slot, restore KV slot, stream} | llama-server today: `/slots/{id}?action=save\|restore`, `-np`, `GGML_VK_VISIBLE_DEVICES` | **Yes** — the only engine-specific code |

The first four are the contribution and are already built as experiment harnesses (`admission_controller.py`, `i4b_closed_loop.py`, `i4c_memory_knee.py`, `h4_arena.py`, `h4_swap_arena.py`, `h4_twocard.py`). Promoting them to a shim is mostly **consolidation**, not new research.

---

## 4. The engine adapter interface

The whole engine-specific surface is small. A backend implements:

```python
class EngineAdapter(Protocol):
    def spawn_replica(self, device: int, port: int, slots: int, ctx: int) -> Handle: ...
    def health(self, port: int, timeout_s: float) -> bool: ...
    def stream(self, port: int, prompt: str, n_predict: int) -> SessionStats: ...  # TBT/TTFT/decode_tps
    # the KV-residency seam — the part that makes it denning and not a load balancer:
    def save_kv(self, port: int, slot: int, path: str) -> int:    ...  # -> bytes written
    def restore_kv(self, port: int, slot: int, path: str) -> float: ... # -> restore ms
    def evict_slot(self, port: int, slot: int) -> None: ...
```

- **llama.cpp adapter (ships today, Windows/Vulkan):** `spawn_replica` → `llama-server -ngl 99 -np <slots> -c <ctx> --slot-save-path D:\...`; `save/restore_kv` → `POST /slots/{id}?action=save|restore`; this is exactly `h4_twocard.py` + `h4_swap_arena.py` refactored behind the interface.
- **vLLM-XPU adapter (Linux/WSL2, when we want it):** `spawn_replica` → a vLLM OpenAI server per card (data-parallel, *not* TP — R3 says TP's host all-reduce doesn't pay on these cards); `save/restore_kv` → vLLM's prefix-cache / KV-connector export. Note vLLM's KV seam is coarser (prefix-cache, not arbitrary sequence slots), so the arena there is block/prefix-grained — which is the regime H4-blockgrained already modeled.

The router and admission controller never know which adapter is underneath. That is the engine-agnostic claim, made concrete.

---

## 5. Why a shim and not a fork

- **We don't out-engineer Intel's kernels.** llm-scaler ships oneCCL, torch.compile, speculative decoding, FP16 multi-GPU. Forking an engine to add co-residency means re-inheriting all of that forever. A shim composes with it.
- **The contribution is portable.** The same control plane wraps llama.cpp on native Windows (where vLLM cannot go — the adversarial-OS setting that is the paper's whole point) *and* vLLM-XPU on Linux (where co-residency still matters whenever the box also drives a display or runs other tenants). Engine-agnostic = the result outlives whichever engine wins.
- **It sharpens the paper.** denning stops being "another way to serve LLMs on Arc" (a crowded, Intel-owned space) and becomes "the residency control plane for LLM state on an OS-arbitrated GPU" — a layer nobody else occupies. The related-work delta is clean: vLLM/llm-scaler/SGLang admit on a *static* budget and assume they own the device; denning admits on the *live* budget and assumes it is a guest.

---

## 6. What we'd build to ship it (stages)

1. **S-shim-1 — extract the adapter.** Refactor `h4_twocard.py` + `h4_swap_arena.py` into `denning/engine/llamacpp.py` behind the `EngineAdapter` protocol. No new behavior; pure consolidation of proven code. (~½ day)
2. **S-shim-2 — the daemon.** A long-lived `denningd` that owns: budget-reader poll loop (I-1 watchdog already does the polling), admission queue (I-4b logic), replica-router (round-robin/least-loaded over per-card adapters), arena/swap manager (H4 + S1). Exposes one OpenAI-compatible endpoint to clients; fans out to the per-card replicas. (~2–3 days)
3. **S-shim-3 — second adapter (optional, proves the claim).** A `vllm_xpu.py` adapter under WSL2/Linux, data-parallel replicas, prefix-cache KV seam. Even a thin version validates "engine-agnostic" empirically and gives the paper a second data point. (~2 days, needs a Linux/WSL2 harness)

S-shim-1 and -2 are the product; S-shim-3 is the proof. None of it is new physics — every policy is already measured. It is the packaging that turns the experiment suite into "a thing you can run."

---

## Sources (verified 2026-06-20)

- Phoronix — *Intel LLM-Scaler vllm-0.14.0-b8.2 Released With Official Arc Pro B70 Support* — https://www.phoronix.com/news/Intel-LLM-Scaler-vllm-0.14-b8.2
- Puget Systems — *Intel Arc Pro B70: Multi-GPU AI Inference Performance* — https://www.pugetsystems.com/labs/articles/intel-arc-pro-b70-multi-gpu-ai-inference-performance/
- DeepWiki — *Multi-GPU and Parallelism | intel/llm-scaler* — https://deepwiki.com/intel/llm-scaler/2.5-multi-gpu-and-parallelism
- fazm.ai — *vLLM on Windows in 2026: what officially works* — https://fazm.ai/t/vllm-windows-support-2026
- XDA — *Intel's $949 GPU has 32GB of VRAM for local AI, but the software is why Nvidia keeps winning* — https://www.xda-developers.com/intel-gpu-32gb-vram-local-ai-software-nvidia-keeps-winning/
- GitHub — *intel/ipex-llm* (archived 2026-01-28) — https://github.com/intel/ipex-llm
