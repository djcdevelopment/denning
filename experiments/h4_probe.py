#!/usr/bin/env python3
r"""H4 probe — confirm the REAL hit/miss prefill cost via llama-server prefix caching.

A cache HIT (the prefix KV is resident in the slot) re-prefills only the new suffix
-> cheap. A MISS (the prefix was evicted) re-prefills the whole prefix -> the real
refetch/recompute stall (R1). `timings.prompt_ms` from the server IS that cost.
This validates the mechanism the on-rig H4 arena is built on.
"""

import json
import sys
import urllib.request

from h1_eviction_pilot import DEFAULT_MODEL
from h1_resident_pilot import wait_health, _kill
from i4b_closed_loop import start_server_np, PORT

BASE = ("The denning project studies LLM KV-cache residency and admission control "
        "on Intel Arc GPUs under Windows VidMm. ")


def post(prompt, id_slot, n_predict=1):
    body = json.dumps({"prompt": prompt, "n_predict": n_predict, "cache_prompt": True,
                       "id_slot": id_slot, "temperature": 0}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/completion", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        o = json.load(r)
    t = o.get("timings", {})
    return t.get("prompt_n"), round(t.get("prompt_ms", 0.0), 1)


def main():
    sysA = "System prompt A. " + BASE * 200          # ~ a few thousand tokens (shared prefix)
    sysB = "System prompt B. " + BASE.replace("denning", "alpha").replace("Arc", "Xe") * 200
    srv = start_server_np(DEFAULT_MODEL, PORT, 2, 16384)
    try:
        if not wait_health(PORT, 240):
            print("health timeout"); return 2
        n1, c1 = post(sysA + " Question one?", 0)     # cold: prefill all of A
        n2, c2 = post(sysA + " Question two?", 0)     # cached HIT: only the new suffix
        n3, c3 = post(sysB + " Question three?", 0)   # evict slot 0 with B
        n4, c4 = post(sysA + " Question four?", 0)    # MISS: A evicted -> re-prefill A
        print(json.dumps({
            "cold_A":  {"prefill_tokens": n1, "prefill_ms": c1},
            "hit_A":   {"prefill_tokens": n2, "prefill_ms": c2},
            "evict_B": {"prefill_tokens": n3, "prefill_ms": c3},
            "miss_A":  {"prefill_tokens": n4, "prefill_ms": c4},
        }, indent=2))
    finally:
        _kill(srv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
