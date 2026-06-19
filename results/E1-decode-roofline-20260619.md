# Result — Decode roofline vs context (2026-06-19)

*Real `llama-bench` (Vulkan b9279) on Card B, Qwen3-30B-A3B-Q4_K_M, single GPU. The bandwidth-bound decode roofline — the empirical foundation of H2′ / admission control. Quantifies the operator's "small snappy, huge slow."*

## Measured (tg64 @ depth)
| context depth | decode t/s | vs empty | t/token |
|---|---|---|---|
| 0 | **132.8 ± 0.3** | 1.00× | 7.5 ms |
| 8,192 | **74.3 ± 10.1** | 0.56× | 13.5 ms |
| 32,768 | **37.0 ± 1.4** | 0.28× | 27.1 ms |

## Reading
- Decode rate **~halves every ~16 K of context** (132 → 74 → 37) — **3.6× slower at 32 K than empty.** Per-decode-step ≈ 7.5 ms base + ~0.6 µs × context-tokens → **~linear in resident KV** (each step streams the whole KV cache — the bandwidth-bound roofline).
- **This is the admission thesis's floor:** to stay "snappy" (meet a TBT SLO) you must cap resident KV / concurrent sessions **left of this slope** → the knee `N*` (cost-model §2). The operator's "huge = slow" is the cliff admission-control exists to keep you off.
- ~linear to 32 K here; the prior-work "5× cliff @ ~25 K" may be a longer-context / config effect — extend the sweep to 64 K / 128 K once the spill edge is watched (safe with the watchdog).

## Manifest
llama-bench b9279 · Card B (`GGML_VK_VISIBLE_DEVICES=1`) · Qwen3-30B-A3B-Q4_K_M · `-p 0 -n 64 -d 0,8192,32768 -r 2` · driver 32.0.101.8826.
