#!/usr/bin/env python3
r"""denningd -- the co-residency control loop over an unmodified engine (S-shim-2).

Wires the four control-plane pieces onto an EngineAdapter:

    client session
        |  route (round-robin across replica-per-card)            [router]
        v
    admission on the LIVE VidMm budget: admit iff in-flight <= N* [budget + admission]
        |  (reject/queue if the OS shrank the budget under a co-tenant)
        v
    lifetime-class KV arena per replica: hit / restore / prefill  [arena]
        |  (the adapter moves the KV bytes; the arena picks what)
        v
    adapter.stream(port, slot) -> SessionStats                    [engine]

The engine underneath is unmodified (one llama-server replica per card today). This
file names no engine -- only EngineAdapter -- so vLLM-XPU / ExLlamaV3 drop in by
swapping the adapter. Programmatic API now (`Daemon.handle`); an OpenAI-compatible
HTTP front is a thin wrapper on top (S-shim-2, next).

  python -m denning.denningd --dry-run                  # no GPU: wiring over a fake engine
  python -m denning.denningd --serve --cards 2 --n 16   # on-rig: real replicas, N sessions
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from denning.control import budget as budgetmod
from denning.control.admission import CARD_BUDGET_GB, AdmissionController
from denning.control.arena import LifetimeClassArena
from denning.control.router import ReplicaRouter
from denning.engine.base import EngineAdapter


@dataclass
class Replica:
    device: int
    port: int
    handle: object
    arena: LifetimeClassArena


class Daemon:
    def __init__(self, adapter: EngineAdapter, devices, base_port: int = 8240,
                 slots: int = 8, ctx: int = 2048, policy: str = "classes",
                 swap: bool = True, controller: AdmissionController = None,
                 live_budget: bool = True, nominal_budget_gb: float = CARD_BUDGET_GB,
                 display_device: int = 0, display_cap: int = 0):
        self.adapter = adapter
        self.devices = list(devices)
        self.base_port = base_port
        self.slots = slots
        self.ctx = ctx
        self.policy = policy
        self.swap = swap
        self.controller = controller or AdmissionController()
        self.live_budget = live_budget
        self.nominal_budget_gb = nominal_budget_gb
        # The display card (device 0) drives the desktop compositor. On this rig,
        # serving inference on it does NOT degrade gracefully: ONE session already
        # produced no tokens and TWO hard-hung the whole box (no TDR recovery, manual
        # reboot, 2026-06-20 -- results/display-card-hardhang-20260620.md). So the
        # default is display_cap=0 = the display card SERVES NOTHING; only headless
        # cards serve. `display_device=None` means "no display card here, serve all".
        self.display_device = display_device
        self.display_cap = display_cap
        self.device_caps = {d: (display_cap if d == display_device else None)
                            for d in self.devices}
        # cap == 0 => reserved, never spawned, never routed to.
        self.serving_devices = [d for d in self.devices if self.device_caps.get(d) != 0]
        self.ports = [base_port + d for d in self.serving_devices]
        self._port_device = {base_port + d: d for d in self.serving_devices}
        self.router = ReplicaRouter(self.ports)
        self.replicas: dict = {}
        self.conv_card: dict = {}        # conv -> device (session affinity)
        self.rejected = 0
        self._rr = 0
        self._lock = threading.Lock()    # guards the fast routing/arena bookkeeping
        self._budget_cache: dict = {}    # device -> (gb, t); filled by the background poller
        self._budget_ttl = 2.0
        self._budget_stop = threading.Event()
        self._budget_thread = None

    # --- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        for d in self.serving_devices:          # cap-0 (display) devices are never spawned
            port = self.base_port + d
            h = self.adapter.spawn_replica(d, port, self.slots, self.slots * self.ctx)
            if not self.adapter.health(port, 300):
                raise RuntimeError(f"replica on device {d} (port {port}) unhealthy")
            self.adapter.stream(port, "warmup", 8, slot=0, label="warmup")
            self.replicas[d] = Replica(
                device=d, port=port, handle=h,
                arena=LifetimeClassArena(self.adapter, port, self.slots, self.policy, self.swap))
        if self.live_budget:
            for d in self.serving_devices:
                self._refresh_budget(d)              # warm once before serving
            self._budget_stop.clear()
            self._budget_thread = threading.Thread(target=self._budget_poller, daemon=True)
            self._budget_thread.start()

    def stop(self) -> None:
        self._budget_stop.set()
        if self._budget_thread is not None:
            self._budget_thread.join(timeout=5)
        for rep in self.replicas.values():
            self.adapter.stop(rep.handle)

    # --- control loop ------------------------------------------------------
    def _route(self, conv) -> int:
        """Session affinity: a conversation returns to the card holding its KV
        (resident or saved), so multi-turn convs hit/restore instead of re-prefilling.
        New conversations are round-robined across the replicas."""
        if conv in self.conv_card:
            port = self.base_port + self.conv_card[conv]
        else:
            port = self.ports[self._rr % len(self.ports)]
            self._rr += 1
            self.conv_card[conv] = self._port_device[port]
        self.router.reserve(port)
        return port

    def _refresh_budget(self, device: int) -> None:
        b = budgetmod.read_live_budget_gb(device)
        self._budget_cache[device] = (b if b is not None else self.nominal_budget_gb, time.time())

    def _budget_poller(self) -> None:
        """Refresh the live VidMm budget OFF the request path. The D3D12 probe shells out
        (~1 s with --hold-s); calling it per-request under concurrency caused a probe
        stampede that inflated E2EL ~18 s (caught by bench.py). Poll once per TTL instead."""
        while not self._budget_stop.wait(self._budget_ttl):
            for d in self.serving_devices:
                try:
                    self._refresh_budget(d)
                except Exception:
                    pass

    def _budget(self, device: int) -> float:
        """Live VidMm budget -- a fast read of the background-polled cache (NEVER probes on
        the request path). Falls back to nominal until the first poll lands."""
        if not self.live_budget:
            return self.nominal_budget_gb
        cached = self._budget_cache.get(device)
        return cached[0] if cached else self.nominal_budget_gb

    def handle(self, conv, prompt: str, n_predict: int = 64) -> dict:
        # The live budget is kept warm by the background poller, so this is a fast cache
        # read; route + admit + slot-assign under the lock (in-memory), the stream runs free.
        with self._lock:
            port = self._route(conv)
            device = self._port_device[port]
            budget = self._budget(device)           # cache hit (warmed above)
            cap = self.controller.capacity(budget)
            dcap = self.device_caps.get(device)     # asymmetric: clamp the display card
            if dcap is not None:
                cap = min(cap, dcap)
            if self.router.inflight[port] > cap:    # over N* for the live budget -> shed
                self.router.release(port)
                self.rejected += 1
                return {"conv": conv, "admitted": False, "device": device, "port": port,
                        "budget_gb": round(budget, 2), "capacity": cap,
                        "reason": "over N* for live budget"}
            rep = self.replicas[device]
            slot, action = rep.arena.access(conv)   # KV move via adapter, per-replica serialized
        try:
            stats = self.adapter.stream(port, prompt, n_predict, slot=slot,
                                        cache_prompt=True, label=f"conv{conv}")
            return {"conv": conv, "admitted": True, "device": device, "port": port,
                    "slot": slot, "action": action, "budget_gb": round(budget, 2),
                    "capacity": cap, "ttft_ms": stats.ttft_ms,
                    "tbt_median_ms": stats.tbt_median_ms, "decode_tps": stats.decode_tps,
                    "tpot_ms": stats.tbt_median_ms, "e2el_ms": stats.e2el_ms,
                    "itl_ms": stats.itl_ms, "tokens": stats.tokens}
        finally:
            with self._lock:
                self.router.release(port)

    def handle_many(self, sessions, max_workers: int = None) -> list:
        """Serve (conv, prompt, n_predict) tuples concurrently across the replicas."""
        mw = max_workers or max(1, len(sessions))
        with ThreadPoolExecutor(max_workers=mw) as ex:
            futs = [ex.submit(self.handle, c, p, n) for (c, p, n) in sessions]
            return [f.result() for f in futs]

    def stats(self) -> dict:
        return {"devices": self.devices, "rejected": self.rejected,
                "router_load": self.router.load(),
                "replicas": {d: rep.arena.stats() for d, rep in self.replicas.items()}}


# --- CLI -------------------------------------------------------------------
def _dry_run() -> int:
    """Wire the daemon over a fake engine (no GPU) and serve a tiny round-robin batch."""
    from tests.test_shim import FakeAdapter
    # display_device=None: no real display here (FakeAdapter), so both cards serve and
    # the routing demo still shows 2-card behavior. On-rig, device 0 is excluded.
    d = Daemon(FakeAdapter(), devices=[0, 1], slots=4, live_budget=False,
               nominal_budget_gb=CARD_BUDGET_GB, display_device=None)
    d.start()
    out = [d.handle(c, f"turn for conv {c}", 16) for c in [1, 2, 1, 3, 2, 4]]
    d.stop()
    for r in out:
        print(f"  conv {r['conv']}: card {r['device']} slot {r.get('slot')} "
              f"{r.get('action'):>7}  admitted={r['admitted']}")
    print("\n  stats:", json.dumps(d.stats()))
    print("\n[dry-run] daemon wiring OK")
    return 0


def _watchdog_path() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "ops", "safing_watchdog.py")


def _serve(cards: int, n: int, display_cap: int = 0, guard_on: bool = True,
           watchdog_on: bool = True, devices_override=None) -> int:
    from collections import Counter

    from denning.control.tdr_guard import TdrGuard
    from denning.engine.llamacpp import LlamaCppAdapter
    # Topology after adding the RTX 2070 SUPER as the display card (2026-06-20):
    #   Vulkan0 = 2070 SUPER (DISPLAY, 8 GB) -- never serve here; Vulkan1/2 = the two
    #   headless B70s (32 GB each). So the serving cards are [1] and [1, 2], NOT [0, 1].
    devices = devices_override if devices_override else ([1] if cards == 1 else [1, 2])
    prompt = ("Explain virtual memory, demand paging, the TLB, and page replacement "
              "in a few precise paragraphs.")

    guard = TdrGuard() if guard_on else None
    tdr_before = guard.arm() if guard else None     # snapshot the display-TDR count

    wd = None
    if watchdog_on:                                  # I-1 safing watchdog as observer
        wd_log = r"D:\work\denning\results\raw\denningd-serve.watchdog.jsonl"
        try:
            wd = subprocess.Popen([sys.executable, _watchdog_path(), "--interval", "3",
                                   "--watch-tdr", "--log", wd_log],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            wd = None

    d = Daemon(LlamaCppAdapter(), devices=devices, slots=8, ctx=2048, policy="classes",
               swap=True, live_budget=True, display_device=0, display_cap=display_cap)
    d.start()
    try:
        sessions = [(i, prompt, 64) for i in range(n)]    # N distinct concurrent sessions
        res = d.handle_many(sessions, max_workers=n)
    finally:
        d.stop()
        if wd and wd.poll() is None:
            wd.terminate()
            try:
                wd.wait(timeout=5)
            except subprocess.TimeoutExpired:
                wd.kill()

    admitted = [r for r in res if r["admitted"]]
    met = [r for r in admitted if (r.get("tbt_median_ms") or 1e9) <= 50.0]
    by_card = Counter(r["device"] for r in admitted)
    tbts = sorted(r["tbt_median_ms"] for r in admitted if r.get("tbt_median_ms"))
    tdr_after = guard.current() if guard else None
    clean = guard.clean() if guard else None
    out = {"cards": cards, "n": n, "display_cap": display_cap,
           "serving_devices": d.serving_devices,
           "display_card_excluded": d.display_device not in d.serving_devices,
           "admitted": len(admitted), "slo_met": len(met), "rejected": d.rejected,
           "by_card": dict(by_card),
           "tbt_median_ms": tbts[len(tbts) // 2] if tbts else None,
           "agg_decode_tps": round(sum(r.get("decode_tps") or 0 for r in admitted), 1),
           "tdr_before": tdr_before, "tdr_after": tdr_after, "tdr_clean": clean}
    if clean is False:
        out["UNSAFE"] = ("display-driver TDR DURING this run -- result is contaminated, "
                         "DO NOT report (raise --cards/--display-cap headroom)")
    print(json.dumps(out, indent=2))
    return 4 if clean is False else 0


SWEEP_LOG = r"D:\work\denning\results\raw\display-cap-sweep.jsonl"


def _append_durable(path: str, obj: dict) -> None:
    """Write one JSON line and flush+fsync immediately -- the ceiling step will likely
    reset the display and may kill the terminal, so every step must survive on disk."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass


def _sweep(max_cap: int = 8, sweep_cards: int = 1, dry: bool = False,
           force: bool = False) -> int:
    r"""Ramp display-card (device 0) concurrency under the TDR guard. SUPERSEDED: the run
    of 2026-06-20 answered this -- device 0 hard-hangs (cap=1 produced no tokens, cap=2
    locked the box, manual reboot, NO TDR recovery so the guard was blind). The display
    card serves nothing; the safe cap is 0. This refuses to touch device 0 unless --dry-run
    (FakeAdapter, no GPU) or an explicit --force-display-unsafe (do not)."""
    if not dry and not force:
        print(json.dumps({
            "refused": "Display-card serving HARD-HANGS this rig -- known result, do not re-run.",
            "evidence": "cap=1 no tokens, cap=2 locked the box + manual reboot 2026-06-20; "
                        "no Event-4101 recovery (guard cannot see a hard hang).",
            "safe_policy": "display_cap=0 (display card serves nothing); serve on Card B only.",
            "see": "results/display-card-hardhang-20260620.md",
            "override": "--force-display-unsafe (NOT recommended; risks another hard reboot)"}, indent=2))
        return 0
    from denning.control.tdr_guard import TdrGuard
    prompt = ("Explain virtual memory, demand paging, the TLB, and page replacement "
              "in a few precise paragraphs.")
    if dry:
        from tests.test_shim import FakeAdapter
        adapter, watchdog_on = FakeAdapter(), False
    else:
        from denning.engine.llamacpp import LlamaCppAdapter
        adapter, watchdog_on = LlamaCppAdapter(), True
    devices = [0] if sweep_cards == 1 else [0, 1]

    guard = TdrGuard()
    wd = None
    if watchdog_on:
        try:
            wd = subprocess.Popen([sys.executable, _watchdog_path(), "--interval", "3",
                                   "--watch-tdr", "--log",
                                   r"D:\work\denning\results\raw\display-sweep.watchdog.jsonl"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            wd = None

    d = Daemon(adapter, devices=devices, slots=max_cap, ctx=2048, policy="classes",
               swap=True, live_budget=not dry, display_device=0, display_cap=max_cap)
    d.start()
    _append_durable(SWEEP_LOG, {"event": "sweep_start", "max_cap": max_cap,
                                "sweep_cards": sweep_cards, "dry": dry})
    safe, ceiling, rows = 0, None, []
    try:
        for cap in range(1, max_cap + 1):
            guard.arm()
            sess = [(cap * 1000 + i, prompt, 64) for i in range(cap)]   # cap fresh on device 0
            for cid, _, _ in sess:
                d.conv_card[cid] = 0
            if sweep_cards == 2:                                        # constant load on Card B
                for i in range(max_cap):
                    cid = cap * 1000 + 500 + i
                    d.conv_card[cid] = 1
                    sess.append((cid, prompt, 64))
            res = d.handle_many(sess, max_workers=len(sess))
            d0 = [r for r in res if r.get("device") == 0 and r["admitted"]]
            t0 = [r["tbt_median_ms"] for r in d0 if r.get("tbt_median_ms")]
            tripped = guard.tripped()
            row = {"display_cap": cap, "d0_admitted": len(d0),
                   "d0_slo_met": sum(1 for r in d0 if (r.get("tbt_median_ms") or 1e9) <= 50.0),
                   "d0_tbt_median_ms": round(statistics.median(t0), 1) if t0 else None,
                   "tdr": tripped, "tdr_delta": guard.delta()}
            rows.append(row)
            _append_durable(SWEEP_LOG, row)
            print(json.dumps(row))
            if tripped:
                ceiling = cap
                print(f"*** TDR at display_cap={cap} -> SAFE display_cap = {safe} ***")
                break
            safe = cap
    finally:
        d.stop()
        if wd and wd.poll() is None:
            wd.terminate()
            try:
                wd.wait(timeout=5)
            except subprocess.TimeoutExpired:
                wd.kill()
    summary = {"event": "sweep_done", "safe_display_cap": safe, "ceiling_cap": ceiling,
               "sweep_cards": sweep_cards, "rows": rows}
    _append_durable(SWEEP_LOG, summary)
    print(json.dumps(summary, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="denningd -- co-residency control loop (S-shim-2)")
    ap.add_argument("--dry-run", action="store_true", help="no-GPU wiring over a fake engine")
    ap.add_argument("--serve", action="store_true", help="on-rig: real replicas")
    ap.add_argument("--cards", type=int, choices=[1, 2], default=2)
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--display-cap", type=int, default=0,
                    help="concurrent sessions allowed on the display card (device 0). DEFAULT 0 = "
                         "serves nothing (it hard-hangs this rig). >0 is unsafe here.")
    ap.add_argument("--no-guard", action="store_true", help="skip the TDR pre/post integrity check")
    ap.add_argument("--no-watchdog", action="store_true", help="do not launch the I-1 safing watchdog")
    ap.add_argument("--devices", type=str, default=None,
                    help="explicit Vulkan device indices to serve on, comma-separated (e.g. '1', '2', '1,2'). "
                         "Overrides --cards. Device 0 = the 2070 display card and is REFUSED.")
    ap.add_argument("--sweep", action="store_true",
                    help="ramp display-card concurrency under the guard until a TDR; find the safe cap")
    ap.add_argument("--max-cap", type=int, default=8, help="top of the display-cap sweep")
    ap.add_argument("--sweep-cards", type=int, choices=[1, 2], default=1,
                    help="1 = display card solo (cleanest); 2 = also load Card B at full")
    ap.add_argument("--force-display-unsafe", action="store_true",
                    help="override the display-card-hardhang refusal (NOT recommended -- risks a hard reboot)")
    args = ap.parse_args()
    if args.sweep:
        return _sweep(args.max_cap, args.sweep_cards, dry=args.dry_run,
                      force=args.force_display_unsafe)
    if args.serve:
        dev_override = None
        if args.devices:
            dev_override = [int(x) for x in args.devices.split(",") if x.strip() != ""]
            if 0 in dev_override:
                print(json.dumps({"refused": "device 0 is the RTX 2070 display card -- never serve on it "
                                  "(8 GB, drives the monitor). Use Vulkan 1 and/or 2 (the B70s)."}))
                return 2
        return _serve(args.cards, args.n, args.display_cap,
                      guard_on=not args.no_guard, watchdog_on=not args.no_watchdog,
                      devices_override=dev_override)
    return _dry_run()


if __name__ == "__main__":
    sys.exit(main())
