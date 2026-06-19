# Result — E1 (partial): prefill + decode rates; R1 confirmed (2026-06-19)

*Real measurement via prebuilt llama.cpp Vulkan (b9279, 47c0eda9d) on **Card B** (single B70, `GGML_VK_VISIBLE_DEVICES=1`), **Qwen3-30B-A3B-Q4_K_M** (17.28 GiB, fits the 31.12 GiB budget). No install, no fabrication. Run by Claude, authorized by operator. Measures cost-model constants + partially tests R1; **full E1 still needs the transfer-bench (`B_pcie`) + dequant-bench (`B_dq`)**, which require custom code.*

## Measured (single card B70, Vulkan, f16 KV)
| test | t/s | note |
|---|---|---|
| prefill `pp512` | **1500.6 ± 219.3** | = `R_prefill` |
| decode `tg128` | **130.3 ± 1.0** | bandwidth-bound; very tight variance |

Device: Intel Arc Pro B70, Vulkan 1.4.348, fp16:1, bf16:0, warp 32, shared-mem 49152, KHR_coopmat.

## Confirms cost-model R1 (committed `1118d0c`, BEFORE this data)
recompute/token = `1/R_prefill` = **667 µs/tok**; refetch-raw/token (FP8 KV, PCIe x8 ~13 GB/s, 49 KB/tok) ≈ **3.8 µs/tok** → **refetch ≈ 176× cheaper.**
→ **R1 holds by a large margin:** refetch ≫ recompute; recompute is a *capacity* tool, not bus-saving. (Refetch side still uses the x8 *estimate*; the measured transfer-bench will tighten it, but a 176× margin is robust to that.)

## Corrects a prior anomaly
Prior `b70tools/docs/findings-dual-b70-qwen30b-moe` reported prefill **30.1** / decode **81.7** t/s (dual). Fresh single-card llama-bench: **1500 / 130** — prefill **~50× higher** → the prior "30.1" was anomalous (different metric/config). **Use `R_prefill ≈ 1500 t/s`.** Decode single-card (130) > dual (81.7) re-confirms "single-card beats dual-split for a fitting model."

## Manifest
llama-bench b9279 (47c0eda9d) · `GGML_VK_VISIBLE_DEVICES=1` (Card B, BDF 10:00.0) · Qwen3-30B-A3B-Q4_K_M 17.28 GiB · `-ngl 99 -p 512 -n 128 -r 3` · driver 32.0.101.8826 · Win10 19045.

## Still `[MEASURE]` (need custom code / not in prebuilt llama.cpp)
`B_pcie` (host↔VRAM transfer bench) · `B_dq` (dequant-kernel throughput, isolated + contended) · the card→card path. These gate cost-model R2/R3 — the compression bet — and remain the part that needs a toolchain.
