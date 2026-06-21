# Result — clean, reproducible two-card serving baseline (2026-06-21)

> ⛔ **SUPERSEDED same day — the 8.81 ms TBT here is an ARTIFACT.** Re-running through the
> raw-persisting harness exposed a `denningd` bug: a per-request budget-probe stampede was
> *serializing* the 16 requests, so they never ran truly concurrent — making per-token
> latency look near-solo (8.81 ms). Fixed (background budget poller); the honest concurrent
> number is **TPOT p99 ~37 ms** (still ≤ the 50 ms SLO, so **16/16 goodput holds**). Use the
> corrected, raw-backed result: [`two-card-bench-corrected-20260621.md`](two-card-bench-corrected-20260621.md).

*The honest replacement for the retracted [`two-card-goodput-20260619`](two-card-goodput-20260619.md).
After offloading the display to an RTX 2070 SUPER (both B70s headless — Vulkan 1+2),
the two-card serve loop runs **clean and reproducibly**, with the display-driver TDRs
that contaminated the original gone. Two back-to-back runs, guard + watchdog armed.*

## Setup
`denningd --serve --cards 2 --n 16` (Vulkan 1+2, the two headless B70s; device 0 = the
2070 display card, never served). Qwen3-30B-A3B-Q4, 16 concurrent sessions, 8 slots/card,
SLO = TBT_median ≤ 50 ms. RTX 2070 SUPER drives the display the whole time.

## Goodput — the solid, reproducible baseline
| run | admitted | SLO met | median TBT | by card | TDR (before→after) |
|---|---|---|---|---|---|
| 1 | 16 | **16 / 16** | 8.81 ms | 8 / 8 | clean (114 → 114) |
| 2 | 16 | **16 / 16** | 8.81 ms | 8 / 8 | clean (114 → 114) |

**16 concurrent agent sessions, all meeting the SLO, on two headless B70s — reproducibly,
with zero display-driver resets.** Identical median TBT across runs; perfectly balanced
8/8 routing. This is the thesis metric ("N concurrent agent sessions at SLO on a
fabric-less consumer box") delivered clean — and it directly **supersedes the retracted
goodput result**, which got 14/16 across two TDRs (the 2 misses there were TDR shrapnel,
not capacity — they're gone here).

> ⚠️ **ARTIFACT STATUS (red-team finding, 2026-06-21): reproducible, but NOT yet
> publication-grade.** `denningd._serve` persists only this *summary* — there is **no
> per-request raw record** committed, so the number can't be independently verified from
> disk. It is also median-TBT (not p99 TPOT), closed-loop fixed-concurrency (not open-loop
> Poisson — risks coordinated omission), and uses non-standard "TBT" vocabulary. To
> publish: persist per-request raw data + re-run with the standard metric block
> (TTFT/TPOT/ITL, p50/p90/p99) under open-loop Poisson via `vllm bench serve`. See
> [`../docs/benchmark-strategy.md`](../docs/benchmark-strategy.md) §0 + §5.

## Throughput — reported, NOT yet a scaling claim (honesty hold)
Aggregate decode (sum of per-session decode-tps) was **1828.5 / 1833.0 t/s** across the
two runs — reproducible. **But it does not cleanly reconcile with the single-card headless
runs** ([`headless-single-card-20260621`](headless-single-card-20260621.md): ~96 t/s at
N=8). Per-card that is ~915 (two-card) vs ~96 (single-card) for the same 8-session per-card
load — a ~9× gap that identical per-card load should not produce.

The likely explanation is a **batching/measurement effect** (continuous batching amortizes
the MoE weight read across the batch, so per-session TBT can stay near solo-speed while
aggregate scales with batch size; and `decode_tps`, computed over each session's full span,
is skewed by inter-token stalls in a way median-TBT is not). But "likely" is not "measured."
**Per the project's pre-registration discipline, no throughput scaling factor is claimed
here.** A clean scaling number needs a *matched-per-card-load* measurement (e.g. single-card
N=8 vs two-card with 8/card, or `llama-bench` replica-vs-replica) over multiple reps — that
is the open TODO, and it is explicitly NOT this result.

## What this result does and does not say
- **Says (solid):** two headless B70s serve **16 concurrent sessions at SLO, reproducibly,
  with zero TDRs.** The display-card hard-hang is structurally gone; the two-card config is
  safe and stable. The retracted goodput claim is honestly replaced.
- **Does not say:** any "Nx throughput scaling" — that number is unmeasured pending a clean,
  matched-load run. (See the retracted `two-card-scaling`, which remains provisional.)

## Next
1. Matched-load scaling measurement for a defensible aggregate-throughput / Nx figure.
2. More reps (≥5) for a goodput CI, though 2/2 identical already shows tight reproducibility.

## Reproduce
```
python -m denning.denningd --serve --cards 2 --n 16   # Vulkan 1+2, guard+watchdog, prints tdr_clean
```
driver 32.0.101.8826 (Arc) / 591.86 (NVIDIA display). 2070 SUPER @ Vulkan0 never served.
