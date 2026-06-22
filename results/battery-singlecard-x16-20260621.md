# Single-card B70 @ PCIe x16 battery — results (2026-06-21/22)

Companion to `prereg/battery-singlecard-x16-20260621.md` (tag
`prereg-singlecard-x16-20260621`, commit 818f569 — predictions locked before data).

## Configuration

Rig reconfigured for airflow after the morning dual-card battery: the 2nd B70 and the
RTX 2070 Super were pulled. **One B70 remains, in the primary slot, now also driving the
4K (3840x2160) display.** The engine enumerates exactly one device:
`Vulkan0: Intel(R) Arc(TM) Pro B70 Graphics (32630 MiB, 31861 free)`. The old
"never serve device 0" rule was 2070-specific and is now moot: Vulkan0 IS the B70.

- Model (unless noted): Qwen3-30B-A3B-Instruct-2507-Q4_K_M (17.28 GiB), f16 KV, FA on.
- Engine: llama.cpp Vulkan b9279 (47c0eda9d). Binary D:\work\llamacpp-b9279-vulkan.
- Host: Ryzen 9 5900X / 32 GiB DDR4-3800. C: 91 GiB free.
- Watchdog: observer + TDR-watch -> results/raw/watchdog-x16-20260622.jsonl.

PCIe note: a single card in the primary X570 slot is x16 electrically (vs x8/x8 with two
cards this morning). We measure the *effect* (load + prefill), not a width readout (live
width reads were unreliable — ASPM idle x1 — in the morning session).

## Configuration update (mid-battery, before Row 2)

The first Row 2 attempt hung the machine on its first (8.4 GiB) load -- a GPU/driver
stall on the B70 *while it was driving the 4K desktop* (the Row 2 CSV held only its
header; 8 GiB cannot pressure 32 GiB RAM, ruling out a host-memory cause). After a
reboot, an RTX 4070 Ti (12 GiB) was added in the chipset x4 slot to take over the
display, returning the B70 to **headless** operation. Post-change enumeration:

```
Vulkan0: NVIDIA GeForce RTX 4070 Ti (11994 MiB)        <- display, never served
Vulkan1: Intel(R) Arc(TM) Pro B70 Graphics (32630 MiB) <- headless compute
```

So Row 1 was measured with the B70 as the display card; **Row 2 onward runs on the
headless B70, pinned with `--device Vulkan1`** (left to auto, llama.cpp would split the
model across both GPUs and place layers on the 12 GiB display card). The B70 stays in the
primary slot (x16); the 4070 Ti on the PCH x4 does not steal CPU lanes (operator's prior
x8/x8 result). Watchdog re-armed without `--watch-tdr` (that path hung its first tick and
gave no coverage during the freeze). Idle host baseline ~9.9 GiB used / ~22 GiB free, so
no-mmap loads are capped at <=18.5 GiB to stay clear of the 32 GiB host wall.

## Row 0 — Display-overhead baseline

The B70 now drives the desktop. At idle the 4K desktop holds ~0.9 GiB dedicated VRAM
(906 MiB measured; 31861 of 32630 MiB free per the engine). **Usable ceiling ~31 GiB**
for model + KV. (Under-load dedicated/shared sampled in Rows 2/4.)

## Row 1 — Prefill (and decode) at x16 vs the morning x8  [P1]

Qwen3-30B-A3B, f16 KV, FA on, 3 reps. `pp512` = prefill throughput, `tg128` = decode.
Raw: results/raw/prefill-x16-20260621.jsonl.

| depth | pp512 t/s (x16) | tg128 t/s (x16) | x8 morning (endpoints) |
|------:|----------------:|----------------:|------------------------|
| 0     | 2016.2          | 119.2           | pp 2014 / tg 119.6 |
| 16384 | 287.4           | 18.85           | — |
| 32768 | 144.2           | 10.27           | — |
| 65536 | 73.0            | 5.37            | pp 69.6 / tg 5.43 |

**P1 CONFIRMED.** At matched depths the x16 numbers are statistically identical to the
morning x8 run: pp512 @d0 2016.2 vs 2014 (+0.1%), tg @d0 119.2 vs 119.6 (-0.4%),
pp @d64k 73.0 vs 69.6 (+4.8%, within noise), tg @d64k 5.37 vs 5.43 (-1.1%). The wider
PCIe link does **not** change steady-state prefill or decode — both are compute-bound
once weights are resident, exactly as predicted. Bonus: the decode cliff replicates
(119 -> 5.37 over 0->64k = 22x; morning 22x), and the first-16k FA-on decode tax is
intact (119 -> 18.85 = 6.3x).

## Row 2 — Model cold/warm load time (rotation cost)  [P2, P3]

no-mmap (`-mmp 0`) forces a full file read + GPU upload at load (vs lazy mmap), making load
time real. Each model loaded cold then immediately warm, pinned `--device Vulkan1`. Watchdog
peak during the run: phys 11.4 GiB / commit 51.5% / level OK (host never stressed — no-mmap
bytes stream disk->host->GPU and host pages reclaim after upload; the ceiling is commit,
limit 61.9 GiB w/ pagefile, not resident phys). Raw: results/raw/modelload-x16-20260622.csv.

D: sequential read ceiling (measured, uncached 5 GiB slice): **1.20 GiB/s**. D: is a Crucial
P3 Plus 4 TB (QLC, DRAM-less NVMe — bulk storage). C: is a Samsung 980 PRO (fast, but small +
space-capped). Models live on D:.

| model | size GiB | cold s | warm s | cold GiB/s | warm GiB/s | speedup | note |
|-------|---------:|-------:|-------:|-----------:|-----------:|--------:|------|
| qwen2.5-14B (dense) | 8.37 | 5.9 | 4.8 | (1.42) | 1.76 | 1.23 | cold contaminated (pre-warmed by smoke test) |
| Mistral-24B (dense) | 13.35 | 16.9 | 7.2 | 0.79 | 1.84 | 2.33 | clean |
| Qwen3-30B-A3B (MoE) | 17.28 | 55.9 | 9.0 | 0.31 | 1.91 | 6.18 | MoE small-tensor read penalty |
| qwen2.5-32B (dense) | 18.49 | 29.5 | 9.6 | 0.63 | 1.93 | 3.08 | clean |
| qwen2.5-coder-32B (dense) | 21.66 | 29.2 | 70.5 | 0.74 | 0.31 | 0.41 | **warm SLOWER -- exceeds cache** |
| qwen2.5-32B-q6 (dense) | 25.04 | 104.1 | 60.2 | 0.24 | 0.42 | 1.73 | **cold thrashes -- exceeds RAM** |

**P2 REFUTED on the numbers, confirmed in spirit.** Predicted disk-bound at ~3 GB/s, linear,
Qwen3 in 6-9 s. Actual: I/O-bound at 0.3-0.8 GiB/s (disk itself caps at 1.2), non-linear,
Qwen3 took 55.9 s. Core claim holds: load is nowhere near PCIe bandwidth (even warm upload is
~2.1 GiB/s), so **x16 vs x8 is irrelevant to load** (why Row 1 saw no prefill change). Two
real bottlenecks instead: (1) storage tier (slow QLC bulk drive), (2) MoE read pattern
(Qwen3 ~26% of sequential vs ~50-66% dense).

**P3 (rotation): warm reload is upload-bound (~0.8 s init + ~2.1 GiB/s), big speedup when
cached.** Warm-vs-size linear fit: slope ~0.47 s/GiB (=> ~2.1 GiB/s GPU upload), intercept
~0.8 s init. At <=18.5 GiB the model fits the ~22 GiB free cache, so warm is 7-10 s (2.3-6.2x
faster than cold) and NOT RAM-bounded. RAM-bound regime (model > cache) tested in Row 2b.

**Rotation vs KV-restore (synthesis / double-check of the one-pager claim).** Cold model
rotation costs 17-56 s here (disk-bound on the bulk drive); warm ~9 s (upload floor). Either
way, rotating *models* is far costlier than denning's *KV restore on a resident model*
(0.3-4 s, morning C1 / Row 4), and three ~17 GiB models cannot co-reside on one 32 GiB card
(51 > 32). So on a single B70 the cheap lever is **keep one model resident, restore/swap KV**
-- not rotate models. Model rotation pays only when models are small enough to co-reside, or
when the alternative is a full multi-minute reprefill. (Aside: the morning C1 restore at
~0.78 GiB/s for 64k is also D:-disk-bound -- a faster drive would speed restore too.)

**P3 CONFIRMED (Row 2b, sharply).** Past the ~22 GiB free-RAM knee the warm benefit doesn't
just vanish -- it inverts. coder-32B (21.66 GiB) warm reload took 70.5 s vs 29.2 s cold
(0.41x, i.e. 2.4x SLOWER) because the fresh no-mmap buffer evicts the very cache it would
reuse, then re-reads under memory pressure (pagefile thrash). At 25 GiB even the cold load
thrashes (0.24 GiB/s, 104 s). The watchdog's phys stayed ~11 GiB throughout -- the thrash is
pagefile I/O, not a resident-RAM spike -- but commit rose to 62.3%, vindicating A4 ("commit,
not free RAM, is the binding signal"). This is the RAM<VRAM inversion made visible: a model
that fits the 32 GiB GPU (25 < 32) does NOT fit the 32 GiB host cache (25 > ~22 free), so
staging/reloading it via host RAM thrashes. Operational rule: don't lean on host RAM to cache
big models; keep them resident in VRAM and manage KV (denning).

## Row 4 — denning restore vs re-prefill on the headless B70  [P4]

C1 re-run on the now-headless B70 (Vulkan1, full 32 GiB), q8 KV, 72k ctx, FA on. COLD
re-prefill TTFT (what a stock engine pays after a co-tenant evicts the prefix) vs RESTORE
TTFT (save KV -> evict -> restore -> first token). Raw: results/raw/battery-C1.json; morning
x8 backup: battery-C1-morning-x8.json.

| depth (tok) | cold re-prefill TTFT | restore total (save / restore / 1st-tok ms) | speedup | morning x8 |
|------------:|---------------------:|--------------------------------------------:|--------:|-----------:|
| 16k (16930) | 37.5 s | 281 (483 / 194 / 87) | **133x** | 114x |
| 32k (33916) | 143.0 s | 558 (762 / 397 / 161) | **256x** | 219x |
| 64k (67888) | 559.1 s (9.3 min) | 1176 (1992 / 864 / 312) | **475x** | 145x |

**P4 CONFIRMED (stronger than x8).** Restore is 133-475x cheaper than re-prefill, far above
the >=50x bar. Cold re-prefill times are identical to the morning x8 run (37.5/143/559 vs
37.2/142.8/558.9 s) -- prefill is compute-bound and x16-invariant (Row 1, now on the full
path). Restore is *faster* this run (64k 1.18 s vs morning 3.85 s): the just-saved KV slot is
served from OS write-cache rather than re-read from the slow D: drive, so restore latency is
disk/cache-sensitive (a faster drive would help it) while the keystone gap holds regardless.
P4's display-overhead clause is N/A now -- B70 headless, no display tax on the serving card.
Whole-battery watchdog peak: phys 27.9 GiB / commit 62.3% / level OK throughout.

Takeaway: the denning thesis in one row. Re-prefilling 64k of evicted context costs **9.3
minutes**; restoring it costs **~1.2 seconds**. Keep the model resident and restore KV rather
than rebuild it (or rotate models, per Row 2).

## Row 5 — vLLM viability on native Windows/Arc  [P5]

Dry-run resolve (`pip install vllm --dry-run`) in the denning venv. The finding refutes the
prereg premise: **PyTorch 2.12.1+xpu is already installed and functional on Windows** --
`torch.xpu.is_available()` True, device 0 = Intel Arc Pro B70 (triton-xpu 3.7.1 + full oneAPI
runtime present). Intel XPU PyTorch on native Windows is real here.

But vLLM itself has **no win_amd64 wheel** -- pip fetched vllm-0.23.0.tar.gz (sdist) and
planned to build from source, which on Windows is unsupported/fragile. The resolve would also
mutate the denning venv (numpy downgrade + ~120 packages incl. transformers 5.12). **Not
installed** -- protecting the working experiment environment.

**P5 verdict: refined.** The barrier is not XPU availability (works on Windows now) but vLLM
packaging: no Windows build, and a source build would likely fail and pollute the env. The
real vLLM-vs-llama.cpp baseline belongs on the Linux box (vLLM's XPU path is Linux-supported)
-- being set up. For a Windows-native Intel engine comparison sooner, IPEX-LLM (prebuilt
Arc/Windows) is the realistic alternative. Decision deferred to operator.

## Row 6 — 70B overcommit / WDDM spill  [P6]

Llama-3.3-70B-Q4 (39.6 GiB) loaded with -ngl 99 on the headless B70 (32 GiB). Sampled GPU
dedicated vs shared during load. Raw: results/raw/spill-70b.*.

| signal | value |
|--------|-------|
| B70 dedicated | 32,537 MB (pinned at the ~32 GiB VRAM cap) |
| B70 shared (system RAM) | 7,529 MB |
| total | ~40 GiB ≈ the 39.6 GiB model |
| host | commit 85.9% (WARN) / phys 22.3 GiB |

**P6 CONFIRMED (mechanism) -- safed before decode.** The 70B overflows the 32 GiB card and
WDDM silently backs the ~7.5 GiB overflow with Shared GPU Memory (system RAM) -- the model-side
demotion we could NOT trigger with a single KV stream <=128k this morning. The run was stopped
at commit 85.9% (WARN) rather than execute the spilled prefill/decode: that is the host-RAM /
shared-memory cascade that previously cost a BIOS reflash, and the memory signal already
confirms the hypothesis. The decode-speed sub-claim (<2 t/s) is UNMEASURED by choice. On kill,
VRAM + host released cleanly (commit 85.9% -> 21.2%, dedicated/shared -> 0). Implication for
denning: admission must REFUSE a model that would spill (or accept slow-spill knowingly) --
the OS will happily let you overcommit into system RAM and crawl.

## Scorecard

| pred | claim | verdict |
|------|-------|---------|
| P1 | prefill/decode unchanged by x16 | CONFIRMED (within 5% of x8; compute-bound) |
| P2 | load disk-bound, not PCIe-bound | REFUTED on numbers / confirmed in spirit (I/O-bound 0.3-0.8 GiB/s on a 1.2 GiB/s QLC drive; MoE penalty; never near PCIe -> x16 irrelevant) |
| P3 | warm reload RAM-bounded | CONFIRMED sharply (warm inverts past the ~22 GiB cache -> 2.4x SLOWER; 25 GiB cold-thrashes) |
| P4 | restore keystone holds | CONFIRMED, stronger (133-475x; identical cold reprefill; cache-served restore) |
| P5 | vLLM won't run on Win/Arc | REFINED (torch-xpu works on Windows; vLLM has no Windows build + would pollute venv -> defer to Linux) |
| P6 | 70B triggers WDDM spill | CONFIRMED (32.5 GiB dedicated + 7.5 GiB shared; safed before decode) |

Cross-cutting: PCIe width (x8->x16) is irrelevant to everything measured -- prefill, decode,
load, restore are all compute- or I/O- or commit-bound, never PCIe-bandwidth-bound. The binding
constraints, in order, are **compute** (decode cliff), **host RAM / commit** (the RAM<VRAM
inversion: load-thrash + model spill), and **storage tier** (the slow QLC bulk drive caps load
and restore). denning's thesis -- keep models resident, restore KV rather than rebuild or
rotate -- is the right architecture for all three.
