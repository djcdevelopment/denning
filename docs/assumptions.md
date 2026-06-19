# Load-Bearing Assumptions

*The premises the design rests on — distinct from threats-to-validity (which are measurement confounds). Each is ranked by load-bearing × uncertainty and mapped to the experiment that tests it. A sharp reviewer reverse-engineers these and attacks the weakest; better that we list them and point each at its test. (Uncle's P5.)*

| ID | Assumption | Load-bearing | Uncertainty | Tested by | Status |
|----|-----------|:---:|:---:|---|---|
| **D** | **Reuse-provenance is predictable enough that lifetime classes carry signal** (else classes can't beat TTL no matter how clean the contract) | **highest** | **high** | H4 classes-ON/OFF | **the scariest — the spine. Untested.** |
| **B** | VidMm will *involuntarily* evict a fitting, max-priority serving process under co-tenancy | high | **high** | H1 / I-3 lock-respect | **ON PROBATION** — Microsoft documents a *cooperative* offer/reclaim path; may not fire |
| **F** | Under good scheduling, **contended `B_dq`** stays above the `B_pcie·r/(r−1)` threshold (the compression bet) | high | high | E1 / R2 | untested — the make-or-break number |
| **A** | The **bus** is the binding constraint, not compute, for materialization | high | medium | E1 / R1–R3 | untested (cost model predicts it) |
| **G** | The OS respects a max-priority lock well enough that the arena is *deterministic* | high | medium | I-3 | untested (also the H1 probe) |
| **E** | Sparse attention / MLA flattens per-step KV bandwidth across context (→ re-ground admission on session count, not context) | medium | medium | H2′ (measure on our models) | asserted in v2; not yet measured here |
| **C** | **Commit charge** (not free RAM, not VRAM) is the feasibility wall | high | **low** | observed (prior work A4) | **strong** — measured at 92% commit / 60% physical |

**Read this:** the project's spine is assumption **D**. If reuse-provenance does not predict reuse-distance, the lifetime-class contribution collapses to "reuse-probability scoring," which Continuum/Aliyun already do — H4 is where we find out, and it is pre-committed to pivot to admission-only on a null. Assumptions **B** and **F** are the next-most-uncertain and are exactly what I-3 and E1 settle first. **C** is the one we can already lean on.
