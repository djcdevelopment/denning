# Block-grained KV arena — design & staged build spec

*The infrastructure that would let denning swap KV at **block granularity** on real inference — turning the validated policies (H4 lifetime classes, I-4a admission) into actual KV management instead of a router/sim. Written 2026-06-19, after the H4 results showed block-grained eviction is worth it but isn't realizable on a contiguous prefix cache.*

> **Status: design only.** S1 is buildable now on existing llama.cpp primitives; S2/S3 are escalating engineering. Bounds-first: do not start S2 until S1 proves the value, or S3 until S2 does.

---

## 1. The problem

We want to **evict and restore individual KV blocks by lifetime class, under VRAM pressure, on real inference.** Today we can't:

- llama.cpp (like most runtimes by default) stores a sequence's KV as one **contiguous** run, and the attention kernel reads it as a contiguous range.
- So you can keep a **prefix** (cache reuse) or drop a **suffix** (truncate), but you **cannot punch a hole** — evict the DOC block in the middle while keeping SYSTEM before it and TURN after it.

That contiguity is exactly why [`H4-blockgrained`](../results/H4-blockgrained-20260619.md) had to be a simulation, and why the [on-rig H4](../results/H4-arena-onrig-20260619.md) is conversation-grained (whole-slot eviction, re-prefill on miss).

**What block-grained swap would unlock:** the policies are already measured. This is the substrate that makes them executable on real KV.

---

## 2. The unlock: a block table (paged KV)

Chop each sequence's KV into fixed-size **blocks** (e.g. 16–64 tokens). Store each block in a non-contiguous physical **page** in a fixed VRAM pool. Keep a per-sequence map `logical block → physical page | swapped-out(host/NVMe location)`. Now any block is individually addressable, evictable, and swappable — denning's arena made literal.

```
        ┌─────────────────────────── model runtime (llama.cpp / Arc / Vulkan) ───────────────────────────┐
        │   decode step t  ──needs──▶  attention over blocks {b0..bk} of seq s                            │
        └───────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                         │ block ids
                          ┌──────────────────────────────▼──────────────────────────────┐
                          │  (2) BLOCK-AWARE ATTENTION                                    │
                          │   gather K/V across the block table → run attention           │
                          │   route a: paged-attention shader  |  route b: gather-then-attend │
                          └──────────────────────────────┬──────────────────────────────┘
                                                         │ resolve block → page
   ┌─────────────────────────────────┐   ┌───────────────▼───────────────┐   ┌─────────────────────────────┐
   │ (4) LIFETIME-CLASS CONTROLLER    │──▶│ (1) PAGED KV STORE            │──▶│ (3) SWAP MANAGER            │
   │  evict TURN→DOC→SYSTEM (H4)      │   │  page pool (fixed VRAM)       │   │  VRAM ⇄ host RAM ⇄ NVMe      │
   │  admit ≤ live VidMm budget (I-4a)│   │  per-seq block tables         │   │  evict=copy out; miss=copy in│
   │  reads (5) provenance tags       │   │  free-list allocator          │   │  optional compress (R2)     │
   └─────────────────────────────────┘   └───────────────────────────────┘   └─────────────────────────────┘
                  ▲                                                                          │
                  └────────── live budget (QueryVideoMemoryInfo) + b70tools signals ─────────┘
```

### The 5 components
1. **Paged KV store** — fixed VRAM page pool + per-sequence block tables + free-list allocator. *The arena.*
2. **Block-aware attention** — the kernel must gather K/V across the block table instead of a contiguous buffer. **The hard piece.** Two routes:
   - **(a) paged-attention shader** for Vulkan/Arc — fast, real, and nobody has written one for this stack.
   - **(b) gather-then-attend** — copy the needed blocks into a contiguous scratch, run llama.cpp's existing attention kernel, discard the scratch. Slower (an extra gather copy per step) but reuses the working kernel; the tractable first cut.
3. **Swap manager** — DMA blocks VRAM ⇄ host RAM ⇄ NVMe. Evict = copy page out, free it, mark the table entry swapped-out; restore-on-miss = copy back into a free page. *This is the R1/R2 refetch path, literally.* Optional compress-on-evict (quantize KV over the bus, R2).
4. **Lifetime-class controller** — which block to evict under pressure, and whether to admit new work. **Already built + validated** ([H4](../results/H4-arena-onrig-20260619.md) + [I-4a](../results/I4a-admission-controller-20260619.md)): evict TURN→DOC→SYSTEM by provenance; admit beneath the live VidMm budget.
5. **Provenance tagging** — tag each block's lifetime class at creation (system-prompt KV vs retrieved-doc KV vs turn KV). Cheap — metadata the controller reads.

---

## 3. The llama.cpp seams (b9279)

You extend llama.cpp's KV cache, because it is the only working Arc/Windows/Vulkan path (vLLM, which has paged KV, GP-faults on this box — #41663/#27408). Its cache is **cell-based with sequence ids** and already exposes the right shapes of operation (exact symbol names track the version):

| Seam | What it gives | Use |
|---|---|---|
| `llama_kv_self_seq_rm(ctx, seq, p0, p1)` | remove a position range | drop/evict a span |
| `llama_kv_self_seq_cp` | copy a sequence's KV to another seq id | shared-prefix fork / COW |
| `llama_kv_self_seq_add` (position shift) | re-apply RoPE for a Δposition | restore a block at a new position |
| `llama_state_seq_save_file` / `load_file` | **save/restore a sequence's KV to/from a file** | the real swap primitive (S1) |
| server `/slots/{id}?action=save\|restore` | the above over HTTP | S1 with zero C++ |

**What's reusable:** the cell store, the seq-level ops, and (critically) state save/restore.
**What's new:** the block table + page allocator (1), the gather/paged attention (2), and the swap-manager bookkeeping (3). Block-grained eviction (sub-sequence, arbitrary blocks) is **not** in llama.cpp — that's the build.

---

## 4. The cost model *is* the spec (already measured)

Every mechanism here maps to a result we've already measured — so the design is parameterised by real constants, not guesses:

| Mechanism in this doc | denning result | measured value |
|---|---|---|
| Swap-out/in = **refetch** (vs recompute) | **R1** | refetch ~176× cheaper than recompute; `B_pcie` ≈ 13.9 GB/s |
| **Compress-on-swap** over the bus | **R2** | `B_dq` 168/94 (int8/int4); wins iff `B_dq > B_pcie·r/(r−1)` |
| Block size ↔ transfer efficiency | **R3** | bigger transfers win; card→card 6.48 GB/s |
| Evict by lifetime class | **H4** | classes beat LRU/TTL +32% on-rig (+365% block-grained sim) |
| Admit beneath the budget | **I-4a / I-4c** | `QueryVideoMemoryInfo.Budget` predicts the cliff 5/5; live |
| Stall on a needed-but-swapped block | **H1 / roofline** | a big re-prefill is ~2.8 s; a refetch would be PCIe-bound instead |

The headline implication: **switching the miss path from re-prefill (recompute) to swap-restore (refetch) is an R1 win of ~176×** — and that's available at sequence granularity *today* (S1).

---

## 5. Staged build (bounds-first)

### S1 — sequence-grained swap (NOW, no kernel work) — *the gate*
- **Build:** extend [`h4_arena.py`](../experiments/h4_arena.py): on eviction, `action=save` the conversation's KV to host RAM (ramdisk) / NVMe (D:) instead of discarding; on a miss, `action=restore` instead of re-prefilling.
- **Measures:** restore time (refetch) vs re-prefill time (recompute) on **real KV bytes** → R1, directly. Save-file size → the real KV footprint per token. Host-tier vs NVMe-tier restore → R3-flavoured. Arena goodput with cheap-refetch misses (should beat the re-prefill arena by a lot).
- **Gate:** is restore ≪ re-prefill on this rig (R1 holds on real KV)? Is save/restore reliable across the `-np` slots? If yes → the swap path is worth paging.
- **Risk:** low. Pure orchestration over existing endpoints.

### S2 — paged KV + gather-then-attend (real block eviction, slow kernel)
- **Build:** components 1 + 3 in ggml; route (b) for component 2 (gather needed blocks → contiguous scratch → existing attention). Controller (4) drives per-block eviction.
- **Measures:** real block-grained H4 (the sim made real); the gather overhead per decode step; the block-size vs PCIe-efficiency curve (R3).
- **Gate:** does block-grained beat sequence-grained by enough to justify a custom kernel? Is the gather overhead tolerable?
- **Risk:** medium-high. ggml KV-cache surgery + position/RoPE correctness.

### S3 — paged-attention kernel for Vulkan/Arc (efficient block-grained)
- **Build:** route (a) — a real block-table-gather attention compute shader. Replaces the gather-then-attend scratch path.
- **Gate:** kernel is numerically identical to the contiguous path and fast enough to beat S2's gather overhead.
- **Risk:** high. **This is the "P1 from-scratch" risk, concrete.** No existing paged-attention for this stack.

---

## 6. Hard parts & open decisions

**Hard parts (eyes open):**
- **The paged-attention kernel (S3)** — the real lift; no prior art on Vulkan/Arc.
- **Positions / RoPE** — K vectors are stored post-RoPE (rotated for their original positions). A restored block is valid only at those positions, or you re-apply a Δ (`seq_add`). Block reuse across positions is fiddly and must be exactly correct.
- **Block size vs PCIe efficiency** — small blocks evict surgically but mean many tiny DMAs (inefficient, R3). Sweet spot is empirical (sweep in S2).
- **The decode stall** — if a block needed *this* step is swapped out, you must restore it before attention (a synchronous stall). The controller's whole job is keeping hot blocks resident so this is rare; prefetch (async restore of soon-needed blocks) is the mitigation.
- **Correctness** — attention output must be bit-comparable to the contiguous path (a test harness gating every stage).

**Open decisions (set before S2):**
- Block size (16 / 32 / 64 tokens?).
- Swap tier: host RAM (small — RAM<VRAM here) vs NVMe (D:, 1.5 TB) vs both (host hot, NVMe cold).
- Compress-on-swap (R2): off for S1/S2, on as an S2.5 lever once the bound is known.
- Sync restore vs async prefetch.

---

## 7. Scope & non-goals
- **In scope:** the KV residency/swap control plane on the one card it matters for, parameterised by the measured cost model.
- **Non-goals (for now):** the asymmetric two-card feed (I-5, gated on the card→card number), frontier-model offload, a portable cross-runtime arena. Deferred per `cost-model.md` §7.
- **Honesty:** S1 is real and small; S2/S3 are genuine engineering with escalating risk. The validated policies don't depend on S3 — they're already measured. This doc exists so that if/when the bound says block-grained is worth it, the build is specified rather than improvised.

---

*Feeds: `cost-model.md` (the constants), `build-roadmap.md` (I-3 arena, now concrete), the H4/I-4 results (the validated policies this would execute).*
