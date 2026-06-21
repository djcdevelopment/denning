#!/usr/bin/env python3
r"""C1 -- restore-vs-re-prefill TTFT at depth (the Step-1 keystone).

For each context depth d, compare:
  * COLD re-prefill TTFT  -- evict, then prefill a ~d-token prompt from scratch
                            (this is what a stock engine pays when the hot prefix
                             was evicted by a co-tenant);
  * RESTORE TTFT          -- save that KV to host/disk, evict, restore it, and take
                            the first token (restore_ms + first-token compute).

The thesis (cost-model R1, the "29x"): restore_total << cold_reprefill, and the gap
widens with depth. Refuted if restore is not dramatically cheaper at 64k.

Spawns its OWN llama-server with -fa -ctk q8_0 -ctv q8_0 (so 64k KV fits a 32GB
B70), then drives it through the unmodified LlamaCppAdapter HTTP methods. Pinned to
B70 #1 (Vulkan dev 1); device 0 (the 2070) is never touched.

  python experiments/c1_restore_vs_reprefill.py            # depths 16k,32k,64k
  python experiments/c1_restore_vs_reprefill.py 2048       # smoke at one small depth
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, r"D:\work\denning")
from denning.engine.llamacpp import LlamaCppAdapter, DEFAULT_BINARY, DEFAULT_MODEL  # noqa: E402

HOST = "127.0.0.1"
PORT = int(os.environ.get("C1_PORT", "8260"))
DEVICE = int(os.environ.get("C1_DEVICE", "1"))   # B70 #1 default; NEVER 0 (the 2070 display card)
SLOT_DIR = r"D:\tmp\slots"
CTX = 73728                      # 72k: covers the 64k depth + headroom; q8 KV ~7GB + model ~18.5GB
OUT = r"D:\work\denning\results\raw\battery-C1.json"
DEPTHS = [16384, 32768, 65536]

# ~55-token paragraph; repeated to approximate a target depth.
PARA = ("Virtual memory decouples the address space a process sees from physical RAM; "
        "the operating system translates pages through the TLB and multi-level page "
        "tables, and under memory pressure the page-replacement policy evicts frames by "
        "working-set and page-fault-frequency models rather than by simple recency. ")


def spawn_q8() -> subprocess.Popen:
    env = dict(os.environ)
    env["GGML_VK_VISIBLE_DEVICES"] = str(DEVICE)   # hide every other device incl. the 2070
    os.makedirs(SLOT_DIR, exist_ok=True)
    argv = [DEFAULT_BINARY, "-m", DEFAULT_MODEL, "-ngl", "99", "--host", HOST,
            "--port", str(PORT), "-np", "1", "-c", str(CTX), "-fa", "on",
            "-ctk", "q8_0", "-ctv", "q8_0", "--slot-save-path", SLOT_DIR]
    return subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)


def build_prompt(approx_tokens: int) -> str:
    return PARA * max(1, approx_tokens // 55)


def count_tokens(prompt: str) -> int:
    req = urllib.request.Request(
        f"http://{HOST}:{PORT}/tokenize", data=json.dumps({"content": prompt}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return len(json.loads(r.read()).get("tokens", []))
    except Exception:
        return -1


def main() -> int:
    depths = [int(x) for x in sys.argv[1:]] or DEPTHS
    if DEVICE == 0:
        print(json.dumps({"refused": "device 0 is the 2070 display card -- never serve on it"}))
        return 2
    a = LlamaCppAdapter()
    proc = spawn_q8()
    results = []
    try:
        if not a.health(PORT, 600):
            print(json.dumps({"error": "health_timeout"})); return 2
        a.stream(PORT, "warmup", 8, slot=0, label="warmup")
        for d in depths:
            prompt = build_prompt(d)
            ntok = count_tokens(prompt)
            a.evict_slot(PORT, 0)
            cold = a.stream(PORT, prompt, 1, slot=0, cache_prompt=True, label=f"cold{d}", timeout_s=1800)
            fn = f"c1_d{d}.bin"
            save_ms = a.save_kv(PORT, 0, fn)
            a.evict_slot(PORT, 0)
            restore_ms = a.restore_kv(PORT, 0, fn)
            warm = a.stream(PORT, prompt, 1, slot=0, cache_prompt=True, label=f"warm{d}", timeout_s=1800)
            cold_ttft = cold.ttft_ms or 0.0
            warm_ttft = warm.ttft_ms or 0.0
            restore_total = round(restore_ms + warm_ttft, 1)
            row = {"target_depth": d, "actual_tokens": ntok,
                   "cold_reprefill_ttft_ms": cold_ttft,
                   "save_ms": round(save_ms, 1), "restore_ms": round(restore_ms, 1),
                   "restore_first_tok_ms": warm_ttft, "restore_total_ms": restore_total,
                   "speedup_x": round(cold_ttft / restore_total, 2) if restore_total else None,
                   "cold_err": cold.error, "warm_err": warm.error}
            results.append(row)
            print(json.dumps(row))
            try:
                os.remove(os.path.join(SLOT_DIR, fn))   # reclaim the KV file (can be GBs)
            except OSError:
                pass
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("C1 DONE ->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
