r"""E1 microbench (isolated pass) — materialization-cost primitives on Intel Arc B70 via torch-xpu.

Measures the cost-model [MEASURE] constants:
  B_pcie  : host<->VRAM transfer GB/s vs buffer size  (cost-model R1/R2 denominator)
  B_dq    : dequant-kernel output GB/s (int8->fp16, 4bit-unpack->fp16)  (R2 linchpin)
  B_c2c   : card->card GB/s (host-bounced on Windows; no P2P)  (R3)

Then checks cost-model R2: compression-over-bus wins iff  B_dq > B_pcie * r/(r-1)
(~2x B_pcie for FP8 r=2, ~1.33x for INT4 r=4). ISOLATED only — contended B_dq (the
headline) is a follow-up that runs this against a concurrent decode load.

Run: D:\work\denning\.venv\Scripts\python.exe experiments\e1_microbench.py --device xpu:1
"""
import argparse, json, time, statistics, sys
import torch

def med_time(fn, iters, warmup):
    for _ in range(warmup):
        fn()
    torch.xpu.synchronize()
    ts = []
    for _ in range(iters):
        torch.xpu.synchronize(); t0 = time.perf_counter()
        fn(); torch.xpu.synchronize()
        ts.append(time.perf_counter() - t0)
    return statistics.median(ts)

def bench_transfer(sizes_mb, iters, warmup):
    out = []
    for mb in sizes_mb:
        n = max(1, int(mb * 1024 * 1024) // 2)  # fp16 elements
        h = torch.empty(n, dtype=torch.float16)
        d = torch.empty(n, dtype=torch.float16, device="xpu")
        nb = n * 2
        h2d = med_time(lambda: d.copy_(h), iters, warmup)
        d2h = med_time(lambda: h.copy_(d), iters, warmup)
        out.append({"MB": mb, "H2D_GBs": round(nb/h2d/1e9, 2), "D2H_GBs": round(nb/d2h/1e9, 2)})
        del h, d; torch.xpu.empty_cache()
    return out

def bench_dequant(mb, iters, warmup):
    n = int(mb * 1024 * 1024)
    res = {}
    # int8 -> fp16 (read 1B, write 2B)
    s8 = torch.randint(-127, 127, (n,), dtype=torch.int8, device="xpu")
    res["int8->fp16_GBs"] = round((n*2) / med_time(lambda: s8.to(torch.float16), iters, warmup) / 1e9, 1)
    del s8
    # 4-bit unpack -> fp16 (1 byte holds 2 nibbles -> 2 fp16 out)
    su = torch.randint(0, 255, (n,), dtype=torch.uint8, device="xpu")
    def unpack():
        lo = (su & 0xF).to(torch.float16); hi = (su >> 4).to(torch.float16)
        return lo + hi  # force materialization of both
    res["int4unpack->fp16_GBs"] = round((n*2*2) / med_time(unpack, iters, warmup) / 1e9, 1)
    del su; torch.xpu.empty_cache()
    return res

def bench_c2c(mb, iters, warmup):
    if torch.xpu.device_count() < 2:
        return None
    n = int(mb * 1024 * 1024) // 2
    s = torch.empty(n, dtype=torch.float16, device="xpu:1")
    nb = n * 2
    def f(): return s.to("xpu:0")
    for _ in range(warmup): f()
    torch.xpu.synchronize("xpu:0"); torch.xpu.synchronize("xpu:1")
    ts = []
    for _ in range(iters):
        torch.xpu.synchronize("xpu:1"); t0 = time.perf_counter(); f()
        torch.xpu.synchronize("xpu:0"); ts.append(time.perf_counter() - t0)
    del s; torch.xpu.empty_cache()
    return round(nb / statistics.median(ts) / 1e9, 2)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="xpu:1")          # Card B (compute)
    ap.add_argument("--iters", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if not torch.xpu.is_available():
        print("xpu not available", file=sys.stderr); sys.exit(2)
    idx = int(a.device.split(":")[1]) if ":" in a.device else 0
    torch.xpu.set_device(idx)
    print(f"device {a.device} = {torch.xpu.get_device_name(idx)}  (driver via torch {torch.__version__})")

    sizes = [0.0625, 0.25, 1, 4, 16, 64, 256]   # MB; sweeps the small-block latency regime up
    transfer = bench_transfer(sizes, a.iters, a.warmup)
    dq = bench_dequant(64, a.iters, a.warmup)
    c2c = bench_c2c(64, a.iters, a.warmup)

    bpcie = max(r["H2D_GBs"] for r in transfer)   # asymptotic effective PCIe
    print("\nB_pcie (H2D/D2H GB/s vs MB):")
    for r in transfer: print(f"  {r['MB']:>7} MB : H2D {r['H2D_GBs']:>7} | D2H {r['D2H_GBs']:>7}")
    print(f"\nB_dq (dequant output GB/s): {dq}")
    print(f"B_c2c (card1->card0 GB/s, host-bounced): {c2c}")
    print(f"\n--- cost-model R2 check (B_dq > B_pcie*r/(r-1)?) using B_pcie~={bpcie} GB/s ---")
    for r, lbl in [(2,"FP8"), (4,"INT4")]:
        thr = bpcie * r/(r-1)
        bdq = dq["int4unpack->fp16_GBs"] if r==4 else dq["int8->fp16_GBs"]
        print(f"  {lbl} (r={r}): threshold {thr:.1f} GB/s ; B_dq {bdq} GB/s -> {'WINS' if bdq>thr else 'LOSES'} (isolated)")
    print(f"  R3: card->card {c2c} GB/s vs host->VRAM {bpcie} GB/s (expect <= ~1/2)")

    result = {"device": a.device, "torch": torch.__version__, "transfer": transfer,
              "dequant": dq, "c2c_GBs": c2c, "B_pcie_GBs": bpcie}
    if a.out:
        with open(a.out, "w") as f: json.dump(result, f, indent=2)
        print(f"\nwrote {a.out}")

if __name__ == "__main__":
    main()
