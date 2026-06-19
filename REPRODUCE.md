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
- hardware:              dual Arc Pro B70 (32GB, 608 GB/s), 32GB RAM, PCIe Gen<N> x<N>, display on <iGPU/card>
```

## Rules
1. **Pin the backend build** and report every number against a *frozen* baseline. Single-digit-% policy wins are meaningless on a noisy substrate without this.
2. **Report distributions, not points:** P50 **and** P99, with confidence intervals over N≥5 runs. Report the measured **noise floor** alongside every comparison.
3. **Caches/models on D: only** — never let HF/model caches land on C: (≤100 GB free redline). Record the redirect env in the manifest.
4. **Raw data** committed if small; if large, gitignored under `results/raw/` with a checksum recorded in the manifest (consider git-LFS later).
5. A `REPRODUCE.md` step list per experiment so a third party can re-run from the manifest.
