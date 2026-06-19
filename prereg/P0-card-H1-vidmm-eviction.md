# Prediction Card — P0 / H1: Does VidMm involuntarily evict a foreground serving process?

`[prereg tag: prereg-P0 — NOT YET TAGGED; finalize numbers + advisor ack @ G0 first]`

- **Committed:** `<YYYY-MM-DD on tag>`  **Advisor ack:** `<date | pending>`
- **Maps to:** H1 / wedge W1 / RQ1. One leg of the **P0 two-sided honesty test**.

## Hypothesis (falsifiable, one sentence)
Under an adversarial desktop VRAM-hog that drives the DXGI budget below the resident KV demand of N concurrent agent sessions on one B70, VidMm involuntarily demotes ≥1 of the serving process's KV heaps, causing a measurable decode-stall.

## Mechanism
WDDM/VidMm virtualizes VRAM; `QueryVideoMemoryInfo` budget shrinks under contention; over-budget processes can be demoted to shared/system memory over PCIe (the bandwidth cliff). Open question: does it demote a *foreground compute* process, or protect it?

## Quantitative prediction `[DRAFT — operator sets, advisor reviews]`
- Involuntary demotion of ≥1 KV heap within **~2 s** of budget < resident demand.
- TBT on affected sessions spikes **≥2× baseline**; decode-stall **≥10%** of a 10 s window.
- **Prior confidence: ~50%** (genuinely uncertain — Microsoft documents cooperative offer/reclaim).

## Measurement protocol (exact)
- **Box:** dual B70, Windows 10, display on iGPU (headless compute card) if possible; else note the desktop card.
- **Build (pinned):** llama.cpp commit `<hash>`, SYCL/Vulkan backend `<build hash>`, `--split-mode layer`. Record all in the result manifest.
- **Model:** Qwen3-Coder-30B-A3B `<file hash>`, INT4 weights, FP8 KV, 128K context cap.
- **Procedure:** spin up N concurrent/paused agent KV sessions on **one** 32 GB card until resident KV demand approaches the DXGI budget (log `CurrentUsage` vs `Budget`). Then launch an adversarial fullscreen/VRAM-hog app. Instrument: `QueryVideoMemoryInfo` budget/usage timeline; per-session TBT; any residency demotion events; correlate stalls with budget-shrink events.
- **N runs:** ≥5; vary N (sessions) and the VRAM-hog size.
- **Seeds:** fixed `<seed>`.

## Analysis plan
Report budget/usage timeline; demotion event count + latency; TBT P50 & P99 before/during/after the hog; **decode-stall-attributable-to-VidMm** (stall time correlated with budget-pressure events). CIs over runs. Compare against the **measured noise floor** (TBT variance on the frozen build with no hog).

## Pass gate
Measurable involuntary demotion + stall ≥ threshold → **W1 confirmed; proceed to S2** (build the D3D12 residency backend; test cooperative-vs-naive).

## Kill / pivot gate
VidMm protects the foreground process / stall < a few % → **W1 premise false on shipping drivers.** Demote co-management to a tested secondary result; re-center the program on W2 (roofline admission) + W3 (RAM<VRAM). Do **not** write D3D12 residency-backend code.

## Pre-committed pivot
On refutation, the headline becomes roofline-admission + the RAM<VRAM inversion; the H1 result ships as an honest "VidMm does not adversarially evict foreground compute on Win10/Arc — here's the evidence" finding (still useful to the field).
