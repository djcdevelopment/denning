# Related Work — citation tracker + verification status

**Verification discipline:** several entries were surfaced by AI web-research and **post-date the assistant's training cutoff (Jan 2026)** — they are marked `[VERIFY]` and MUST be independently confirmed (read the paper, confirm venue/year/claims) before citing in any submission. An MIT-grade reviewer will check these; so must we.

## The incumbents we must NOT re-claim (the subsumption set)

| Work | What it owns | Status |
|------|-------------|--------|
| vLLM + PagedAttention (SOSP'23) | OS-paging for KV; the baseline | confirmed |
| SGLang + RadixAttention / HiCache | prefix sharing; layer-wise + deadline prefetch; tiering | confirmed (HiCache date `[VERIFY]`) |
| LMCache | engine-independent tiered KV daemon; OTel/Prometheus | confirmed |
| NVIDIA Dynamo **KVBM** | engine-independent tiered KV API; priority+TTL eviction | `[VERIFY]` exact feature set |
| **Continuum / CacheTTL** | per-request KV TTL pinning on vLLM (ICLR'26) | `[VERIFY]` (ICLR'26 acceptance, arXiv 2511.02230) |
| **kvcached** | "OS-style virtual memory abstraction" for KV; vLLM+SGLang | `[VERIFY]` (production date, backers) |
| vLLM native `OffloadingConnector` | in-engine per-request offloading/tiering | `[VERIFY]` (v0.11.0, blog 2026-01-08) |
| **Symphony** (HotOS'25) | OS-style syscall + "KVFS" for KV — pre-claims the OS framing | `[VERIFY]` (arXiv 2510.25412) |
| **vAttention** (ASPLOS'25) | *removes* software paging via HW VM — counter-trend | `[VERIFY]` (arXiv 2405.04437) |
| PTask (SOSP'11) | "OS abstractions for GPUs" — the 15-yr-old framing | confirmed |

## Expert-residency / MoE-offload (why the 6th wedge is DEMOTED to generalization-evidence)

| Work | What it owns | Status |
|------|-------------|--------|
| **KTransformers** (SOSP'25) | frontier MoE on 1 consumer GPU + CPU/NVMe offload; needs ~382 GB DRAM + Intel AMX (∴ inapplicable to our 16–18 GB-RAM box) | `[VERIFY]` |
| **FluxMoE** (arXiv 2604.02715) | **DECOUPLES** expert residency (our claim is the opposite — *unify*) | `[VERIFY]` |
| **MoE-ERAS** | "Expert Residency Aware Scheduling" | `[VERIFY]` |
| MoE-Infinity | MoE offload serving | `[VERIFY]` |
| llama.cpp #20757 | tiered GPU/RAM/SSD expert cache (LRU/SLRU/LFU + admission) in our own engine | `[VERIFY]` |

## The tradition we BORROW from (cite as foundations)

| Work | Borrowed as |
|------|-------------|
| **Denning** — working-set model + page-fault-frequency load control (CACM 1968) | the admission-control backbone (and the project's namesake) |
| Bélády MIN | optimal eviction reference (we have partial future knowledge) |
| Segcache (NSDI'21) | TTL-grouped segments → per-class (not per-block) metadata, off the hot path |
| ARC / ghost lists (ZFS) | recompute-avoided regret telemetry |
| Tofte–Talpin regions; generational GC | lifetime classes as proven adjacent-domain prior art |
| AdaptSize (NSDI'17) | size-aware admission |
| dm-cache / page-cache writeback | per-class write policy |

## Hardware / platform facts to cite (all `[VERIFY]`)
- Intel Arc Pro B70: 32 GB, ~608 GB/s GDDR6, ~22.9 TFLOPS FP32 / 367 INT8 TOPS (launch ~Mar 2026).
- Intel "Arc does not support GPU-to-GPU connection"; Project Battlematrix / llm-scaler delivers PCIe P2P + multi-GPU on **Linux** (Ubuntu 25.04, VT-d off + ReBAR).
- vLLM #41663 / #27408: GP-fault on dual B70 TP=2 (tensor-parallel unavailable on this box).
- ipex-llm archived 2026-01-28.
- DeepSeek-V4: ~9.62 GiB KV at 1M context (KV residency persists at the frontier).
