# Prediction Card — E1: Materialization-Cost Crossover

`[prereg tag: prereg-E1 — NOT YET TAGGED]`
**STATUS: DRAFT — predictions derived from `../docs/cost-model.md` as a STARTING POINT. The operator finalizes the priors/thresholds and the advisor ratifies at G0; this is tagged (binding) only then. Not a result; not the operator's committed prior until tagged.**

- **Committed:** `<YYYY-MM-DD on tag>`  **Advisor ack:** `<date | pending>`
- **Maps to:** E1 / completes H3′ / tests cost-model Results R1–R3 + the scheduling-dependence / wedge W2. The model-free physics de-risk; gates the compression idea, the asymmetric feed, and the "spend FLOPs to dodge the bus" principle.

## Hypothesis (falsifiable)
The cost of *materializing* a KV block on the compute card follows the cost model: refetch dominates recompute on time (R1); compression-over-the-bus wins iff the **contended** dequant throughput clears the threshold (R2); card→card is a worse path than host→VRAM (R3) — and the contended `B_dq` is **scheduling-dependent**, recoverable by engine-separated scheduling.

## Quantitative predictions `[DRAFT — operator to own/adjust at G0]`
- **P-R1 (recompute vs refetch):** per-token refetch ≈ `k/B_pcie` ≈ **3.5 µs/tok** (FP8 KV, PCIe x8); recompute ≈ `1/R_prefill` ≫ that even at generous prefill rates. **Predict recompute essentially never beats refetch on time** (crossover `L*` ≈ a handful of tokens); recompute's role is *capacity* (don't store), not speed. **Prior ~75%.**
- **P-R2 (the make-or-break):** isolated `B_dq` (INT4/FP8 bit-unpack) ≫ threshold (`B_pcie·r/(r−1)` ≈ **17 GB/s INT4, 26 GB/s FP8**) → compression wins *isolated*. **Under decode contention:** predict that **with engine-separated scheduling** (copy-engine transfer + compute-engine decode/dequant), contended `B_dq` *stays above threshold* → compression still wins; with **naive same-queue** scheduling or heavy/learned codecs it drops below → loses. **Prior ~55%** that cheap-scheme + good-scheduling wins under load. *(This single number decides the compression/asymmetric-feed/spend-FLOPs family.)*
- **P-R3 (card→card):** effective card→card BW ≈ **≤ ½ `B_pcie`** (~6–7 GB/s, host-bounced; no P2P on Windows). **Prior ~70%.**
- **P-sched (scheduling-dependence):** engine-separated contended `B_dq` exceeds same-queue contended `B_dq` by ≥ ~2×. **Prior ~60%.**

## Measurement protocol (exact)
- **Build (pinned/frozen):** llama.cpp/SYCL+Vulkan build hash, driver, model hash — per `../REPRODUCE.md`. **Engine = SYCL and Vulkan as SEPARATE panels, never differenced.**
- **Primitives:** (1) PCIe-x8 transfer GB/s vs buffer size {64 KB … 256 MB} — **sweep down to real per-block KV sizes; report the latency-dominated small-block regime + the fixed launch term separately.** (2) dequant-kernel output GB/s per scheme {INT4→FP16, FP8→FP16, low-rank}. (3) prefill/recompute rate (tokens/s). (4) **card→card** effective BW.
- **Two fidelity levels:** isolated → **under concurrent decode load (the headline).** Record per-engine util (b70tools `pdh_gpu_engine`: 3D/compute/copy/video) so overlap-vs-serialization is *observed*.
- **Scheduling axis:** same-queue vs separate-queue; copy-engine-transfer vs compute-engine-transfer; HAGS on/off.
- **Fidelity gate (lossy schemes):** reconstruction error of dequantized KV vs FP16 original (per-head relative-L2 / cosine) ≤ `<ε [set at G0]` — compression timing is only valid if the KV is faithful.
- **Stats:** N ≥ 5 per cell; report **P50 & P99 + the measured noise floor on the frozen build**; raise N per the power/MDE rule (G0).

## Analysis / figures
The crossover scatterplot (materialize-time vs block size, three series), **isolated panel + contended panel**; the measured constants (the `[MEASURE]` set → values); predicted-vs-actual table vs P-R1/R2/R3/sched; the per-engine-util traces showing overlap.

## Pass gate
Contended `B_dq` > threshold under some realizable schedule (P-R2 holds) → the compression/spend-FLOPs family is alive; proceed (I-3/I-4).

## Kill / pre-committed pivot (decided NOW)
If contended `B_dq` < threshold for **all** schedules and schemes → "spend FLOPs to dodge the bus," compression-over-the-bus, and the asymmetric feed all collapse → **report the bounded negative result** ("the trade does not survive contention on FLOP-modest commodity silicon — here is the break-even and why") and re-center on admission control (H2′) + co-residency (H1) with raw-refetch + keep-resident. *Either outcome is publishable.*

## Safety
Bounded buffers, no adversarial allocator → no VRAM-cascade risk; runs attended in an afternoon once the watchdog (I-1) is armed. Still gated behind G0 + I-1 per the roadmap.
