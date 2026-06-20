#!/usr/bin/env python3
r"""S1 swap probe -- does llama-server slot save/restore give a real refetch path?

Cold-prefill a conversation (recompute), SAVE its KV to disk, evict it, then RESTORE
the bytes (refetch) and verify it's resident again. Compares restore time (refetch)
vs cold-prefill time (recompute) on REAL KV -> R1 on real bytes, and reports the KV
file size (the per-token footprint, R2/R3). Needs the server started with
--slot-save-path. Validates the mechanism for the S1 swap arena.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

from h1_eviction_pilot import DEFAULT_MODEL, card_b_env
from h1_resident_pilot import wait_health, _kill

PORT = 8233
LLAMA_SERVER = r"D:\work\llamacpp-b9279-vulkan\llama-server.exe"
SLOT_DIR = r"D:\tmp\slots"
FILLER = "The denning project studies KV residency and admission control on Arc GPUs. "


def start_server(slots=2, ctx=16384):
    os.makedirs(SLOT_DIR, exist_ok=True)
    return subprocess.Popen(
        [LLAMA_SERVER, "-m", DEFAULT_MODEL, "-ngl", "99", "--host", "127.0.0.1",
         "--port", str(PORT), "-np", str(slots), "-c", str(ctx), "--slot-save-path", SLOT_DIR],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=card_b_env())


def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            o = json.load(r)
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read().decode("utf-8", "replace")[:300]}, \
               round((time.perf_counter() - t0) * 1000, 1)
    return o, round((time.perf_counter() - t0) * 1000, 1)


def prefill(prompt, slot):
    o, _ = post("/completion", {"prompt": prompt, "n_predict": 1, "cache_prompt": True,
                                "id_slot": slot, "temperature": 0})
    t = o.get("timings", {})
    return round(t.get("prompt_ms", 0.0), 1), t.get("prompt_n", 0)


def main():
    A = "Conversation A. " + FILLER * 250                      # ~4.5k tokens
    B = "Conversation B. " + FILLER.replace("denning", "beta") * 250
    srv = start_server()
    try:
        if not wait_health(PORT, 240):
            print(json.dumps({"error": "health_timeout"})); return 2
        cold_ms, cold_n = prefill(A + " Q1?", 0)               # recompute A into slot 0
        save_resp, save_wall = post("/slots/0?action=save", {"filename": "convA.bin"})
        prefill(B + " Q2?", 0)                                 # evict A (B overwrites slot 0)
        restore_resp, restore_wall = post("/slots/0?action=restore", {"filename": "convA.bin"})
        hit_ms, hit_n = prefill(A + " Q3?", 0)                 # verify: A resident -> only Q3 prefills
        fp = os.path.join(SLOT_DIR, "convA.bin")
        fsize = os.path.getsize(fp) if os.path.exists(fp) else None
        out = {
            "cold_prefill_ms": cold_ms, "cold_prefill_tokens": cold_n,
            "save_resp": save_resp, "save_wall_ms": save_wall,
            "restore_resp": restore_resp, "restore_wall_ms": restore_wall,
            "verify_hit_ms": hit_ms, "verify_hit_tokens": hit_n,
            "kv_file_bytes": fsize,
            "kv_file_gb": round(fsize / 2**30, 3) if fsize else None,
            "R1_recompute_over_refetch": (round(cold_ms / restore_wall, 1)
                                          if restore_wall else None),
        }
        print(json.dumps(out, indent=2))
    finally:
        _kill(srv)
    return 0


if __name__ == "__main__":
    import urllib.error  # noqa
    sys.exit(main())
