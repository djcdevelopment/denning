#!/usr/bin/env python3
r"""LlamaCppAdapter -- the llama.cpp engine adapter for denning (S-shim-1).

Consolidates the engine-specific primitives proven in the experiment harnesses
into the single EngineAdapter surface (docs/denning-as-shim.md §4):

  * spawn_replica / health / stream  <- experiments/h4_twocard.py + h1_resident_pilot.py
  * save_kv / restore_kv / evict_slot <- experiments/h4_swap_arena.py (the S1 seam)

This is the ONLY engine-specific code in denning. The control plane (budget-reader,
admission, replica-router, lifetime-class arena) imports base.EngineAdapter and
never names llama.cpp. Adding vLLM-XPU or ExLlamaV3 is a sibling file, nothing else.

  python -m denning.engine.llamacpp --dry-run               # no GPU: print plan + check paths
  python -m denning.engine.llamacpp --smoke --device 1      # on-rig: spawn->stream->save->evict->restore->stream->stop
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

from denning.engine.base import EngineAdapter, ReplicaHandle, SessionStats

# Defaults match the validated harnesses (experiments/h1_eviction_pilot.py).
DEFAULT_BINARY = r"D:\work\llamacpp-b9279-vulkan\llama-server.exe"
DEFAULT_MODEL = r"D:\work\battlemage\models\Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf"
DEFAULT_SLOT_DIR = r"D:\tmp\slots"


class LlamaCppAdapter:
    """EngineAdapter over an unmodified llama-server (Vulkan backend, Windows)."""

    def __init__(self, binary: str = DEFAULT_BINARY, model: str = DEFAULT_MODEL,
                 slot_dir: str = DEFAULT_SLOT_DIR, host: str = "127.0.0.1",
                 device_env: str = "GGML_VK_VISIBLE_DEVICES"):
        self.binary = binary
        self.model = model
        self.slot_dir = slot_dir
        self.host = host
        self.device_env = device_env

    # --- lifecycle ---------------------------------------------------------
    def spawn_replica(self, device: int, port: int, slots: int, ctx: int) -> ReplicaHandle:
        os.makedirs(self.slot_dir, exist_ok=True)
        env = dict(os.environ)
        env[self.device_env] = str(device)   # pin this replica to one card
        proc = subprocess.Popen(
            [self.binary, "-m", self.model, "-ngl", "99", "--host", self.host,
             "--port", str(port), "-np", str(slots), "-c", str(ctx),
             "--slot-save-path", self.slot_dir],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        return ReplicaHandle(device=device, port=port, slots=slots, ctx=ctx, proc=proc)

    def replica_argv(self, device: int, port: int, slots: int, ctx: int) -> list[str]:
        """The exact command spawn_replica would run (for --dry-run / logging)."""
        return [self.binary, "-m", self.model, "-ngl", "99", "--host", self.host,
                "--port", str(port), "-np", str(slots), "-c", str(ctx),
                "--slot-save-path", self.slot_dir]

    def health(self, port: int, timeout_s: float = 300.0) -> bool:
        url = f"http://{self.host}:{port}/health"
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            try:
                with urllib.request.urlopen(url, timeout=3) as r:
                    if r.status == 200:
                        return True
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(1.0)
        return False

    def stop(self, handle: ReplicaHandle) -> None:
        p = handle.proc if handle else None
        if p and p.poll() is None:
            try:
                p.terminate(); p.wait(timeout=10)
            except (subprocess.TimeoutExpired, OSError):
                p.kill()

    # --- serving -----------------------------------------------------------
    def stream(self, port: int, prompt: str, n_predict: int, *, slot: int = -1,
               cache_prompt: bool = False, temperature: float = 0.7,
               label: str = "s") -> SessionStats:
        body = {"prompt": prompt, "n_predict": n_predict, "stream": True,
                "cache_prompt": cache_prompt, "temperature": temperature}
        if slot >= 0:
            body["id_slot"] = slot
        req = urllib.request.Request(
            f"http://{self.host}:{port}/completion", data=json.dumps(body).encode(),
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
            return SessionStats(label=label, tokens=len(times), error=str(e))
        if len(times) < 2:
            return SessionStats(label=label, tokens=len(times), error="too few tokens")
        deltas = [times[i] - times[i - 1] for i in range(1, len(times))]
        return SessionStats(
            label=label, tokens=len(times),
            ttft_ms=round((times[0] - t0) * 1000, 1),
            tbt_median_ms=round(statistics.median(deltas) * 1000, 2),
            tbt_p95_ms=round(sorted(deltas)[max(0, int(0.95 * len(deltas)) - 1)] * 1000, 2),
            decode_tps=round((len(times) - 1) / (times[-1] - times[0]), 2))

    # --- the KV-residency seam ---------------------------------------------
    def _slot_action(self, port: int, slot: int, action: str, body: dict) -> float:
        req = urllib.request.Request(
            f"http://{self.host}:{port}/slots/{slot}?action={action}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=300) as r:
            r.read()
        return (time.perf_counter() - t0) * 1000

    def save_kv(self, port: int, slot: int, filename: str) -> float:
        return self._slot_action(port, slot, "save", {"filename": filename})

    def restore_kv(self, port: int, slot: int, filename: str) -> float:
        return self._slot_action(port, slot, "restore", {"filename": filename})

    def evict_slot(self, port: int, slot: int) -> None:
        self._slot_action(port, slot, "erase", {})


# --- self-checks -----------------------------------------------------------
def _dry_run(a: LlamaCppAdapter) -> int:
    print("[dry-run] LlamaCppAdapter wiring check (no GPU)\n")
    argv = a.replica_argv(device=1, port=8240, slots=2, ctx=8192)
    print("  spawn_replica(device=1, port=8240, slots=2, ctx=8192) would exec:")
    print("    " + " ".join(argv) + "\n")
    paths = [("binary", a.binary), ("model", a.model)]
    ok = True
    for name, p in paths:
        exists = os.path.exists(p)
        ok = ok and exists
        print(f"  [{'OK ' if exists else 'MISSING'}] {name}: {p}")
    parent = os.path.dirname(a.slot_dir) or "."
    wok = os.path.isdir(parent) or os.path.isdir(a.slot_dir)
    print(f"  [{'OK ' if wok else 'MISSING'}] slot-dir parent writable: {parent}")
    assert isinstance(a, EngineAdapter), "LlamaCppAdapter must satisfy EngineAdapter"
    print("\n  [OK ] LlamaCppAdapter satisfies the EngineAdapter protocol")
    print("\n[dry-run] " + ("READY" if ok and wok else "paths missing (fine off-rig)"))
    return 0


def _smoke(a: LlamaCppAdapter, device: int, port: int) -> int:
    r"""On-rig: exercise every adapter method against a live replica, bounded."""
    prompt = ("Explain virtual memory, demand paging, the TLB, and page replacement "
              "in a few precise paragraphs.")
    out = {"device": device, "port": port}
    h = a.spawn_replica(device=device, port=port, slots=2, ctx=8192)
    try:
        if not a.health(port, 300):
            print(json.dumps({**out, "error": "health_timeout"})); return 2
        a.stream(port, "warmup", 8, slot=0, label="warmup")
        # populate KV on slot 0 (cache_prompt so the prefix stays resident)
        cold = a.stream(port, prompt, 16, slot=0, cache_prompt=True, label="cold")
        save_ms = a.save_kv(port, 0, "smoke.bin")
        a.evict_slot(port, 0)
        restore_ms = a.restore_kv(port, 0, "smoke.bin")
        warm = a.stream(port, prompt, 16, slot=0, cache_prompt=True, label="warm")
        out.update(
            health=True,
            cold_decode_tps=cold.decode_tps, cold_ttft_ms=cold.ttft_ms,
            save_ms=round(save_ms, 1), restore_ms=round(restore_ms, 1),
            warm_decode_tps=warm.decode_tps, warm_ttft_ms=warm.ttft_ms,
            seam_ok=(save_ms > 0 and restore_ms > 0 and warm.ok))
    finally:
        a.stop(h)
    print(json.dumps(out, indent=2))
    return 0 if out.get("seam_ok") else 3


def main() -> int:
    ap = argparse.ArgumentParser(description="llama.cpp EngineAdapter (S-shim-1)")
    ap.add_argument("--dry-run", action="store_true", help="no-GPU wiring + path check")
    ap.add_argument("--smoke", action="store_true", help="on-rig: spawn + full seam round-trip")
    ap.add_argument("--device", type=int, default=1, help="GPU index (1 = Card B/compute)")
    ap.add_argument("--port", type=int, default=8240)
    ap.add_argument("--binary", default=DEFAULT_BINARY)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()
    a = LlamaCppAdapter(binary=args.binary, model=args.model)
    if args.smoke:
        return _smoke(a, args.device, args.port)
    return _dry_run(a)


if __name__ == "__main__":
    sys.exit(main())
