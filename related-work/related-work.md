# Related Work — citation tracker (verified 2026-06-19)

**All entries below were web-verified on 2026-06-19** (agent run). None were hallucinated; corrections are applied inline. Six fixes were needed (venue/title/artifact-type/attribution) — flagged **[FIX]**. Methods-section reads still recommended before camera-ready for the load-bearing threats.

## Incumbents we must NOT re-claim (subsumption set)

| Work | What it owns | Overlap vs denning |
|------|-------------|--------------------|
| vLLM + PagedAttention (SOSP'23) | OS-paging for KV; the baseline | foundational baseline |
| SGLang HiCache (LMSYS 2025-09-10) | L1/L2/L3 GPU/host/distributed tiering, layer-wise prefetch | tiering mechanism; no admission model / no VidMm |
| LMCache | engine-independent tiered KV daemon | mechanism, CUDA/Linux |
| **NVIDIA Dynamo KVBM** | engine-independent 4-tier KV API, **priority+TTL** eviction via `cache_control` | **closest incumbent** — but CUDA/fabric/datacenter, no closed-form admission, no OS-mem-mgr co-residency on RAM<VRAM Windows/Arc |
| Continuum / CacheTTL (arXiv 2511.02230) | per-request KV TTL pinning on vLLM (~1k LoC) | **[FIX]** venue = **Lifelong Agent Workshop @ ICLR 2026 (workshop)**, not main track. TTL is one mechanism we share; no lifetime *classes*, no admission, no VidMm |
| kvcached (`ovg-project/kvcached`) | "OS-style virtual memory" for KV via CUDA VMM; vLLM+SGLang | elastic GPU-VM for multi-model sharing on CUDA — orthogonal mechanism, not our policy/substrate |
| vLLM native OffloadingConnector | in-engine async CPU KV offload (v0.11.0, 2025-10-02) | the "absorption machine"; in-engine, CUDA |
| Symphony (HotOS'25, arXiv 2510.25412) | syscall interface + **KVFS** filesystem for KV | pre-claims the OS/FS *framing*; no admission controller, no VidMm co-residency. **Also a SOSP'25 follow-up (arXiv 2510.24051) — cite both** |
| vAttention (ASPLOS'25, arXiv 2405.04437) | removes software paging via HW VM (CUDA VMM) | counter-trend (remove indirection); MSR |
| PTask (SOSP'11) | "OS abstractions for GPUs" | the 15-yr-old framing |

## Expert-residency / MoE-offload (why the 6th wedge is DEMOTED to generalization-evidence)

| Work | What it owns | Note |
|------|-------------|------|
| KTransformers (SOSP'25, DOI 10.1145/3731569.3764843) | frontier MoE on 1 consumer GPU + CPU/NVMe offload; ~382 GB DRAM | **[FIX]** Intel AMX is *recommended, not required* (AVX2 `kt-kernel` backend, Mar 2026). DRAM-capacity argument (inapplicable to a 32 GB-RAM box) **stands**; hard-AMX argument does not |
| FluxMoE (arXiv 2604.02715, CUHK+SCITIX, Apr 2026) | **DECOUPLES** expert residency (PagedTensor streaming), up to 3.0× vLLM | counter-positioned — opposite of our *unify*; the cleanest contrast cite, not a threat |
| MoE-ERAS | residency-aware expert **selection** | **[FIX]** title = "Expert Residency Aware **Selection**" (not Scheduling); venue **ISCA 2024 / MLArchSys workshop** |
| MoE-Infinity (arXiv 2401.14361) | activation-aware expert offloading + prefetch | |
| llama.cpp **#20757** | 3-tier GPU/RAM/SSD expert cache, LRU/SLRU/LFU + admit-on-2nd-miss | **[FIX]** it's an **Issue**, not a PR (substance accurate) |

## The tradition we BORROW from (cite as foundations)

| Work | Borrowed as |
|------|-------------|
| **Denning — working-set model** (CACM 1968, DOI 10.1145/363095.363141) | the working-set language for admission |
| **Page-fault-frequency load control** — **[FIX] SEPARATE later line** (Chu & Opderbeck 1972/76; Denning, "Working Sets Past and Present," IEEE TSE 1980) | the load-control/anti-thrash backbone. **Do NOT attribute PFF to the 1968 paper.** (Project is named for the *tradition*, cite both.) |
| Bélády MIN | optimal-eviction reference (we have partial future knowledge) |
| **CacheGen** (SIGCOMM'24, arXiv 2310.07240) | **the direct prior art for the compression arm** — KV compressed into bitstreams for fast *transfer*, then decoded |
| Segcache (NSDI'21) | TTL-grouped segments → per-class metadata off the hot path |
| ARC / ghost lists (ZFS) | recompute-avoided regret telemetry |
| Tofte–Talpin regions; generational GC | lifetime classes as proven adjacent-domain prior art |
| AdaptSize (NSDI'17) | size-aware admission |
| dm-cache / page-cache writeback | per-class write policy |

## Hardware / platform facts (all verified 2026-06-19)
- **Intel Arc Pro B70:** 32 GB GDDR6, **608 GB/s**, **22.9 TFLOPS FP32 / 367 INT8 TOPS**, BMG-G31, launched **2026-03-25** (Intel spec page + Tom's Hardware).
- Intel: **"Arc does not support GPU-to-GPU connection"** (verbatim support article). **Project Battlematrix / llm-scaler 1.0** delivers PCIe P2P + multi-GPU (up to 8 Arc Pro), **Linux** containerized.
- **ipex-llm archived 2026-01-28** (fixes upstreamed to PyTorch 2.9).
- **vLLM #41663** = the real **dual-B70 TP=2 GP-fault** (GP fault + xe BCS engine reset). **[FIX] #27408 is a different bug** — SIGABRT on dual **B60** during model inspection (not B70, not TP). Cite #41663 for the TP fault.

## Positioning (one-line delta vs the nearest threats)
- **vs KVBM** (closest): KVBM is engine-independent tiered KV with priority+TTL, but assumes the engine owns HBM + a fast fabric on CUDA/Linux; denning operates where the OS (VidMm) arbitrates residency, the fabric is absent, and RAM<VRAM — and adds a *closed-form* admission controller, not a heuristic tier policy.
- **vs Symphony**: it pushes KV management *up* to the user program via a filesystem; denning pushes residency arbitration *down* to coexist with VidMm. Complementary, inverted.
- **vs kvcached / Continuum**: each ships one mechanism we also use (elastic VM / TTL); neither has lifetime *classes*, the closed-form admission model, or the OS-co-residency substrate.
