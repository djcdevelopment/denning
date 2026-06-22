#!/usr/bin/env python3
"""Intel XPU (Arc B70) capability probe on Windows: matmul TFLOPS + dtype support + mem."""
import time
import torch

print("torch:", torch.__version__)
print("xpu available:", torch.xpu.is_available())
print("device:", torch.xpu.get_device_name(0))
dev = "xpu"


def bench(dtype, n=4096, iters=30):
    try:
        a = torch.randn(n, n, device=dev, dtype=dtype)
        b = torch.randn(n, n, device=dev, dtype=dtype)
        for _ in range(5):
            c = a @ b
        torch.xpu.synchronize()
        t0 = time.perf_counter()
        for _ in range(iters):
            c = a @ b
        torch.xpu.synchronize()
        el = time.perf_counter() - t0
        tflops = 2 * (n ** 3) * iters / el / 1e12
        print(f"  {str(dtype):15s} {tflops:7.1f} TFLOPS  ({el / iters * 1000:6.2f} ms/matmul)")
    except Exception as e:
        print(f"  {str(dtype):15s} FAILED: {type(e).__name__}: {str(e)[:120]}")


print("matmul 4096x4096:")
for d in (torch.float16, torch.bfloat16, torch.float32):
    bench(d)

try:
    free, total = torch.xpu.mem_get_info(0)
    print(f"xpu mem: {free / 1e9:.1f} / {total / 1e9:.1f} GB free")
except Exception as e:
    print("mem_get_info:", type(e).__name__, str(e)[:80])
