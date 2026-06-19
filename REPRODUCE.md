# Reproducibility Standard

A result is not "done" until it ships a **manifest**. Design for Artifact Evaluation from day one — a clean artifact is a credibility multiplier, especially for a first author.

## Per-result manifest (copy this block into each result)

```
## Manifest — <Stage/Exp ID>
- git commit:            <hash>
- llama.cpp commit:      <hash>
- SYCL/Vulkan backend:   <build hash / version>   # PINNED & FROZEN (3–4x throughput swings by version)
- OS / driver:           Windows 10 <build> / Intel Arc driver <version>
- model:                 <name> / file sha256 <hash> / quant <e.g. Q4_K_M> / KV dtype <FP8>
- config / flags:        --split-mode layer, ctx <N>, <env incl. HF_HOME=D:\...>
- seeds:                 <seed(s)>
- N runs:                <k>
- raw data:              results/raw/<...>   (gitignored if large; note checksum)
- analysis notebook:     <path>
- hardware:              dual Arc Pro B70 (32GB, 608 GB/s), 32GB RAM, PCIe 4.0 x8/x8, display on <iGPU/card>
- BIOS:                  <version> (ReBAR on, ECC off, Above-4G on)
- idle GPU clocks:       <MHz/card>     # baseline to detect thermal/clock drift mid-campaign
- idle thermals:         <die/VRAM °C per card>
```

## Rules
1. **Pin the backend build** and report every number against a *frozen* baseline. Single-digit-% policy wins are meaningless on a noisy substrate without this.
2. **Report distributions, not points:** P50 **and** P99, with confidence intervals over N≥5 runs. Report the measured **noise floor** alongside every comparison.
3. **Caches/models on D: only** — never let HF/model caches land on C: (≤100 GB free redline). Record the redirect env in the manifest.
4. **Raw data** committed if small; if large, gitignored under `results/raw/` with a checksum recorded in the manifest (consider git-LFS later).
5. A `REPRODUCE.md` step list per experiment so a third party can re-run from the manifest.

## Flight rules (added from the 4-lens review, 2026-06-19)

6. **Frozen-config campaign.** The pinned set (driver version, BIOS version+settings, SYCL/Vulkan build hash, llama.cpp commit, model hashes, OS build) is FROZEN for a campaign. **Any change to one — especially a driver update — invalidates the frozen baseline and REQUIRES re-measuring the noise floor before further runs are comparable.** *(Prior work: a driver bump silently changed both stability AND the SYCL-vs-Vulkan verdict — an uncontrolled config change invalidated a settled conclusion.)*
7. **Deterministic replay + full-state attribution.** Every result ships the backing b70tools `events.jsonl` and is confirmed replayable. Capture driver / BIOS / build-hash / idle-clocks / idle-thermals / ReBAR / ECC **out-of-band in the manifest** — do not rely on pure replay to recover rig identity. *(Verify b70tools `replay_reader` event-kind coverage before depending on it; the audit could not confirm which kinds it reconstructs vs only counts.)*
8. **Interleave conditions within a session** (A,B,A,B…), never all-of-A-then-all-of-B, to control driver/thermal/background drift across a multi-week campaign.
9. **Telemetry-completeness is a PASS condition.** No run produces a citable result unless the recording demonstrably contains the signal its prediction is scored on (heartbeat seen + the load-bearing metric present and not in a known blind spot). See [`docs/operational-safety-runbook.md`](docs/operational-safety-runbook.md) for the pre-flight checklist, per-failure-mode malfunction procedures, abort criteria, the unattended-run standard, and the telemetry blind-spot table.
