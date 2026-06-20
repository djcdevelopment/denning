#!/usr/bin/env python3
r"""Swap-cost characterization -- refetch (restore) vs recompute (re-prefill) vs KV size.

Sweeps context size; for each: cold-prefill (recompute), save the KV, evict, restore
(refetch). Reports the restore bandwidth and the R1 ratio across the range -- the
quantitative backbone of the swap lever (S1) for the cost model and the paper.
Needs the server with --slot-save-path.
"""

import json
import os
import subprocess
import sys
import urllib.request

from h1_eviction_pilot import DEFAULT_MODEL, card_b_env
from h1_resident_pilot import wait_health, _kill

PORT = 8235
LLAMA_SERVER = r"D:\work\llamacpp-b9279-vulkan\llama-server.exe"
SLOT_DIR = r"D:\tmp\slots"
FILLER = "The denning project studies KV residency and admission control on Arc GPUs. "


def start_server():
    os.makedirs(SLOT_DIR, exist_ok=True)
    return subprocess.Popen(
        [LLAMA_SERVER, "-m", DEFAULT_MODEL, "-ngl", "99", "--host", "127.0.0.1",
         "--port", str(PORT), "-np", "2", "-c", "40960", "--slot-save-path", SLOT_DIR],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=card_b_env())


def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def prefill(prompt, slot):
    o = post("/completion", {"prompt": prompt, "n_predict": 1, "cache_prompt": True,
                             "id_slot": slot, "temperature": 0})
    t = o.get("timings", {})
    return t.get("prompt_ms", 0.0), t.get("prompt_n", 0)


def main():
    srv = start_server()
    rows = []
    try:
        if not wait_health(PORT, 240):
            print(json.dumps({"error": "health_timeout"})); return 2
        for ctx in [1000, 2000, 4000, 8000, 16000]:
            prompt = f"Ctx{ctx}. " + FILLER * (ctx // 16)
            prefill(f"reset {ctx}", 1)                              # keep slot 1 busy/distinct
            rp_ms, rp_n = prefill(prompt + " Q?", 0)               # RECOMPUTE (cold prefill)
            sv = post("/slots/0?action=save", {"filename": f"sw{ctx}.bin"})
            sv_ms = sv.get("timings", {}).get("save_ms", 0.0)
            nb = sv.get("n_written", 0)
            prefill("evict " + ("x" * 60), 0)                      # evict slot 0
            rs = post("/slots/0?action=restore", {"filename": f"sw{ctx}.bin"})
            rs_ms = rs.get("timings", {}).get("restore_ms", 0.0)
            gb = nb / 2**30
            rows.append({
                "ctx_tok": rp_n, "reprefill_ms": round(rp_ms, 0), "save_ms": round(sv_ms, 1),
                "restore_ms": round(rs_ms, 1), "kv_gb": round(gb, 3),
                "restore_GBps": round(gb / (rs_ms / 1000), 1) if rs_ms else None,
                "R1_x": round(rp_ms / rs_ms, 1) if rs_ms else None,
            })
    finally:
        _kill(srv)

    print(f"{'ctx_tok':>8} {'reprefill_ms':>12} {'restore_ms':>11} {'kv_GB':>7} {'restore_GB/s':>12} {'R1_x':>6}")
    for r in rows:
        print(f"{r['ctx_tok']:>8} {r['reprefill_ms']:>12.0f} {r['restore_ms']:>11.1f} "
              f"{r['kv_gb']:>7.3f} {r['restore_GBps']:>12.1f} {r['R1_x']:>6.1f}")
    print(json.dumps(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
