# experiments/

Measurement harnesses and code. **Nothing runs until its Prediction Card is finalized and tagged** (see `../prereg/`).

## Planned

- `p0-harness/` — instrumented llama.cpp (pinned SYCL/Vulkan build, `--split-mode layer`) for the **P0 two-sided honesty test**:
  - **H1 leg:** N concurrent/paused agent KV sessions on one B70 + an adversarial desktop VRAM-hog; instrument `QueryVideoMemoryInfo` budget/usage, residency demotion events, per-session TBT.
  - **H3 leg:** recompute-vs-refetch break-even sweep across prefix lengths; first measure the *effective* prefill FLOP rate and achieved PCIe/NVMe bandwidths on the frozen build.

Each harness ships its `REPRODUCE.md` manifest block (see `../REPRODUCE.md`).

## Inherited scaffold (generalize, NOT from-scratch)

The harness is not built from zero — frame these as *scaffold to generalize*, explicitly not "already built":
- **b70tools backlog item 8c** (planner/critic two-lane: pin a 2nd model to a distinct `ONEAPI_DEVICE_SELECTOR` / `level_zero:1`, confirm each lane holds throughput under simultaneous load) → generalize into the **N-session concurrency sweep** (H2').
- **the WoW co-tenancy run** (`D:/work/b70tools/docs/findings-wow-realtime-inference-impact-1.md`) → the **adversarial-co-tenant template** (scheduled stressor + passive capture + frame-log tail; add PresentMon for frame-times) (H1).
