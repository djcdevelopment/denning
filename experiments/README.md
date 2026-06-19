# experiments/

Measurement harnesses and code. **Nothing runs until its Prediction Card is finalized and tagged** (see `../prereg/`).

## Planned

- `p0-harness/` — instrumented llama.cpp (pinned SYCL/Vulkan build, `--split-mode layer`) for the **P0 two-sided honesty test**:
  - **H1 leg:** N concurrent/paused agent KV sessions on one B70 + an adversarial desktop VRAM-hog; instrument `QueryVideoMemoryInfo` budget/usage, residency demotion events, per-session TBT.
  - **H3 leg:** recompute-vs-refetch break-even sweep across prefix lengths; first measure the *effective* prefill FLOP rate and achieved PCIe/NVMe bandwidths on the frozen build.

Each harness ships its `REPRODUCE.md` manifest block (see `../REPRODUCE.md`).
