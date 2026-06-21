#!/usr/bin/env python3
r"""denning serving benchmark -- raw-persisting, percentile metrics, open-loop Poisson.

Closes the goodput-artifact gap (docs/benchmark-strategy.md §0 + §5):
  * every request's RAW record (TTFT + full ITL series + client-measured E2EL) is
    fsync'd to results/raw/bench-<ts>.jsonl -- independently recomputable, not a summary;
  * the STANDARD metric block (TTFT / TPOT / ITL / E2EL) is reported at mean/p50/p90/p99
    -- the tail, not the median, because the OS-eviction + long-context stalls live there;
  * arrivals are OPEN-LOOP POISSON (--rate) so a stalled server keeps receiving load and
    the tail is actually sampled (no coordinated omission); --rate omitted = closed-loop;
  * a DISCLOSURE block (model, quant, engine, drivers, devices, live VidMm budget, SLO,
    seed, headless/display note) ships with the result.

Drives denning (admission + routing + lifetime-class arena) via the Daemon. Point
--devices at the headless B70s (Vulkan 1,2); device 0 (the 2070 display card) is refused.

  python -m denning.bench --dry-run                         # no GPU: verify the harness
  python -m denning.bench --devices 1,2 --n 64 --rate 8     # on-rig: open-loop Poisson @ 8 req/s
  python -m denning.bench --devices 1,2 --n 16              # on-rig: closed-loop fixed-concurrency
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from denning.control import budget as budgetmod
from denning.denningd import Daemon

RAW_DIR = r"D:\work\denning\results\raw"
PROMPT = ("Explain virtual memory, demand paging, the TLB, and page replacement in a few "
          "precise paragraphs, then discuss working-set models and page-fault frequency.")

# Fixed rig facts for the disclosure block (live values captured at run time).
RIG = {
    "gpus": "2x Intel Arc Pro B70 32GB (headless) + RTX 2070 Super (display)",
    "arc_driver": "32.0.101.8826", "nvidia_display_driver": "591.86",
    "os": "Windows 10", "engine": "llama.cpp Vulkan b9279", "kv_quant": "f16",
    "model": "Qwen3-30B-A3B-Instruct-2507-Q4_K_M",
    "host": "Ryzen 5900X / X570 / 32GB RAM",
    "note": "Arc B70s headless; display on a separate RTX 2070 Super (Vulkan0, never served)",
}


def pctl(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1)))))
    return round(xs[k], 2)


def block(name, vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {name: None}
    return {name: {"mean": round(statistics.mean(vals), 2), "p50": pctl(vals, 50),
                   "p90": pctl(vals, 90), "p99": pctl(vals, 99), "n": len(vals)}}


def arrivals(n, rate, seed):
    """Open-loop Poisson inter-arrivals at `rate` req/s; rate falsy/<=0 => all at t=0 (closed-loop)."""
    if not rate or rate <= 0:
        return [0.0] * n
    rng = random.Random(seed)
    t, out = 0.0, []
    for _ in range(n):
        out.append(t)
        t += rng.expovariate(rate)
    return out


def run(dispatch, n, rate, n_predict, seed):
    sched = arrivals(n, rate, seed)
    rec = [None] * n
    t0 = time.perf_counter()

    def fire(i):
        wait = sched[i] - (time.perf_counter() - t0)
        if wait > 0:
            time.sleep(wait)                      # open-loop: fire at the scheduled arrival
        arr = time.perf_counter()
        r = dispatch(i, PROMPT, n_predict)        # denning: admission+arena+stream; baseline: raw stream
        e2e = round((time.perf_counter() - arr) * 1000, 1)   # client E2EL incl. queueing
        itl = r.get("itl_ms")
        rec[i] = {"i": i, "arrival_ms": round((arr - t0) * 1000, 1),
                  "admitted": bool(r.get("admitted")), "device": r.get("device"),
                  "action": r.get("action"), "ttft_ms": r.get("ttft_ms"),
                  "tpot_ms": round(statistics.mean(itl), 2) if itl else r.get("tpot_ms"),
                  "e2el_ms": e2e, "decode_span_ms": r.get("e2el_ms"),
                  "tokens": r.get("tokens"), "itl_ms": itl,
                  "error": None if r.get("admitted") else r.get("reason")}

    with ThreadPoolExecutor(max_workers=max(1, n)) as ex:
        list(ex.map(fire, range(n)))
    return [r for r in rec if r], time.perf_counter() - t0


def summarize(records, wall, slo_tpot, slo_ttft):
    adm = [r for r in records if r.get("admitted")]
    out_tok = sum((r.get("tokens") or 0) for r in adm)
    itl_all = [x for r in adm if r.get("itl_ms") for x in r["itl_ms"]]
    met = [r for r in records if r.get("admitted")
           and (r.get("tpot_ms") or 1e9) <= slo_tpot and (r.get("ttft_ms") or 1e9) <= slo_ttft]
    s = {"requests": len(records), "admitted": len(adm), "rejected": len(records) - len(adm),
         "goodput_count": len(met), "goodput_frac": round(len(met) / max(1, len(records)), 3),
         "slo": {"tpot_ms": slo_tpot, "ttft_ms": slo_ttft, "percentile": "per-request"},
         "output_tok_per_s": round(out_tok / wall, 1) if wall else None,
         "request_per_s": round(len(adm) / wall, 2) if wall else None,
         "wall_s": round(wall, 1)}
    s.update(block("ttft_ms", [r["ttft_ms"] for r in adm]))
    s.update(block("tpot_ms", [r["tpot_ms"] for r in adm]))
    s.update(block("itl_ms", itl_all))
    s.update(block("e2el_ms", [r["e2el_ms"] for r in adm]))
    return s


def main():
    ap = argparse.ArgumentParser(description="denning serving benchmark (raw + p99 + open-loop Poisson)")
    ap.add_argument("--dry-run", action="store_true", help="no GPU: drive a fake engine")
    ap.add_argument("--devices", type=str, default="1,2", help="Vulkan device indices (B70s); 0 refused")
    ap.add_argument("--n", type=int, default=64, help="number of requests")
    ap.add_argument("--rate", type=float, default=None, help="open-loop Poisson req/s; omit = closed-loop")
    ap.add_argument("--n-predict", type=int, default=128)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--slo-tpot", type=float, default=50.0)
    ap.add_argument("--slo-ttft", type=float, default=2000.0)
    ap.add_argument("--arm", choices=["denning", "baseline"], default="denning",
                    help="denning = control plane (admission+arena+routing); baseline = stock engine, round-robin")
    ap.add_argument("--tag", default=None, help="also write the summary JSON to results/raw/bench-<tag>.summary.json")
    args = ap.parse_args()

    devices = [int(x) for x in args.devices.split(",") if x.strip() != ""]
    if 0 in devices and not args.dry_run:
        print(json.dumps({"refused": "device 0 is the 2070 display card -- never serve on it"}))
        return 2

    guard = None
    if args.dry_run:
        from tests.test_shim import FakeAdapter
        adapter, live = FakeAdapter(), False
    else:
        from denning.control.tdr_guard import TdrGuard
        from denning.engine.llamacpp import LlamaCppAdapter
        adapter, live = LlamaCppAdapter(), True
        guard = TdrGuard(); guard.arm()

    if args.arm == "denning":
        daemon = Daemon(adapter, devices=devices, slots=8, ctx=2048, live_budget=live,
                        display_device=(None if args.dry_run else 0))
        daemon.start()
        serving = daemon.serving_devices
        dispatch, stop = (lambda i, p, n: daemon.handle(i, p, n)), daemon.stop
    else:   # baseline -- stock engine replicas, round-robin, NO admission/arena/affinity
        ports, handles, rr, lock = [], [], {"n": 0}, threading.Lock()
        for dev in devices:
            port = 8240 + dev
            handles.append(adapter.spawn_replica(dev, port, 8, 2048 * 8))
            if not adapter.health(port, 300):
                print(json.dumps({"error": "health timeout dev %d" % dev})); return 2
            adapter.stream(port, "warmup", 8, label="warmup")
            ports.append(port)
        serving = list(devices)

        def dispatch(i, p, n):
            with lock:
                port = ports[rr["n"] % len(ports)]; rr["n"] += 1
            st = adapter.stream(port, p, n, cache_prompt=True, label="r%d" % i)
            return {"admitted": True, "device": port - 8240, "action": "baseline",
                    "ttft_ms": st.ttft_ms, "tpot_ms": st.tbt_median_ms, "e2el_ms": st.e2el_ms,
                    "itl_ms": st.itl_ms, "tokens": st.tokens}

        def stop():
            for h in handles:
                adapter.stop(h)

    try:
        records, wall = run(dispatch, args.n, args.rate, args.n_predict, args.seed)
    finally:
        stop()

    summary = summarize(records, wall, args.slo_tpot, args.slo_ttft)
    summary["disclosure"] = dict(
        RIG, arm=args.arm, serving_devices=serving,
        arrival=("poisson@%g_req_s" % args.rate) if args.rate else "closed-loop_fixed-concurrency",
        n_requests=args.n, n_predict=args.n_predict, seed=args.seed, prompt_chars=len(PROMPT),
        live_budget_gb=None if args.dry_run else [budgetmod.read_live_budget_gb(x) for x in serving])
    if guard is not None:
        summary["tdr_clean"], summary["tdr_delta"] = guard.clean(), guard.delta()

    ts = "dry" if args.dry_run else str(int(time.time()))
    os.makedirs(RAW_DIR, exist_ok=True)
    raw_path = os.path.join(RAW_DIR, "bench-%s.jsonl" % ts)
    with open(raw_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
        f.flush()
        os.fsync(f.fileno())
    summary["raw_records"] = raw_path
    if args.tag:
        with open(os.path.join(RAW_DIR, "bench-%s.summary.json" % args.tag), "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
