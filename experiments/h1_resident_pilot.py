#!/usr/bin/env python3
r"""
H1 resident-server variant (I-3) — the stricter "evict-already-resident" test.

Unlike the load-under-contention pilot (`h1_eviction_pilot.py`, where the model
loaded WHILE the hog held VRAM), here the model is brought FULLY RESIDENT first
(persistent llama-server; a baseline stream confirms it), THEN the hog applies →
VidMm must evict ALREADY-RESIDENT model bytes (or evict the hog). This is the
faithful form of the tagged H1' prediction ("a model that fits is serving, and a
GPU-heavy app THEN runs").

Measures time-resolved TBT via a streaming completion (baseline vs under
pressure), correlated with the b70tools `non_local` timeline. Same safety
envelope as the pilot: watchdog observer-only + bounded hog.

  python experiments/h1_resident_pilot.py --baseline-only
  python experiments/h1_resident_pilot.py --arm-pressure --hog-cap-gb 15
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request

from h1_eviction_pilot import (card_b_env, preflight, start_recorder,
                               start_watchdog, start_hog, analyze, DEFAULT_MODEL)

LLAMA_SERVER = r"D:\work\llamacpp-b9279-vulkan\llama-server.exe"
PORT = 8231
PROMPT = ("Write a thorough, multi-paragraph technical explanation of how modern "
          "operating systems implement virtual memory, demand paging, the TLB, and "
          "page replacement. Be detailed and precise.")


def start_server(model: str, port: int) -> subprocess.Popen:
    return subprocess.Popen(
        [LLAMA_SERVER, "-m", model, "-ngl", "99", "--host", "127.0.0.1",
         "--port", str(port), "-c", "4096"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=card_b_env())


def wait_health(port: int, timeout: float = 180.0) -> bool:
    url = f"http://127.0.0.1:{port}/health"
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(1.0)
    return False


def stream_tbt(port: int, n_predict: int, label: str) -> dict:
    """Stream a completion; derive TBT stats from per-token timestamps."""
    body = json.dumps({"prompt": PROMPT, "n_predict": n_predict, "stream": True,
                       "cache_prompt": False, "temperature": 0.7}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/completion", data=body,
                                 headers={"Content-Type": "application/json"})
    times, t0 = [], time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    obj = json.loads(line[5:].strip())
                except ValueError:
                    continue
                times.append(time.perf_counter())
                if obj.get("stop"):
                    break
    except (urllib.error.URLError, OSError) as e:
        return {"label": label, "error": str(e), "tokens": len(times)}
    if len(times) < 2:
        return {"label": label, "tokens": len(times), "error": "too few tokens"}
    deltas = [times[i] - times[i - 1] for i in range(1, len(times))]
    return {"label": label, "tokens": len(times),
            "ttft_ms": round((times[0] - t0) * 1000, 1),
            "tbt_median_ms": round(statistics.median(deltas) * 1000, 2),
            "tbt_p95_ms": round(sorted(deltas)[max(0, int(0.95 * len(deltas)) - 1)] * 1000, 2),
            "decode_tps": round((len(times) - 1) / (times[-1] - times[0]), 2)}


def _kill(p):
    if p and p.poll() is None:
        try:
            p.terminate(); p.wait(timeout=10)
        except (subprocess.TimeoutExpired, OSError):
            p.kill()


def main() -> int:
    ap = argparse.ArgumentParser(description="H1 resident-server eviction test (I-3)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--arm-pressure", action="store_true")
    ap.add_argument("--baseline-only", action="store_true")
    ap.add_argument("--hog-cap-gb", type=float, default=15.0)
    ap.add_argument("--hog-hold-s", type=float, default=180.0)
    args = ap.parse_args()
    armed = args.arm_pressure and not args.baseline_only

    print("[h1r] === preflight ===")
    if not preflight(args.model):
        print("[h1r] NO-GO from preflight", file=sys.stderr)
        return 1

    ts = int(time.time())
    out_dir = rf"D:\work\denning\results\raw\h1r-{ts}"
    log_path = rf"D:\work\denning\results\raw\h1r-{ts}.watchdog.jsonl"
    result = {"ts": ts, "variant": "resident-server", "model": os.path.basename(args.model),
              "armed": armed, "hog_cap_gb": args.hog_cap_gb if armed else 0}

    rec = wd = hog = srv = None
    try:
        rec = start_recorder(out_dir); time.sleep(1.5)
        wd = start_watchdog(log_path, out_dir); time.sleep(0.5)
        print("[h1r] starting llama-server (bringing model fully resident) ...")
        srv = start_server(args.model, PORT)
        if not wait_health(PORT):
            print("[h1r] server failed to become healthy", file=sys.stderr)
            result["error"] = "server_health_timeout"
            return 2
        print("[h1r] server resident. warmup + baseline stream ...")
        stream_tbt(PORT, 16, "warmup")
        result["baseline"] = stream_tbt(PORT, args.n, "baseline")
        print(f"[h1r] baseline: {result['baseline']}")

        if armed:
            print(f"[h1r] === ARMED: hog -> {args.hog_cap_gb} GB (evicting a RESIDENT model) ===")
            hog = start_hog(args.hog_cap_gb, args.hog_hold_s)
            trace, t0 = [], time.time()
            while time.time() - t0 < 60:
                ln = hog.stdout.readline()
                if not ln:
                    if hog.poll() is not None:
                        break
                    continue
                trace.append(ln.rstrip()); print("   " + ln.rstrip())
                if "HOLDING" in ln:
                    break
            result["hog_trace"] = trace
            time.sleep(2.0)
            result["pressured"] = stream_tbt(PORT, args.n, "pressured")
            print(f"[h1r] pressured: {result['pressured']}")
            _kill(hog)
    finally:
        for p in (hog, srv, wd, rec):
            _kill(p)

    result["analysis"] = analyze(out_dir)
    b = result.get("baseline", {}).get("decode_tps")
    p = result.get("pressured", {}).get("decode_tps")
    if armed and b and p:
        result["decode_ratio"] = round(p / b, 3)
        nlpk = result["analysis"].get("nonlocal_peak_gb")
        result["pilot_verdict"] = (
            "H1-SUPPORTED-resident" if (p / b < 0.8 and nlpk and nlpk >= 0.5)
            else "VidMm-PROTECTED" if p / b > 0.9 else "AMBIGUOUS")
        print(f"[h1r] decode ratio={result['decode_ratio']} | "
              f"tbt {result['baseline']['tbt_median_ms']}->{result['pressured']['tbt_median_ms']} ms | "
              f"non_local={nlpk} GB -> {result['pilot_verdict']}")

    rp = rf"D:\work\denning\results\raw\h1r-{ts}.result.json"
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"[h1r] result -> {rp}")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
