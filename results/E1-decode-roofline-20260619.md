# Result — Decode roofline vs context, to 64K (2026-06-19)

> ℹ️ **Status (red-team review, 2026-06-21): real data, but reframe + re-measure.** A
> benchmark-strategy red team mistook this for the *broken battlemage 70B `-c` files* and
> called it "retracted-grade" — that was **wrong**: this is a genuine `-d`-depth `llama-bench`
> run on the 30B model (see Manifest). BUT two real caveats: (1) it is only **`-r 2`** —
> thin; re-measure at **r≥5**, add a **q8-KV arm**, persist raw UTF-8 JSONL. (2) The cliff is
> **MOTIVATION (the admission floor), not a denning contribution** — a control plane cannot
> make a decode step faster than the Vulkan kernel allows, so never headline "denning fixes
> the decode cliff." The real long-context wins are capacity (KV vs the OS budget) + prefill/
> TTFT. See [`../docs/benchmark-strategy.md`](../docs/benchmark-strategy.md) §2.3.

*`llama-bench` (Vulkan b9279), Card B, Qwen3-30B-A3B-Q4_K_M, single GPU, tg64 @ depth (two runs combined). The bandwidth-bound decode roofline **and the long-context cliff** — the H2′ admission floor, and the operator's "small snappy, huge slow," quantified.*

## Measured (tg64 @ depth)
| context | decode t/s | vs empty | t/token |
|---|---|---|---|
| 0 | **132.8** | 1.00× | 7.5 ms |
| 8,192 | 74.3 | 0.56× | 13.5 ms |
| 16,384 | 58.2 | 0.44× | 17.2 ms |
| 32,768 | 38.0 | 0.29× | 26.3 ms |
| 65,536 | **11.5** | **0.087×** | 87.0 ms |

## Reading — the cliff is real
- **~Linear to 32K** (~0.6 µs added per context-token per decode step), then a **superlinear collapse**: **32K→64K is a 3.3× drop for 2× context** (38 → 11.5 t/s; per-ctx-token slope jumps to ~1.85 µs). **64K decode = 11.5× slower than empty.**
- This is the operator's "huge = slow" AND the prior-work **Vulkan attention-kernel cliff** (SYCL was ~3.5× better at 25K) → the cliff is partly a Vulkan-kernel artifact; **engine choice shifts it** (the SYCL-vs-Vulkan first-class variable).
- **Admission implication:** the controller must keep sessions **left of the cliff** (~≤32K here) to stay snappy. The cliff is exactly where admission control earns its keep — cap context/concurrency before the superlinear collapse. Combined with the N-session curve: **pack many *small*-context sessions; the roofline + cliff bite as context grows** (so `N*` shrinks with context — cost-model §2).

## Manifest
llama-bench b9279 · Card B (`GGML_VK_VISIBLE_DEVICES=1`) · `-p 0 -n 64 -d {0,8192,16384,32768,65536} -r 2` · f16 KV · driver 32.0.101.8826. *(64K KV ~6.3 GB fits; 128K skipped — spill edge, needs the safing watchdog first.)*
