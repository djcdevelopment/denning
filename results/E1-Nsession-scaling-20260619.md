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
