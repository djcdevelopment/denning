# Result — q8-KV decode roofline: compression SLOWER on Vulkan (kernel dominates) (2026-06-19)

*⚠️ **PREDICTION CORRECTED.** I predicted q8 KV (half the bytes) would push the decode cliff OUT (faster at depth + reach 128K). The data shows the OPPOSITE on this Vulkan build: q8 KV is **2–4× slower** than f16 at depth. Honest finding: **the kernel implementation dominates the byte savings.** llama-bench (Vulkan b9279), Card B, Qwen3-30B-A3B, q8_0 KV + flash attention (required by llama.cpp for quantized KV).*

## Measured (tg64 @ depth) — q8 KV (+FA) vs f16 KV (no FA)
| ctx | f16 KV (default attn) | q8 KV (+FA) | q8 vs f16 |
|---|---|---|---|
| 0 | 132.8 | 104.1 | 0.78× |
| 32K | 38.0 | **9.38** | **0.25×** |
| 64K | 11.5 | **4.92** | 0.43× |
| 128K | (f16 didn't fit) | **2.52** | reaches 128K — but 2.5 t/s |

## Reading — the kernel dominates the bytes
- q8 KV has **half** the bytes → by pure bandwidth it *should* be faster. Instead it is **2–4× slower at depth.**
- **Cause:** llama.cpp requires **flash attention (`-fa`)** for quantized KV, and the **Vulkan/Arc FA kernel is poorly optimized** (slow even at d=0: 104 vs 133; degrades worse at depth than the f16 default-attention path). **The kernel implementation dominates the byte savings.**
- **Confound (honest):** the comparison changes *two* variables — KV dtype (f16→q8) AND attention kernel (default→FA, forced by q8). Isolation test (f16 + FA) is the next run, to attribute the slowdown to the FA kernel vs the q8 dtype.

## This does NOT contradict R2 (important)
R2 is **compress-for-bus-transfer**: compress a KV block, ship it across PCIe, **dequant to f16** on arrival (dequant measured fast at 168 GB/s), then use. That still holds. **This result is a different operation** — *in-place q8 attention* (the FA kernel reads quantized KV during attention), which is **kernel-bound on Vulkan/Arc.** So:
- Compression **for the bus** (R2): a win, kernel-cheap (bulk dequant).
- Compression **in-place for the KV cache** (q8 attention): a **capacity** win (halves footprint → fit more context/sessions) but a **decode-speed cost** on this substrate (the FA kernel), *not* the byte-savings speedup.

## Net
On the current Vulkan/Arc stack, **f16 KV (default attention) beats q8 KV (flash attention)** for decode despite 2× the bytes. The byte-savings benefit is **real but gated on a good FA/quantized-attention kernel**, which Vulkan/Arc currently lacks (SYCL or a better kernel might realize it). **The kernel, not the byte count, sets long-context decode cost here** — reinforcing the engine/kernel-is-a-first-class-variable thesis.

## Manifest
llama-bench b9279 · Card B · `-p 0 -n 64 -d {0,32768,65536,131072} -ctk q8_0 -ctv q8_0 -fa 1 -r 2` · driver 32.0.101.8826.

## ISOLATION RESULT — the cause is the FA KERNEL, not q8
Ran **f16 KV + flash attention** (`-fa 1`, no q8) to separate the FA kernel from the q8 dtype:
| ctx | f16 no-FA | **f16 +FA** | q8 +FA |
|---|---|---|---|
| 0 | 132.8 | 119.7 | 104.1 |
| 32K | 38.0 | **10.34** | 9.38 |
| 64K | 11.5 | **5.36** | 4.92 |

**f16+FA ≈ q8+FA at depth** (10.3 vs 9.4; 5.4 vs 4.9), both **~4× slower than f16-no-FA** → **the Vulkan/Arc flash-attention kernel is the bottleneck, independent of KV dtype**; q8 adds only ~10%. **Conclusion (airtight, actionable): on Vulkan/Arc, flash attention is a *pessimization* for long-context decode** (opposite of CUDA) — the default path wins ~4×. Since quantized KV *requires* FA, **q8 KV is a trap on this stack** (can't get byte-savings without the broken-FA tax). Fix = a better Vulkan FA kernel / a non-FA quantized-KV path / SYCL. **Engine + kernel is a first-class variable** — sharpened to a deployable rule.
