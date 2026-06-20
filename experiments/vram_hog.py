#!/usr/bin/env python3
r"""
H1 VRAM-hog (experiments) — the adversarial co-tenant.

Drives a card's DXGI budget down to induce *involuntary* VidMm demotion of a
serving process that otherwise FITS. Allocates and **touches** (writes) VRAM on
the compute card in --step-gb increments up to --cap-gb, holds for --hold-s,
then frees. Touch forces a real commit, not a lazy reservation — that's what
actually pressures the budget.

H1 question it serves: with a fitting llama.cpp Vulkan server running on the same
physical card, does this hog cause VidMm to demote the *server's* KV/weights to
shared memory (PDH non_local rises on the server) — or does VidMm protect the
foreground compute process and demote the hog instead?

SAFETY: run UNDER ops/safing_watchdog.py (observer mode — a non_local rise is the
H1 signal, not a fault; the watchdog's ABORT level still guards the real cascade:
commit>=95%, phys>=29.5GB, TDR). Start with a small --cap-gb and walk it up.

  python experiments/vram_hog.py --device xpu:1 --cap-gb 2 --step-gb 1 --hold-s 3
"""

from __future__ import annotations

import argparse
import sys
import time

import torch

GIB = 1024 ** 3
FP16_ELEMS_PER_GB = GIB // 2  # float16 = 2 bytes/elem


def mem_info(dev: str):
    """(free_gb, total_gb) for the xpu device, or (None, None) if unsupported."""
    try:
        free, total = torch.xpu.mem_get_info(dev)
        return free / GIB, total / GIB
    except (RuntimeError, AttributeError, TypeError):
        return None, None


def main() -> int:
    ap = argparse.ArgumentParser(description="H1 adversarial VRAM-hog")
    ap.add_argument("--device", default="xpu:1", help="xpu device (xpu:1 = Card B, compute)")
    ap.add_argument("--cap-gb", type=float, default=2.0, help="max GB to allocate")
    ap.add_argument("--step-gb", type=float, default=1.0, help="allocation increment")
    ap.add_argument("--hold-s", type=float, default=10.0, help="hold time at cap")
    ap.add_argument("--step-pause-s", type=float, default=1.0, help="pause between steps")
    args = ap.parse_args()

    dev = args.device
    if not torch.xpu.is_available():
        print("[hog] ERROR: torch.xpu not available", file=sys.stderr)
        return 2
    torch.xpu.set_device(dev)

    f, t = mem_info(dev)
    print(f"[hog] target {dev} | cap {args.cap_gb} GB, step {args.step_gb} GB"
          + (f" | card free {f:.2f}/{t:.2f} GB before" if t else ""))
    sys.stdout.flush()

    blocks = []
    allocated = 0.0
    try:
        while allocated + args.step_gb <= args.cap_gb + 1e-6:
            n = int(args.step_gb * FP16_ELEMS_PER_GB)
            b = torch.empty(n, dtype=torch.float16, device=dev)
            b.fill_(1.0)                 # touch -> real commit
            torch.xpu.synchronize()
            blocks.append(b)
            allocated += args.step_gb
            f, t = mem_info(dev)
            print(f"[hog] +{args.step_gb:.1f} -> {allocated:.1f} GB resident"
                  + (f" | card free {f:.2f} GB" if t else ""))
            sys.stdout.flush()
            time.sleep(args.step_pause_s)

        print(f"[hog] HOLDING {allocated:.1f} GB for {args.hold_s}s "
              f"(watch the server's non_local / TBT now) ...")
        sys.stdout.flush()
        time.sleep(args.hold_s)
    except (RuntimeError, MemoryError) as e:
        # allocation failure is itself informative (budget exhausted)
        print(f"[hog] alloc stopped at {allocated:.1f} GB: {e}")
    except KeyboardInterrupt:
        print(f"[hog] interrupted at {allocated:.1f} GB")
    finally:
        blocks.clear()
        try:
            torch.xpu.empty_cache()
        except (RuntimeError, AttributeError):
            pass
        print("[hog] freed.")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
