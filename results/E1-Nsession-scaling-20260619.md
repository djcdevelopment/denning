# Result — N-session decode scaling (H2′ admission curve) (2026-06-19)

*`llama-batched-bench` (b9279), Card B, Qwen3-30B-A3B-Q4_K_M, npp 512 / ntg 128, parallel 1/2/4/8. The H2′ admission/roofline data: how throughput scales with concurrent sessions (one model, N KV caches).*

| parallel B | decode S_TG t/s (aggregate) | per-session | prefill S_PP t/s | N_KV |
|---|---|---|---|---|
| 1 | 60.9 | 60.9 | 265 | 640 |
| 2 | 80.6 | 40.3 | 594 | 1280 |
| 4 | 97.4 | 24.3 | 875 | 2560 |
| 8 | **109.9** | 13.7 | **894** | 5120 |

## Reading
- **Aggregate decode rises sublinearly and is still climbing at B=8** (60.9 → 110, 1.8×) → the bandwidth-roofline knee `N*` is **not reached by 8** at this small context (640 KV). Per-session decode falls (60.9 → 13.7) but aggregate gains → admission can profitably **pack many small-context sessions** (the snappy regime).
- **Prefill plateaus ~B=4** (875 → 894) — prefill is compute-bound, knee ≈ 4.
- This is **cost-model §2 in data:** `N* = min(bandwidth, commit)`, context-dependent. Small context → `N*` > 8; large context (bigger KV/session) → the roofline bites sooner, fewer sessions fit. Confirms the duty-cycle insight: low-context = low-duty = pack many; the admission controller trades **concurrency × context** against the roofline (and commit).
- *Methodology note:* batched-bench B=1 S_TG (60.9) differs from llama-bench tg128 (130) — different harness accounting; use **within-tool scaling**, not cross-tool absolutes.

## Next
**Dequant-under-N-decode** — does B_dq drop as the N-session duty cycle rises? — closes the R2-contention loop at the realistic high-duty end. And extend `N*` to larger context (where the roofline bites sooner).

## Manifest
llama-batched-bench b9279 · Card B (`GGML_VK_VISIBLE_DEVICES=1`) · `-npp 512 -ntg 128 -npl 1,2,4,8` · driver 32.0.101.8826.

## Extended sweep (1→32) + the noise reality
| B | decode S_TG | prefill S_PP |
|---|---|---|
| 1 | 76.0 | 572 |
| 4 | 113.8 | 839 |
| 8 | **145.6** | 892 |
| 16 | 85.4 | 896 |
| 32 | 131.0 | 896 |

**Decode peaks ~B=8, then goes non-monotonic** (85 @16, 131 @32). **Run-to-run variance is large:** this sweep's B=1=76 / B=8=146 vs the earlier sweep's 61 / 110 — a **~20–30% swing between identical runs**. So:
- **`N*` ≈ B 8** at this small context (aggregate decode peaks there), but the exact knee is **obscured by substrate noise** — pinning it needs averaged runs + a noise floor (Uncle's power/MDE discipline, **validated empirically here**).
- Prefill plateaus cleanly at **~896 t/s** for B ≥ 8 (compute-bound).
- **Honest:** these single-run batched-bench numbers are noisy — treat the *shape* (rise to ~8, prefill plateau) as the signal, not the absolute t/s. The red-team/Uncle substrate-noise concern is real and measured.
