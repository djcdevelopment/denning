# Result — the first baseline-vs-denning A/B: admission control under overload (2026-06-21)

*The control group we'd never run. Same client, same workload (N=16, closed-loop), same
SLO, same raw+p99 harness ([`../denning/bench.py`](../denning/bench.py)) — the **only**
variable is whether denning's control plane is in the path. ARM A = stock `llama-server`,
round-robin, no admission/arena. ARM B = denning (admission on the live VidMm budget +
lifetime-class arena + routing). Six configs: {baseline, denning} × {card 1, card 2, both}.*

## The matrix
| arm | cards | admitted | rejected | goodput | TTFT p50 | TTFT p99 | TPOT p99 | E2EL p99 | out tok/s | TDR |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 1 (Vk1) | 16 | 0 | 8/16 | **5,510 ms** | 6,845 ms | 41.7 | 10,490 ms | 196.7 | clean |
| baseline | 1 (Vk2) | 16 | 0 | 8/16 | 4,702 ms | 5,884 ms | 36.9 | 9,463 ms | 218.0 | clean |
| **denning** | 1 (Vk1) | 8 | 8 | 8/16 | **322 ms** | 324 ms | 29.1 | 3,930 ms | 262.6 | clean |
| **denning** | 1 (Vk2) | 8 | 8 | 8/16 | 490 ms | 492 ms | 29.9 | 4,042 ms | 255.2 | clean |
| baseline | both | 16 | 0 | 16/16 | 504 ms | 508 ms | 31.4 | 4,235 ms | 487.3 | clean |
| **denning** | both | 16 | 0 | 16/16 | 323 ms | 329 ms | 29.7 | 4,016 ms | 513.7 | clean |

SLO: per-request TPOT ≤ 50 ms **and** TTFT ≤ 2000 ms.

## What it shows (and what it doesn't)
**Single card = 2× oversubscribed (16 requests, 8 slots) — denning's admission control is the difference:**
- **Baseline accepts all 16 and queues 8.** The queue backs up so badly that even the
  **median TTFT is 5.5 s** (p99 6.8 s) — most requests wait behind the queue. Goodput 8/16
  (the 8 queued blow the 2 s TTFT bound).
- **denning sheds the 8 that don't fit N\*** (admitted 8, rejected 8). The 8 served are
  **snappy: TTFT p50 322 ms** — a **17× better median** — and the rejected 8 fail *fast*
  (a clean 503 the client can retry/shed), not after a 5.5 s wait. Goodput 8/16.
- **Same goodput, opposite experience:** graceful degradation (fast service + fast failure)
  vs uncontrolled queueing collapse (everyone slow). This is exactly what admission control
  is *for*, shown against the real control group.

**Two cards = load fits (16 requests, 16 slots) — denning ≈ baseline:** both 16/16, both
snappy (denning 329 ms vs baseline 508 ms p99 TTFT — a slight edge, no oversubscription to
manage). **denning's overhead when it isn't needed is negligible** — the "no-op under no
pressure" property we need to be able to claim, confirmed.

**Honest scope — this is NOT a goodput win.** At fixed concurrency with no memory pressure,
denning serves the *same* number within SLO (slot-bound). The win is **tail/median latency
under overload** via load-shedding, and **predictability**. denning trades the baseline's
"serve everyone, slowly" for "serve the admissible fast, shed the rest" — the right trade
for interactive SLO serving, the wrong frame for batch throughput.

## Reference anchor
Against **MLPerf Llama-2-70B Server (TTFT ≤ 2 s)**: under single-card overload the **stock
engine violates it at the median** (5.5 s); **denning stays 6× under it** (322 ms). That is
the anchored, one-line version of the result.

## Caveats (before anyone over-reads this)
- **Our harness, not the industry-standard tool.** Per [`../docs/benchmark-strategy.md`](../docs/benchmark-strategy.md) §1.5, the *publishable* A/B must be re-run with **`vllm bench serve`** against an OpenAI `/v1` endpoint on both arms (baseline already has one; denning needs the `/v1` front — the next build). This result is mechanistically clear and suggestive, not yet leaderboard-grade.
- **N = 16, single rig, no noise floor, small-sample percentiles.** Need N ≥ hundreds + the frozen-build noise floor before any effect-size claim.
- **Closed-loop fixed-concurrency**, not open-loop Poisson (the rate-sweep is the correct form, and it's where the goodput *knee* — not just latency — would diverge).
- **Admission tuning is unexamined:** denning shed 8/8 over capacity; whether a small queue (N\* slightly > 8) would lift goodput without blowing the SLO is an open question.

## Reproduce
```
python -m denning.bench --arm baseline --devices 1   --n 16 --tag base-c1
python -m denning.bench --arm denning  --devices 1   --n 16 --tag den-c1
python -m denning.bench --arm baseline --devices 1,2 --n 16 --tag base-both
python -m denning.bench --arm denning  --devices 1,2 --n 16 --tag den-both
```
Raw per-request records: `results/raw/bench-*.jsonl`; summaries: `results/raw/bench-*.summary.json`.
