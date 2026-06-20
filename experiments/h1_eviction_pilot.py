#!/usr/bin/env python3
r"""
H1 core eviction pilot (experiments) — the tagged P0 make-or-break-A.

QUESTION (prereg H1'): under an adversarial VRAM-hog that drives Card B's DXGI
budget below the resident demand of a model that otherwise FITS, does VidMm
*involuntarily* demote the serving process's KV/weights to shared memory
(PDH `non_local` rises) and stall its decode — or does it protect the
foreground compute process and demote the hog instead?

DESIGN (Vulkan, per the blind-spot table — PDH reads cleanly here):
  baseline   : llama-bench tg on Card B, no hog            -> baseline tg t/s
  pressured  : hog holds N GB on Card B, llama-bench tg     -> pressured tg t/s
               (b70tools records non_local throughout)
  verdict    : pressured tg collapse + non_local rise  => H1 CONFIRMED
               tg unchanged + hog fails/demoted itself  => H1 REFUTED (VidMm
                                                            protects foreground)

SAFETY: the induced-pressure leg only runs with --arm-pressure. The safing
watchdog runs OBSERVER-ONLY (a non_local rise is the signal, not a fault); its
ABORT level (commit>=95%, phys>=29.5GB, TDR) still guards the real cascade. The
hog cap is bounded by --hog-cap-gb. Default (no --arm-pressure) is a baseline-
only scaffolding validation that touches no danger.

  # safe scaffolding check (no pressure):
  python experiments/h1_eviction_pilot.py --baseline-only
  # the real run (your go) — induce pressure, bounded hog:
  python experiments/h1_eviction_pilot.py --arm-pressure --hog-cap-gb 15
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

PY = sys.executable
LLAMA_BENCH = r"D:\work\llamacpp-b9279-vulkan\llama-bench.exe"
B70 = r"D:\work\b70tools\build\b70tools.exe"
HOG = os.path.join(os.path.dirname(__file__), "vram_hog.py")
WATCHDOG = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ops", "safing_watchdog.py")
PREFLIGHT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ops", "preflight.py")
DEFAULT_MODEL = r"D:\work\battlemage\models\Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf"

CARD_B_VK = "1"   # GGML_VK_VISIBLE_DEVICES -> Card B
CARD_B_XPU = "xpu:1"


def card_b_env() -> dict:
    e = dict(os.environ)
    e["GGML_VK_VISIBLE_DEVICES"] = CARD_B_VK
    return e


def preflight(model: str) -> bool:
    p = subprocess.run([PY, PREFLIGHT, "--model", model], text=True)
    return p.returncode == 0


def bench_tg(model: str, n: int, label: str) -> dict:
    """Run llama-bench tg on Card B; parse the tg t/s. Returns {label, tg_tps, raw}."""
    cmd = [LLAMA_BENCH, "-m", model, "-ngl", "99", "-p", "0", "-n", str(n), "-r", "2"]
    p = subprocess.run(cmd, capture_output=True, text=True, env=card_b_env(), timeout=600)
    tg = None
    for line in p.stdout.splitlines():
        if re.search(r"\btg\d", line) and "|" in line:
            # t/s is the last cell holding a float (robust to the ± encoding)
            for cell in reversed([c.strip() for c in line.split("|")]):
                m = re.search(r"([0-9]+\.[0-9]+)", cell)
                if m:
                    tg = float(m.group(1))
                    break
    return {"label": label, "tg_tps": tg, "raw_tail": "\n".join(p.stdout.splitlines()[-4:])}


def start_recorder(out_dir: str) -> subprocess.Popen:
    os.makedirs(out_dir, exist_ok=True)
    return subprocess.Popen(
        [B70, "run", "--ticks", "100000", "--cadence-ms", "500", "--flush-every-tick", "--out", out_dir],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=card_b_env(),
    )


def start_watchdog(log_path: str, b70_dir: str) -> subprocess.Popen:
    # observer-only (no --enforce): non_local rise is the H1 signal, not a kill trigger
    return subprocess.Popen(
        [PY, WATCHDOG, "--interval", "0.5", "--log", log_path, "--b70-dir", b70_dir],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def start_hog(cap_gb: float, hold_s: float) -> subprocess.Popen:
    return subprocess.Popen(
        [PY, HOG, "--device", CARD_B_XPU, "--cap-gb", str(cap_gb),
         "--step-gb", "2", "--hold-s", str(hold_s), "--step-pause-s", "0.5"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


def analyze(out_dir: str) -> dict:
    """Pull the worst non_local the recording saw, via b70tools verdict --json."""
    out = {"verdict_rc": None, "nonlocal_gb": None, "raw": None}
    try:
        p = subprocess.run([B70, "verdict", "--json", out_dir, "--window-s", "0"],
                           capture_output=True, text=True, timeout=30)
        out["verdict_rc"] = p.returncode
        txt = (p.stdout or "").strip()
        if txt:
            try:
                out["raw"] = json.loads(txt.splitlines()[-1])
            except (ValueError, IndexError):
                out["raw"] = txt.splitlines()[-1] if txt.splitlines() else None
    except (OSError, subprocess.TimeoutExpired) as e:
        out["error"] = str(e)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="H1 core eviction pilot")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--n", type=int, default=128, help="tokens to generate per bench")
    ap.add_argument("--arm-pressure", action="store_true",
                    help="ENABLE the induced-pressure leg (default: baseline-only, safe)")
    ap.add_argument("--baseline-only", action="store_true", help="explicit baseline-only")
    ap.add_argument("--hog-cap-gb", type=float, default=15.0)
    ap.add_argument("--hog-hold-s", type=float, default=60.0)
    ap.add_argument("--out", default=None, help="recording dir (default: D:\\work\\denning\\results\\raw\\h1-<ts>)")
    args = ap.parse_args()

    armed = args.arm_pressure and not args.baseline_only

    if not os.path.isfile(args.model):
        print(f"[h1] model missing: {args.model}", file=sys.stderr)
        return 2
    print(f"[h1] === preflight ===")
    if not preflight(args.model):
        print("[h1] NO-GO from preflight; aborting.", file=sys.stderr)
        return 1

    ts = int(time.time())
    out_dir = args.out or rf"D:\work\denning\results\raw\h1-{ts}"
    log_path = rf"D:\work\denning\results\raw\h1-{ts}.watchdog.jsonl"
    result = {"ts": ts, "model": os.path.basename(args.model), "armed": armed,
              "out_dir": out_dir, "engine": "Vulkan(GGML_VK_VISIBLE_DEVICES=1)"}

    rec = wd = hog = None
    try:
        print(f"[h1] === recorder + watchdog (observer) -> {out_dir} ===")
        rec = start_recorder(out_dir)
        time.sleep(2.0)
        wd = start_watchdog(log_path, out_dir)
        time.sleep(1.0)

        print(f"[h1] === baseline bench (no hog) ===")
        result["baseline"] = bench_tg(args.model, args.n, "baseline")
        print(f"[h1] baseline tg = {result['baseline']['tg_tps']} t/s")

        if armed:
            print(f"[h1] === ARMED: hog -> {args.hog_cap_gb} GB on Card B, then pressured bench ===")
            hog = start_hog(args.hog_cap_gb, args.hog_hold_s)
            # let the hog walk up to cap before benching under pressure
            time.sleep(min(args.hog_cap_gb / 2 * 0.5 + 4.0, 20.0))
            result["pressured"] = bench_tg(args.model, args.n, "pressured")
            print(f"[h1] pressured tg = {result['pressured']['tg_tps']} t/s")
            try:
                hog.terminate()
                hog.wait(timeout=15)
            except (subprocess.TimeoutExpired, OSError):
                hog.kill()
        else:
            print("[h1] baseline-only (pressure NOT armed). Scaffolding validated.")
    finally:
        for proc, name in ((hog, "hog"), (wd, "watchdog"), (rec, "recorder")):
            if proc and proc.poll() is None:
                try:
                    proc.terminate(); proc.wait(timeout=10)
                except (subprocess.TimeoutExpired, OSError):
                    proc.kill()

    print(f"[h1] === analyze recording ===")
    result["analysis"] = analyze(out_dir)

    # verdict
    if armed and result.get("baseline", {}).get("tg_tps") and result.get("pressured", {}).get("tg_tps"):
        b, p = result["baseline"]["tg_tps"], result["pressured"]["tg_tps"]
        result["tg_ratio_pressured_over_baseline"] = round(p / b, 3)
        print(f"[h1] tg ratio pressured/baseline = {result['tg_ratio_pressured_over_baseline']} "
              f"(<<1 + non_local rise => H1 CONFIRMED; ~1 => VidMm protected foreground)")

    res_path = rf"D:\work\denning\results\raw\h1-{ts}.result.json"
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"[h1] result -> {res_path}")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
