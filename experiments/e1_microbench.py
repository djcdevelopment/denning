r"""E1 microbench — materialization-cost primitives on Intel Arc B70 via torch-xpu.

Measures the cost-model [MEASURE] constants:
  B_pcie  : host<->VRAM transfer GB/s vs buffer size  (R1/R2 denominator)
  B_dq    : dequant-kernel output GB/s (int8->fp16, 4bit-unpack->fp16)  (R2 linchpin)
  B_c2c   : card->card GB/s (host-bounced on Windows; no P2P)  (R3)
  --contended: B_dq while a background matmul load runs on a separate stream (the HEADLINE:
               does R2's margin survive contention? cost-model R2 + Uncle #1).

R2 check: compression-over-bus wins iff  B_dq > B_pcie * r/(r-1)
(~2x B_pcie for FP8 r=2, ~1.33x for INT4 r=4).

Run: D:\work\denning\.venv\Scripts\python.exe experiments\e1_microbench.py --device xpu:1 --contended
"""
import argparse, json, time, statistics, sys, threading
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
        n = max(1, int(mb * 1024 * 1024) // 2)
        h = torch.empty(n, dtype=torch.float16); d = torch.empty(n, dtype=torch.float16, device="xpu")
        nb = n * 2
        h2d = med_time(lambda: d.copy_(h), iters, warmup)
        d2h = med_time(lambda: h.copy_(d), iters, warmup)
        out.append({"MB": mb, "H2D_GBs": round(nb/h2d/1e9, 2), "D2H_GBs": round(nb/d2h/1e9, 2)})
        del h, d; torch.xpu.empty_cache()
    return out

def bench_dequant(mb, iters, warmup):
    n = int(mb * 1024 * 1024)
    res = {}
    s8 = torch.randint(-127, 127, (n,), dtype=torch.int8, device="xpu")
    res["int8->fp16_GBs"] = round((n*2) / med_time(lambda: s8.to(torch.float16), iters, warmup) / 1e9, 1)
    del s8
    su = torch.randint(0, 255, (n,), dtype=torch.uint8, device="xpu")
    def unpack():
        lo = (su & 0xF).to(torch.float16); hi = (su >> 4).to(torch.float16)
        return lo + hi
    res["int4unpack->fp16_GBs"] = round((n*2*2) / med_time(unpack, iters, warmup) / 1e9, 1)
    del su; torch.xpu.empty_cache()
    return res

def bench_dequant_contended(mb, iters, warmup, load_n=4096):
    """Dequant throughput while a background matmul load saturates the GPU on a 2nd stream."""
    load_stream = torch.xpu.Stream()
    a = torch.randn(load_n, load_n, device="xpu", dtype=torch.float16)
    b = torch.randn(load_n, load_n, device="xpu", dtype=torch.float16)
    c = torch.empty(load_n, load_n, device="xpu", dtype=torch.float16)
    stop = threading.Event()
    def loader():
        with torch.xpu.stream(load_stream):
            while not stop.is_set():
                for _ in range(10):
                    torch.matmul(a, b, out=c)
                load_stream.synchronize()
    th = threading.Thread(target=loader, daemon=True); th.start()
    time.sleep(1.5)  # ramp the load
    res = bench_dequant(mb, iters, warmup)
    stop.set(); th.join(timeout=10)
    del a, b, c; torch.xpu.empty_cache()
    return res

def bench_c2c(mb, iters, warmup):
    if torch.xpu.device_count() < 2:
        return None
    n = int(mb * 1024 * 1024) // 2
    s = torch.empty(n, dtype=torch.float16, device="xpu:1"); nb = n * 2
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
    ap.add_argument("--device", default="xpu:1")
    ap.add_argument("--iters", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--contended", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if not torch.xpu.is_available():
        print("xpu not available", file=sys.stderr); sys.exit(2)
    idx = int(a.device.split(":")[1]) if ":" in a.device else 0
    torch.xpu.set_device(idx)
    print(f"device {a.device} = {torch.xpu.get_device_name(idx)}  (torch {torch.__version__})")

    sizes = [0.0625, 0.25, 1, 4, 16, 64, 256]
    transfer = bench_transfer(sizes, a.iters, a.warmup)
    dq = bench_dequant(64, a.iters, a.warmup)
    dq_load = bench_dequant_contended(64, a.iters, a.warmup) if a.contended else None
    c2c = bench_c2c(64, a.iters, a.warmup)

    bpcie = max(r["H2D_GBs"] for r in transfer)
    print("\nB_pcie (H2D/D2H GB/s vs MB):")
    for r in transfer: print(f"  {r['MB']:>7} MB : H2D {r['H2D_GBs']:>7} | D2H {r['D2H_GBs']:>7}")
    print(f"\nB_dq isolated:  {dq}")
    if dq_load: print(f"B_dq CONTENDED: {dq_load}")
    print(f"B_c2c (card1->card0, host-bounced): {c2c}")
    print(f"\n--- cost-model R2 (B_dq > B_pcie*r/(r-1)?) using B_pcie~={bpcie} GB/s ---")
    for r, lbl in [(2,"FP8"), (4,"INT4")]:
        thr = bpcie * r/(r-1)
        key = "int4unpack->fp16_GBs" if r==4 else "int8->fp16_GBs"
        line = f"  {lbl} (r={r}): threshold {thr:.1f} ; isolated {dq[key]} -> {'WINS' if dq[key]>thr else 'LOSES'}"
        if dq_load: line += f" ; contended {dq_load[key]} -> {'WINS' if dq_load[key]>thr else 'LOSES'}"
        print(line)
    print(f"  R3: card->card {c2c} vs host->VRAM {bpcie} (expect <= ~1/2)")

    result = {"device": a.device, "torch": torch.__version__, "transfer": transfer,
              "dequant_isolated": dq, "dequant_contended": dq_load, "c2c_GBs": c2c, "B_pcie_GBs": bpcie}
    if a.out:
        with open(a.out, "w") as f: json.dump(result, f, indent=2)
        print(f"\nwrote {a.out}")

if __name__ == "__main__":
    main()
