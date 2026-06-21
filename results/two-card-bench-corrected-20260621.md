# Result — two-card serving, publication-grade & corrected (2026-06-21)

*The goodput result re-run through the new raw-persisting harness ([`../denning/bench.py`](../denning/bench.py)) — which immediately exposed, and forced the correction of, a daemon bug that had been making the old "8.81 ms" numbers look artificially fast. This is the honest, reproducible, raw-backed two-card baseline. It **supersedes** the summary-only [`two-card-clean-baseline-20260621`](two-card-clean-baseline-20260621.md).*

## The bug the harness caught
The first publication-grade run reported **TPOT p99 8.89 ms but E2EL p99 21,360 ms** — a 2,400× gap the old median-TBT summary never measured. Decomposing the raw records: decode was a healthy ~1.3 s, but there was an **18.7 s gap between request arrival and the stream even being sent**. Cause: `denningd.handle()` synchronously shelled out to the D3D12 budget probe (`--hold-s 1`) on *every* request, so 16 concurrent requests stampeded into ~32 contending GPU-probe subprocesses.

**Two consequences, both important:**
1. The stampede *serialized* the requests, so they never actually ran 16-way concurrent — which is why per-token latency looked near-solo (**the "8.81 ms TBT" was an artifact**, in the old `_serve` runs too).
2. End-to-end latency was catastrophic (~20 s) and completely invisible to a TBT-only metric.

**Fix:** poll the live VidMm budget in a **background thread**, off the request path; `handle()` reads the cached value (never probes). E2EL dropped 20.2 s → 4.8 s and the numbers became *internally consistent* (E2EL ≈ TTFT + decode, no mystery gap).

## Corrected baseline (2 reps, raw-backed, full disclosure)
`bench --devices 1,2 --n 16` (closed-loop, 16 concurrent), seeds 0 and 1. Raw per-request records (TTFT + full ITL series + E2EL) fsync'd to `results/raw/bench-{1782030843,1782030939}.jsonl`.

| metric | seed 0 (p50 / p99) | seed 1 (p50 / p99) |
|---|---|---|
| **goodput** | **16 / 16** | **16 / 16** |
| TPOT | 34.6 / 37.6 ms | 34.0 / 36.6 ms |
| ITL | 28.5 / 31.1 ms | 28.8 / 30.9 ms |
| TTFT | 329.7 / 1042.6 ms | 868.8 / 1548.5 ms |
| E2EL | 4607.7 / 5858.2 ms | 5224.2 / 6233.4 ms |
| output tok/s | 352.2 | ~350 |
| TDR | clean (114→114) | clean |

SLO: per-request TPOT ≤ 50 ms **and** TTFT ≤ 2000 ms. **Both runs: 16/16 meet it.** TPOT/ITL p99 are tight and reproducible (~37 / ~31 ms); TTFT is noisier (1.0–1.5 s, prefill of 8 concurrent per card); E2EL ~6 s for 128 tokens under 16-way load.

## What this says (honestly)
- **The thesis metric holds:** two headless B70s sustain **16 concurrent sessions at SLO**, reproducibly, zero TDRs — now with *real* latency numbers and a raw artifact anyone can recompute.
- **The "8.81 ms" is retracted** as a serialization artifact. Per-token decode is genuinely fast; *16-way concurrent* the honest TPOT is ~37 ms p99 — still well under the 50 ms SLO.
- **The method worked exactly as designed:** raw + E2EL + p99 caught a daemon bug that the median-TBT summary hid, and the fix made the numbers honest *without* breaking the goodput claim.

## Caveats (still not a leaderboard number)
- **N = 16 → noisy percentiles**, TTFT especially (p90 = p99 at this sample size). Publication needs **N ≥ hundreds** per load point.
- **Closed-loop fixed-concurrency**, not yet open-loop Poisson — risks coordinated omission. The harness supports `--rate`; the real number is the open-loop sweep.
- **No baseline arm yet.** The contribution is the **stock-vs-denning A/B under OS pressure** (benchmark-strategy §2.1), not this single-arm point.

## Reproduce
```
python -m denning.bench --devices 1,2 --n 16            # closed-loop, raw + p99 + disclosure
python -m denning.bench --devices 1,2 --n 64 --rate 8   # open-loop Poisson (the correct form)
```
