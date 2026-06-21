# denning Benchmark Strategy (2026-06-21)

*Produced by a 9-agent red-team/green-team workflow (5 research + 3 adversarial + 1
synthesis), then **verified against the actual artifacts** by the main loop. Two
red-team findings were checked directly; one was confirmed, one was overstated (see
§0). This is the canonical plan for how denning measures and presents results.*

## §0 — Verification of the two red-team "[fatal]" findings
The adversarial pass raised two showstoppers. Checking them against the repo:

| finding | verdict | basis |
|---|---|---|
| "The 11.5× decode cliff is retracted-grade / a misread of a 70B-at-empty value" | **OVERSTATED — rejected** | The agent read the *battlemage 70B* files (`overnight-*-c*.jsonl`), which aborted on the bogus `-c` flag (confirmed broken). The denning roofline ([`E1-decode-roofline-20260619`](../results/E1-decode-roofline-20260619.md)) is a *separate, real* measurement: 30B-A3B-Q4, `llama-bench -n 64 -d {0,8k,16k,32k,64k} -r 2` — the **correct `-d` depth flag**. The cliff is genuine data. |
| "The 16-session goodput headline has no backing raw artifact" | **CONFIRMED — real gap** | `denningd._serve` prints a *summary* and computes per-session stats, but never persists per-request raw records. The result is reproducible (2/2) and the summary is committed, but there is no per-request artifact for independent verification. |

**Both corrections matter.** The cliff stands as *data* — but the strategy still
**demotes it** (§2.3), for a different reason than the agent gave: a control plane
cannot make a decode kernel faster, so the cliff is *motivation*, not a denning win.
The goodput gap is **real and must be closed** before the number is published.

The lesson is the method working in both directions: don't accept our own results
uncritically (goodput raw data), and don't accept the red team's claims uncritically
(the cliff "retraction"). Verify everything against the artifacts.

---

## §1 — Standard language to adopt (answers "how do people communicate this?")
Stop inventing vocabulary; speak the field's. Report the **full block** for every
serving run — never throughput alone:

- **Latency:** **TTFT** (time-to-first-token), **TPOT** (time-per-output-token = mean ITL excl. first), **ITL** (inter-token-latency distribution), **E2EL** (end-to-end). Report **mean + p50 + p90 + p99** for each. A median-only number is a red flag — *and* p50 hides denning's own thesis (OS-eviction stalls and the long-context tail live in **p99**).
- **Throughput:** output tok/s, total tok/s, request tok/s (req/s).
- **Goodput-under-SLO is the headline** (DistServe definition): the max sustained request rate where ≥X% of requests meet TTFT **and** TPOT bounds *jointly*. State the SLO string explicitly, the percentile band, and the MLPerf yardstick (Server: TTFT≤2s/TPOT≤80ms p99; Interactive: 15ms — denning's 50ms sits between).
- **Vocabulary fix:** kill "TBT" in external materials → **ITL/TPOT**. "median TBT ≤ 50ms" → "**TPOT/ITL p50 ≤ 50ms**". Ship a one-line mapping table.

**Tooling:** drive **`vllm bench serve`** against llama.cpp's OpenAI `/v1` endpoint
(no engine mod — fits the shim thesis): `--dataset-name {sharegpt,random}`,
`--request-rate` + `--burstiness 1.0` (**open-loop Poisson**), `--goodput tpot:50`,
`--percentile-metrics ttft,tpot,itl,e2el`. Cross-check with GenAI-Perf. For
single-stream sanity, emit raw `llama-bench` markdown tables.

**Open-loop Poisson is mandatory**, not fixed concurrency — closed-loop tools stop
firing while the server stalls (**coordinated omission**), so they never sample the
OS-eviction collapse or the long-context tail, which are *exactly* denning's
phenomena. Our current `handle_many` fixed-concurrency harness has this flaw.

**Canonical plots:** (1) **goodput knee** — x = arrival rate or context depth, y =
sessions/req-s meeting the SLO (drawn as a line), baseline vs denning; (2)
**latency-vs-load Pareto** — twin p99-TTFT / p99-TPOT panels, hockey-stick at the
saturation knee (denning's `N*=min(compute,mem-budget)` **is** that knee — name it).

**Disclosure block (every number; missing field = non-publishable):** model + weight
quant + **KV quant**; context; concurrency; engine + exact llama.cpp commit; Vulkan +
Arc driver; Windows build; flash-attn on/off; **the live VidMm budget at run time**;
and "**Arc B70s headless; display on a separate RTX 2070 Super**" (measurement hygiene
= a credibility asset, state it up front).

---

## §2 — Highest-value benchmark directions (ranked to survive the red team)

### #1 (THE headline) — Goodput collapse vs graceful degradation under OS memory pressure
The only axis where denning's control plane is the independent variable and the
incumbents (vLLM/PagedAttention, CacheGen, FlexGen, DistServe — all assume the server
*owns* a fixed VRAM budget) structurally cannot compete.

**Pre-registered experiment:** fix model + N=16 sessions; sweep per-session context
depth d ∈ {2k, 8k, 16k, 32k, 64k}. Two arms, identical hw/driver/seed/engine:
- **ARM A** = stock llama-server, OS-default residency, no admission.
- **ARM B** = denning (admission on live VidMm budget + lifetime-class eviction + host KV swap).

**Primary plot:** x = context depth (log), y = goodput (# of 16 sustaining **p99 TPOT
≤ 50ms**). **Pre-state the predicted shape:** curves *overlap at short context*
(denning is honestly a no-op at low pressure — report that, it's integrity) and
*diverge* once aggregate KV crosses the OS budget (baseline falls toward 0 via
eviction/TDR/OOM; denning plateaus). **Headline = the depth where baseline hits 0
while denning still serves ≥k/16.** Secondary: a b70tools eviction/TDR-event timeline
on the baseline arm — the H1 mechanism made visible.

### #2 — KV-swap restore-vs-re-prefill TTFT win (CacheGen-shaped)
Reframe the "29×" microbench as a serving plot: resumed-session **TTFT with host-KV
restore vs cold re-prefill**, swept by depth. This is exactly CacheGen's (SIGCOMM'24)
metric → directly comparable. This is where long-context *prefill* cost actually bites,
and the rig data supports it (prefill 186→120 t/s by 16k).

### #3 — Long-context cliff: REAL data, but reframe as motivation (not a denning win)
The cliff is genuine (§0). But denning is a control plane over an unmodified engine —
**it cannot make one decode step faster than the Vulkan attention kernel allows.** So
"denning mitigates the decode cliff" is not a defensible *contribution*. Correct use:
- **Re-measure cleanly** (it's currently only `-r 2`): `llama-bench -d {0,4k,8k,16k,32k,64k} -n 128 -r 5`, **fp16 + q8 KV**, decode (tg) and prefill (pp) reported **separately**, raw JSONL persisted UTF-8. Add a **q8-KV arm** or a reviewer says "just quantize the cache."
- Use it as the **admission floor** motivation (keep sessions left of the cliff) and fold the real long-context story into #1 (capacity) and #2 (prefill/TTFT). **Never headline "decode cliff" as a denning speedup.**

### #4 — Cost / power accessibility (separate note, OUT of the systems claim)
Lead with **bandwidth-per-dollar** (608 GB/s ÷ $949 ≈ 0.64 GB/s/$). Compute **$/Mtok
at a fixed SLO from real ~$2k receipts** with stated utilization + quant; 3yr + 5yr
amortization (never a single point). Compare **only** to used-3090 rigs and open-model
APIs at matched quality — **never frontier datacenter parts**. Frame headless-Arc as
hygiene. Keep it entirely out of the novelty claim.

---

## §3 — Reuse (don't rebuild)
- **b70tools (no modification):** the `MetricSample` schema, event bus, replay reader; the per-adapter FSM + DXGI LOCAL budget = the admission signal *and* the eviction/TDR-timeline for the #1 mechanism plot; the `DriverRuntimeFingerprint` JSONL event **is** the disclosure block — emit it with every result set.
- **battlemage:** reuse the PerfBench concurrent-batch HTTP runner for the goodput A/B — **but fix the harness first** (it wrote UTF-16 + used the bogus `-c`). Clean same-rig baselines to anchor against: 14b ~45 t/s Vulkan; 70b ~151 t/s prefill / ~11.7 t/s decode (layer-split).
- **Do NOT cite** the four `overnight-*-c*/fp16kv/q8kv.jsonl` files — aborted/prefill-only. Quarantined.

---

## §4 — Honesty guardrails (what NOT to claim)
- **No throughput-scaling factor** — keep holding the unexplained aggregate; never derive a 2-card multiplier from it.
- **No "16-session goodput" as published** until a repro bundle exists: **persisted per-request raw records**, client-side timestamps, open-loop Poisson, N≥2. (The summary stands as a reproducible *internal* result; it is not yet publication-grade.)
- **No "decode cliff" as a denning win** — it's the kernel's, not ours; use it as motivation only.
- **No single-stream speedup framing** — denning doesn't touch the kernel. Every win is a goodput-under-pressure **A/B delta**, never an absolute.
- **No "OS for KV / first-class resource"** phrasing (Symphony/PTask/kvcached own it). The one durable sentence: *"all prior KV systems assume the server owns a fixed VRAM budget; denning targets the regime where the OS grants a moving, revocable budget and crossing it is fatal."*
- **No cross-vendor leaderboard claim** — everything is within-rig A/B (no Linux/Arc/Vulkan apples-to-apples baseline exists).
- **Concede the absorbables:** admission control is classical (Denning PFF/roofline); KV swap/tiering is shipped (vLLM OffloadingConnector, KVBM, LMCache, CacheGen). The non-absorbable residuals: (a) the **adversarial involuntarily-shrinking budget** the server doesn't own; (b) the **inverted tier cascade** (recompute-as-primary-reclaim, because 32GB VRAM can't evict into 16GB host); (c) the **lifetime-class eviction ablation** (must beat per-request-TTL and per-block-priority by a robust margin or be dropped).
- **Publish a frozen-build noise floor first** (N≥5, p50/p99, CIs on one pinned build/driver/quant) and require every reported delta to exceed it by a stated effect size. Anything under the floor is null.

---

## §5 — Next experiments (ordered)
1. **Make `denningd` persist per-request raw records** (per-session TTFT/ITL series + the disclosure block) — closes the §0 goodput gap. The single highest-leverage fix.
2. **Publish the noise floor** — one frozen build/driver/quant, N≥5, p50/p99 + CIs for pp512/tg128 and a small goodput point. Gates every later delta.
3. **Re-measure the long-context curve as motivation** — `-d` sweep, fp16 + q8 KV, decode & prefill separate, r≥5, raw UTF-8 JSONL. Decide cliff-in-or-out from the data.
4. **Stand up the open-loop serving harness** — `vllm bench serve` → llama.cpp `/v1`, Poisson, `--goodput tpot:50`, full p50/p90/p99 block; validate it reproduces the stock baselines.
5. **Run the #1 A/B** (goodput vs context depth, stock vs denning, + q8-KV arm) with b70tools eviction-timeline capture. **This is the contribution figure.** Pre-register; N≥2.
6. **Run the #2 KV-restore-vs-re-prefill TTFT curve** (the "29×" as a CacheGen-style serving plot).
7. **Only then**, if #5/#6 land, write the cost/accessibility note (#4) as a standalone artifact.

**Key files:** harness to fix — `D:\work\battlemage\bench-2026-05-24\overnight-2026-05-24-context-curve.ps1`; reuse telemetry — `D:\work\b70tools` (MetricSample + DriverRuntimeFingerprint); quarantined — the four `overnight-*-c*/fp16kv/q8kv.jsonl`.
