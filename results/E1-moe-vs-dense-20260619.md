# Result — MoE vs dense decode/prefill (the bandwidth-architecture thesis) (2026-06-19)

*`llama-bench` (Vulkan b9279), Card B, single GPU, Q4. At equal ~32B total params: the 3B-active MoE vs a dense 32B — does the MoE stream fewer active params → faster decode? (The cost-model / north-star bandwidth premise, on the model-architecture axis.)*

| model | total / active params | prefill pp512 | decode tg128 |
|---|---|---|---|
| Qwen3-30B-A3B (MoE) | 30.5B / ~3B | **1500.6** | **130.3** |
| Qwen2.5-32B (dense) | 32.8B / 32.8B | 513.7 | 23.0 |
| **MoE advantage** | | **2.9×** | **5.7×** |

## Reading
- **Decode: MoE 5.7× faster** (130 vs 23). Decode is bandwidth-bound (stream active weights per token); MoE streams ~3B active vs dense's 32.8B (~11× ratio), realized as **5.7×** (MoE pays routing + shared-expert + same-attention overhead). **Strong confirmation of the active-params bandwidth thesis.**
- **Prefill: MoE 2.9× faster** — prefill is more compute-bound, so the active-param advantage is smaller but clearly present.
- **Empirically validates the MoE choice for this hardware:** on a bandwidth-starved B70, MoE is the bandwidth-efficient architecture — big-model quality at a fraction of the per-token streaming cost, exactly as the cost model and the project's MoE decision argued.
- **Caveat (honest):** different model families (Qwen3-MoE vs Qwen2.5-dense), so attention/training differ — not a perfectly-controlled same-base MoE-vs-dense. But the dominant driver of the decode gap is the active-param count, so the ~5.7× is attributable primarily to MoE sparsity.

## Manifest
llama-bench b9279 · Card B (`GGML_VK_VISIBLE_DEVICES=1`) · `-p 512 -n 128 -r 3` · Qwen3-30B-A3B-Q4 (18.5 GiB) vs Qwen2.5-32B-Q4 (18.5 GiB) · driver 32.0.101.8826.
