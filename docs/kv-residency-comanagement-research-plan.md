# Research Plan — KV Residency Co-management under an Adversarial OS GPU Memory Manager

*Generated 2026-06-19 from an 11-agent survey + adversarial red-team + synthesis workflow (run `wf_2911cb8d-ed5`). Prior-art claims dated 2025–2026 and specific issue/paper numbers were surfaced by agent web-research and **must be independently verified before citing** — several post-date the assistant's training knowledge.*

---

## 0. One-line thesis (PIVOTED)

> When the OS already owns GPU residency (Windows/WDDM/VidMm) and there is **no fast fabric** (PCIe-only, no NVLink/Xe-Link, broken Level-Zero P2P on Intel Arc), correct KV-cache management is **not transparent paging**. It is (1) **co-scheduling residency with an adversarial OS memory manager** that can evict your KV under a shifting DXGI budget, and (2) **bandwidth-roofline-aware admission control** over which sequences may decode concurrently — with a small declarative **reuse-provenance lifetime-class contract** as the single control signal that residency priority, write policy, and admission all read.

**The contribution is a co-management *model* + an anti-paging *design point*, not new paging, new eviction, or a portable "OS for the KV cache."**

---

## 1. What died, and why (the pivot)

The opening ambition — "treat LLM context as an OS-managed resource with five first-class pillars (lifetime classes, residency, prefetch, eviction, telemetry), portable across engines" — **does not survive adversarial review.** All four red-team lenses (novelty, abstraction-validity, adoption, OSDI/NSDI Reviewer 2) returned **"reframe-needed,"** and they agreed on the cause: the space is far more occupied in 2025–2026 than the premise assumed.

Four of the five pillars are already shipped or peer-reviewed:

| Pillar | Already done by | Verify |
|---|---|---|
| Residency / tiering + engine-independent layer | **NVIDIA Dynamo KVBM** (G1 HBM→G2 host→G3 SSD→G4 remote, block lifecycle, connectors for vLLM/TRT-LLM, *priority-based eviction + TTL pinning* per live docs); **LMCache** (standalone daemon, GPU/CPU/NVMe/Redis/S3, OTel+Prometheus) | docs.nvidia.com/dynamo/components/kvbm ; arXiv 2510.09665 |
| Lifetime drives retention | **Continuum / CacheTTL** — per-request KV TTL pinning on vLLM, ~8× JCT, "performant across hardware setups," reportedly **accepted to ICLR 2026** | arXiv 2511.02230 |
| Eviction (priority/learned) | TensorRT-LLM priority eviction (+~20% hit rate); **"Rethinking Caching for LLM Serving"** (arXiv 2508.18736); **LCR/LARU** Belady-competitive learned eviction (arXiv 2509.20979) | — |
| Prefetch + residency | **SGLang HiCache** (layer-wise + deadline-aware prefetch, HiRadixTree); **InfiniGen** (OSDI'24); **AttentionStore** (ATC'24) | lmsys.org/blog/2025-09-10-sglang-hicache |
| Telemetry | **vLLM** already emits `KVCacheEvictionEvent{lifetime_seconds, idle_seconds, reuse_gaps_seconds}`; **LMCache** OTel/Prometheus block-lifecycle tracing; **llm-d** real-time KV-locality index | deepwiki vllm metrics |

And two independent threats hit the *framing* and the *adoption path*:

- **The framing is claimed.** **Symphony — "Serve Programs, Not Prompts" (HotOS'25, arXiv 2510.25412)** builds an OS-style syscall + "KVFS" filesystem interface for the KV cache *at an OS venue*. Going back further, **PTask (SOSP'11)** / Rossbach "OS must support GPU abstractions" established "manage the GPU as an OS-arbitrated resource" 15 years ago. "OS for KV" pattern-matches in a reviewer's first 90 seconds.
- **The adoption niche is occupied.** **kvcached** (github.com/ovg-project/kvcached) already ships an *"OS-style virtual memory abstraction"* for KV across **both vLLM and SGLang**, multi-vendor backed (NVIDIA/Intel/AMD/Google/Red Hat/ByteDance/Alibaba/Tencent), ~1.1k stars, **productionized by Red Hat (April 2026)** — and it won by doing **one** pillar well and deferring tiering/eviction/lifetime to the engines.
- **The absorption machine is running.** **vLLM v0.11.0 (Oct 2025)** shipped a native pluggable `OffloadingConnector`; the tree now lists per-request offloading policy, tiering, and object-store secondary tier **in-engine, default-on**. Any good standalone policy lands as a ~200-line PR, not a new dependency.

**Honest correction to the project's opening premise:** the white space is *not* "tier/share/page the KV cache" and *not* "the OS framing." Those are taken.

---

## 2. What survives — and why it is non-absorbable

Exactly one region has **no subsumption threat**: the **Windows/WDDM/VidMm + Intel-Arc + PCIe-only** regime. The wedge is **LOAD-BEARING** (remove it and the project dies on KVBM + LMCache + Continuum) for three independent reasons:

1. **Non-absorption.** Every incumbent assumes the *engine owns HBM* (CUDA) and a *coherent/RDMA fabric* (NVLink/Xe-Link). Both are **false** on the target. None model an OS memory manager (VidMm) evicting your KV from underneath you — the **"two memory managers fighting"** problem. It cannot be closed by an upstream PR because it needs a *different residency substrate* (D3D12 `MakeResident`/`Evict`/`SetResidencyPriority`/`QueryVideoMemoryInfo`, **not** CUDA VMM).
2. **It makes the physics legible.** The ~17× HBM/PCIe cliff (≈456 GB/s GDDR6 vs ≈26 GB/s PCIe Gen4) is what converts "tiering" into **admission control**; the ~14× advantage NVLink-C2C (900 GB/s) buys NVIDIA is *exactly why datacenter systems never had to discover this design point*. This regime is the only one where the roofline **forces** the non-obvious design — turning the "negative result" risk into the intellectual contribution.
3. **It is the portability proof.** A lifetime-class contract that drives policy on **both** a VidMm/D3D12 substrate **and** a CUDA/Level-Zero substrate is the only credible evidence the abstraction is substrate-portable rather than CUDA-shaped.

---

## 3. Novelty wedges (the defensible claims)

1. **VidMm co-management protocol** — a KV residency planner that *cooperates* with WDDM VidMm: maps lifetime classes → `SetResidencyPriority`, reacts to a `QueryVideoMemoryInfo` budget that shrinks when the desktop compositor/other apps demand VRAM, and avoids the double-paging / priority-inversion failure where both VidMm and the engine evict the same KV. Structurally impossible on CUDA, where the app owns HBM.
2. **Bandwidth-roofline admission control as the eviction mechanism** — a *formalized, measured* model that **never pages actively-decoding KV**, gates concurrent-decode count to fit the HBM-bandwidth roofline, and relocates *only* demonstrably-idle/reusable KV (paused sessions, shared prefixes, speculative branches) where transfer amortizes over many reuses.
3. **PCIe-only / no-P2P multi-Arc topology** where host DRAM is a *forced L2 hub* (Level-Zero P2P returns `-995` on Arc), with an explicit **recompute-vs-refetch cost model that inverts** relative to datacenter assumptions: recomputing a prefix (compute-bound prefill) can beat refetching it over PCIe (bandwidth-bound) — the opposite of the NVLink regime.
4. **Reuse-provenance lifetime-class contract** (system-prompt / session / turn / one-shot / sink) as a single typed signal driving residency priority + write policy + admission eligibility — with the **classes-ON vs classes-OFF ablation** proving the typing is load-bearing, not dressing.
5. **Telemetry the incumbents don't export** — per-class miss-ratio curves (Mattson reuse-distance), ghost-list "recompute-avoided" regret accounting, and uniquely **decode-stall-attributable-to-VidMm-eviction** (budget-pressure events correlated with TBT spikes).

---

## 4. OS / systems → KV-cache borrow map

*This is the "existing paths to borrow" deliverable. Note the irony: because the target is Windows, the famous **Linux** mechanisms (userfaultfd = user-defined demand paging; DAMON/DAMOS = access-driven demotion; cgroups v2 memory.high/PSI = pressure signal; MGLRU) are the **intellectual scaffolding**, but the real implementation substrate is **D3D12 residency** — and that gap is precisely where the novelty lives.*

| Mechanism (origin) | KV-cache application | Role |
|---|---|---|
| **Denning working-set + Page-Fault-Frequency load control** (CACM 1968) | Request KV working set = {sinks} ∪ {recency window} ∪ {query-dependent top-k}; admit a sequence to concurrent decode only if summed working sets fit the bandwidth roofline. PFF signal = VidMm eviction/budget-pressure rate. | **Load-bearing** — reframes the work as *load control under a roofline* (the anti-paging point) |
| **D3D12 explicit residency** — `MakeResident`/`Evict`, `QueryVideoMemoryInfo`, `SetResidencyPriority` | The actual Windows substrate. Lifetime class → residency priority (sink/system = MAX, draft = MIN); `MakeResident` active KV, `Evict` idle KV, re-plan vs shifting budget; fences guarantee the GPU never touches non-resident KV. | The differentiator no CUDA system can have |
| **Segcache TTL-grouped segments** (NSDI'21) | Lifetime classes as segments: tier/priority/TTL stored **once per class-segment**, not per block; finished session = O(1) segment free. | Answers "abstraction leaks into the kernel" — metadata off the per-token path |
| **ARC ghost lists** (ZFS) | Shadow list of evicted KV content hashes; a later prefix-match = measured "recompute/refetch we could have avoided" = regret signal for per-class telemetry. (cf. vLLM issue #40268 requesting ARC for KV.) | Telemetry/audit primitive, off hot path |
| **Tofte-Talpin region inference + generational GC** | Sequence KV = region with a known free point (completion = `letregion` exit); tag blocks with a reuse-provenance generation (ephemeral=nursery / session=survivor / shared-prefix=tenured / sink=immortal) at allocation. | The **proven** adjacent-domain implementation of lifetime classes — cite as prior art; claim only the contract + VidMm mapping |
| **AdaptSize size-aware admission** (NSDI'17) | Gate whether a large low-reuse prefill's KV earns residency, so one 100k-token one-shot can't evict many small high-reuse shared prefixes (the CDN large-object problem, sharpened on scarce Arc HBM). | Adds the size/value-per-byte dimension |
| **dm-cache / page-cache writeback** | Class → write policy: shared-prefix = write-through to host (cheap to refetch/recompute); session = write-back (spill on pressure, reload on resume); one-shot = never spill. | Maps the taxonomy to a citable storage discipline |
| **Content-defined chunking + Merkle/content hashing** (HF XET CAS) | Key idle/spilled prefix blocks by content hash in the host-DRAM hub (generalizes SGLang's in-process token-ID radix tree). | **Optional**, MVP-deferred |

---

## 5. Research questions

- **RQ1 (co-management):** When VidMm can evict KV heaps under a shifting DXGI budget, what class-driven residency-priority assignment + re-planning protocol minimizes decode-stall-attributable-to-OS-eviction, and does it avoid double-paging / priority inversion?
- **RQ2 (roofline admission):** Can a working-set + bandwidth-roofline admission model that gates concurrent-decode count (never paging active KV) be formalized and shown to hold the system at the achievable goodput ceiling on PCIe-only Arc — and what is that ceiling vs the NVLink-C2C regime?
- **RQ3 (classes earn their keep):** Does a typed reuse-provenance class contract beat per-request TTL (Continuum) and per-block priority (KVBM) on the hostile target — and does **classes-ON vs classes-OFF** show the typing is load-bearing?
- **RQ4 (recompute vs refetch inversion):** On PCIe-only/no-P2P Arc, where is the per-block break-even between recomputing a prefix (compute-bound) and refetching from the host hub (bandwidth-bound), and how does a class-aware cost model exploiting it compare to datacenter refetch-always?
- **RQ5 (portability is real):** Does the same contract, behind one residency interface, drive sensible policy on **both** D3D12/VidMm **and** CUDA/Level-Zero — or does it secretly assume CUDA semantics?
- **RQ6 (honest telemetry value):** Do per-class miss-ratio curves + ghost-list regret signals let an operator provision HBM-vs-concurrency better than opaque hit-rate, and can decode stalls be cleanly attributed to VidMm budget-pressure?

---

## 6. Evaluation design

**Workloads:** ShareGPT + WildChat multi-turn (session spill/resume); Aliyun "KVCache-in-the-Wild" ATC'25 to-B/to-C split (real lifetime heterogeneity, not synthetic); agentic tool-call traces with long idle gaps (SWE-Bench / BFCL style); shared-system-prompt RAG (sink/tenured class); **adversarial co-tenancy** — a VRAM-hog foreground app forcing VidMm budget shrink mid-serving (the scenario no datacenter eval can produce; direct test of RQ1).

**Baselines:** on identical Arc hardware — "keep-resident + LRU/TTL spill of idle prefixes" straw-man (*if we can't beat this, we add nothing*); vLLM + PagedAttention (+ native OffloadingConnector); SGLang + RadixAttention/HiCache; Continuum per-request TTL. On a CUDA box — NVIDIA Dynamo KVBM (*expect a tie, not a win — the point is it doesn't lose*). Recompute-all / refetch-all endpoints to bound RQ4.

**Metrics:** goodput under SLO (primary); TTFT + per-token TBT at **P50 and P99**; **decode-stall-attributable-to-VidMm-eviction** (novel); achieved vs roofline-predicted concurrent-decode ceiling; HBM-hours + host-bytes-moved per request; per-class hit rate / miss-ratio curve / ghost-list recompute-avoided; **per-decode-step policy overhead in µs (must show <1%)**.

**Ablations (the spine):** **classes-ON vs classes-OFF** (highest-variance, must-run); VidMm-cooperative vs VidMm-naive; admission-control vs live-paging-of-active-KV; spill-idle-only vs spill-anything; recompute-vs-refetch cost model on/off; per-request-TTL vs typed-class TTL; **substrate swap** (D3D12/VidMm vs CUDA/Level-Zero).

---

## 7. Milestones + MVP

| Phase | Duration | Deliverable |
|---|---|---|
| **P0 — Roofline characterization + kill-gate (NO abstraction)** | 3–4 wk | Minimal measured decode harness (or instrumented llama.cpp + SYCL/Vulkan) on the 1–2× Arc Windows box: quantify (a) the HBM/PCIe cliff in practice, (b) decode-stall cost of pulling active KV over PCIe, (c) decode-stall from deliberately triggering VidMm eviction via a co-tenant VRAM hog, (d) recompute-vs-refetch break-even. **Early go/no-go.** |
| **P1 — VidMm co-management mechanism** | 4–6 wk | D3D12 residency backend (`MakeResident`/`Evict`/`SetResidencyPriority`/`QueryVideoMemoryInfo`) holding active KV resident, evicting idle KV to a pinned host hub, re-planning vs live budget; demonstrates double-paging avoidance under a forced co-tenant. (RQ1) |
| **P2 — Lifetime-class contract + admission control** | 4–5 wk | Reuse-provenance taxonomy as a Segcache-style per-class-segment contract → residency priority + write policy + admission; working-set + roofline admission controller. Enables classes-on/off + admission ablations. (RQ3) |
| **P3 — Telemetry plane + cost model** | 2–3 wk | Off-hot-path ghost-list regret, per-class reuse-distance/miss-ratio curves, decode-stall-attribution-to-VidMm; class-aware recompute-vs-refetch model; the <1% overhead measurement. (RQ4/RQ6) |
| **P4 — Portability backend (non-negotiable 2nd substrate)** | 3–4 wk | Same contract over CUDA-VMM (or Level-Zero) residency behind the shared interface + one vLLM/SGLang connector on CUDA. Produces the "ties incumbents on fast fabric, wins on Arc" result. (RQ5) |
| **P5 — Full eval, ablations, paper + artifact** | 4–6 wk | All workloads/baselines/metrics/ablations; adversarial co-tenancy; reproducible Docker/scripts artifact; paper. |

**MVP (smallest thing that defends the pivoted thesis):** P0 characterization + P1 VidMm co-management on a **single** Arc GPU with a host-DRAM hub and the class→priority mapping, evaluated with VidMm-cooperative-vs-naive and admission-vs-live-paging ablations under a forced co-tenant. Proves the two non-absorbable claims **without** depending on flaky multi-Arc P2P. Multi-GPU, the 2nd substrate, and engine integrations are *additive proof*, not prerequisites.

---

## 8. Kill criteria (front-loaded)

- **P0 bandwidth/stall gate:** if VidMm-eviction-induced decode stalls under realistic co-tenancy are negligible (drivers rarely evict a serving process's heaps; stalls <few % of TBT), the "two memory managers" problem isn't real on shipping drivers → drop the co-management wedge or abandon.
- **P0 headroom gate:** if idle/reusable KV is a tiny fraction of resident KV (almost everything resident is actively decoding), "spill idle only" has ~0 headroom → pivot to paused-session/agentic workloads, else abandon.
- **Classes-on/off gate (post-P2):** if typed classes don't beat per-request TTL / reuse-probability scoring by a robust margin → drop lifetime classes, narrow to co-management + admission (still a paper, smaller).
- **Portability gate (P4):** if the contract can't drive a 2nd substrate without leaking CUDA assumptions → drop "portable," retitle to single-platform characterization.
- **Platform-viability gate:** if neither vLLM-XPU multi-GPU nor a minimal custom/llama.cpp harness stabilizes on Arc/Windows within P0+P1 → single-Arc scope or abandon; do **not** paper over with simulation-only results.
- **Absorption gate:** if an incumbent ships WDDM/VidMm co-management OR published bandwidth-roofline admission on PCIe-only Arc before submission → pivot to the remaining open sub-problem (likely the recompute-vs-refetch inversion model) or stop.

---

## 9. Artifact + venue strategy

**Paper and OSS live on opposite sides of the absorption line.** The **paper's** claim (co-management model + anti-paging admission + cross-substrate portability) can't be merged away — it needs the VidMm substrate and the no-fabric regime. The **OSS** hedges adoption: the reusable, non-platform pieces (the lifetime-class telemetry; a roofline admission policy) ship as **upstream PRs** to vLLM/SGLang riding their existing connector seams — so "adoption" = *merged + cited*, not "install a new daemon" (which loses to native vLLM and kvcached). The **VidMm residency backend** ships as a standalone reference impl (the part no engine will absorb).

**Venues, in order of fit:**
1. **HotOS (next cycle)** — the position/early-result version: *"Don't Page Active KV: Co-managing Residency with the OS on Fabric-less GPUs."* De-risks the framing before the full build; it's where Symphony (the closest prior framing) appeared.
2. **OSDI / NSDI** — *iff* the artifact is built and the classes-on/off + VidMm-cooperative ablations land. Delete "OS-managed resource" from the contributions; lead with the VidMm/PCIe systems problem.
3. **ASPLOS / EuroSys** — strong fit for the hardware/OS-residency-mechanism angle (vAttention precedent) + the roofline characterization.
4. **MLSys** — if the result leans policy + telemetry + engine integration over OS-mechanism depth.
5. **USENIX ATC** — the measurement-forward fallback (where the Aliyun in-the-wild and HCache papers landed).

---

## 10. Hardware reality check (this is your box)

- The study found **vLLM-XPU GP-faults / engine-resets on dual Arc Pro B70** (reported vLLM issues #27408, #41663) — i.e. the flagship serving path is unstable *on your exact hardware*.
- **Intel archived `ipex-llm` (Jan 2026)** over security issues; SYCL backend reportedly ~1/3 theoretical bandwidth.
- **Intel + the vLLM community are enabling PCIe P2P on Arc Pro B-series (Nov 2025)** — but **Linux/Ubuntu-only**. This *erodes* the no-P2P moat on Linux while leaving **Windows/WDDM uniquely uncontested**.

**Implication:** Windows is simultaneously your **moat** (nobody else targets it) and your **hazard** (the builder-hostile platform). Mitigation is baked into the plan: the load-bearing contributions (VidMm co-management + admission model) live at the **D3D12 / Level-Zero residency layer** with a **minimal custom decode harness**, so they do **not** fate-share with flaky vLLM-XPU multi-GPU. Single-Arc + host-DRAM hub proves co-management even if multi-Arc P2P never stabilizes.

---

## Appendix A — Adversarial verdicts (all four: "reframe-needed")

- **Novelty Assassin:** four of five pillars already in production/peer-reviewed (KVBM/LMCache/HiCache/Continuum/vLLM-events); only WDDM/VidMm co-management + the typed-class unification survive.
- **Category-Error:** the OS/VM analogy is wrong (no cheap GPU fault path; decode is bandwidth- not capacity-bound; PagedAttention-style indirection already costs 20–40% and vAttention/ASPLOS'25 is *removing* it) — but a "bandwidth-roofline-aware KV residency planner coexisting with VidMm on PCIe-only Arc" is genuine.
- **Adoption/Wedge:** fatal as a standalone adopted layer (vLLM absorbs good ideas as PRs; kvcached already occupies the framing); survivable as a research characterization + upstream PRs + telemetry incumbents don't export.
- **OSDI/NSDI Reviewer 2:** broad framing fatal (Symphony/PTask own the framing; KVBM/CacheTTL/LCR own the pillars; **no artifact — `D:\work\infexp` is empty**); narrow "VidMm co-management + PCIe admission-control + lifetime-class contract, real prototype, classes-on/off ablation" is a survivable, novel systems paper.

## Appendix B — Key prior art to read first (verify all)

KVBM (docs.nvidia.com/dynamo/components/kvbm) · LMCache (arXiv 2510.09665) · Continuum/CacheTTL (arXiv 2511.02230, ICLR'26) · Symphony (arXiv 2510.25412, HotOS'25) · kvcached (github.com/ovg-project/kvcached) · vLLM OffloadingConnector (vllm.ai blog 2026-01-08) · vAttention (arXiv 2405.04437, ASPLOS'25) · "Rethinking Caching for LLM Serving" (arXiv 2508.18736) · LCR/LARU (arXiv 2509.20979) · Aliyun "KVCache in the Wild" (arXiv 2506.02634, ATC'25) · vLLM Intel Arc Pro B (vllm.ai blog 2025-11-11) · Segcache (NSDI'21) · AdaptSize (NSDI'17) · PTask (SOSP'11).
