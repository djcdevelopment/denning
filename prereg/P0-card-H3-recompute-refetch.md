# Prediction Card — P0 / H3: Recompute-vs-refetch break-even on B70

`[prereg tag: prereg-P0 — NOT YET TAGGED; finalize numbers + advisor ack @ G0 first]`

- **Committed:** `<YYYY-MM-DD on tag>`  **Advisor ack:** `<date | pending>`
- **Maps to:** H3 / wedge W2 / RQ4. Second leg of the **P0 two-sided honesty test**.

## Hypothesis (falsifiable, one sentence)
There exists a prefix length L* below which on-GPU recompute of a prefix's KV beats refetching that KV over PCIe; we predict L* is small on B70 (recompute *loses* to DRAM-refetch across practical prefixes).

## Mechanism / back-of-envelope `[DRAFT — recompute constants from MEASURED kernel throughput before tagging]`
Per prefix-token: recompute ≈ `2·active_params / FLOP_rate`; refetch ≈ `KV_bytes_per_token / PCIe_BW`.
For Qwen3-Coder-30B-A3B (~3.3B active; ~49 KB/tok FP8 KV) on B70 (assume ~100 TFLOPS *effective*; PCIe ~28 GB/s → host DRAM):
- recompute ≈ ~66 µs/tok; DRAM-refetch ≈ ~1.75 µs/tok → **~38× favoring refetch.**
*(The effective FLOP rate is the dominant uncertainty — immature SYCL/Vulkan kernels may run ~1/3 of peak. Measure it; don't assume.)*

## Quantitative prediction `[DRAFT]`
- **L* ≈ 0 vs DRAM-refetch** — recompute loses across the practical prefix range; "spend FLOPs to dodge the bus" **inverts** on bandwidth-rich/FLOP-modest B70.
- Recompute's only plausible win: vs **NVMe-refetch** (~3–7 GB/s) or when KV was never stored. Predict a finite L*_nvme there.
- **Prior: ~60%** that recompute loses to DRAM-refetch.

## Measurement protocol (exact)
- **Box / build / model:** as in the H1 card (pinned hashes recorded in manifest).
- **Procedure:** for prefix lengths L ∈ {64, 256, 1k, 4k, 16k, 64k}: (a) measure on-GPU prefill/recompute wall-time for the prefix's KV; (b) measure host-DRAM→VRAM refetch wall-time for the same KV (FP8 and FP16); (c) measure NVMe→VRAM refetch wall-time. Plot the three curves; read off L*_dram and L*_nvme. **First measure the effective prefill FLOP rate and the achieved PCIe + NVMe bandwidths** on the frozen build (these are the model constants).
- **N runs:** ≥5 per L; report P50 & P99.

## Analysis plan
Three time-vs-L curves with CIs; the crossover points L*_dram, L*_nvme; the measured effective FLOP rate and bandwidths (so the back-of-envelope can be checked against reality and the prediction honestly scored).

## Pass gate
L*_dram > a useful threshold → recompute is a real reclaim path; "spend FLOPs to dodge the bus" holds; keep it load-bearing.

## Kill / "predicted negative" gate
L*_dram ≈ 0 (predicted) → recompute loses; **report as the bounded negative result** (it reshapes the design toward keep-resident + refetch). This does NOT kill the program — H2 (roofline admission) and W3 (RAM<VRAM) carry it.

## Pre-committed framing
Either outcome is publishable. A confirmed inversion is a surprising positive; the predicted negative is "the datacenter recompute/refetch answer does not invert on commodity bandwidth-rich/FLOP-modest silicon — here is the measured break-even," which is exactly the kind of regime-mapping result that motivated the project.
