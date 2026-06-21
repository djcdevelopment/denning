# Result — both B70s serve clean headless after the 2070 display offload (2026-06-21)

*The control experiment for the display-card fix. After installing an RTX 2070 SUPER as
the primary display (both B70s now headless — see [`display-card-hardhang-20260620`](display-card-hardhang-20260620.md)),
run **each B70 solo** through the full `denningd` serve loop (admission → arena → swap →
stream), guard + watchdog armed, to confirm each card holds independently before any
two-card run. The decisive question: does the card that **hard-hung the whole machine
while driving the display** behave when it's headless?*

## Setup
RTX 2070 SUPER drives the display (Vulkan0, never served). The two headless B70s are
Vulkan1 + Vulkan2. `denningd --serve --devices 1 --n 8`, then `--devices 2 --n 8`
(device 0 is hard-refused). Qwen3-30B-A3B-Q4, 8 concurrent sessions, SLO TBT ≤ 50 ms.

## Result — both cards clean
| card | admitted | SLO met | median TBT | agg decode | TDR (before→after) |
|---|---|---|---|---|---|
| B70 #1 (Vulkan 1) | 8 | **8 / 8** | 27.6 ms | 98.4 t/s | clean (114 → 114) |
| B70 #2 (Vulkan 2) | 8 | **8 / 8** | 27.4 ms | 94.4 t/s | clean (114 → 114) |

Near-identical (same silicon), all sessions met the SLO, **zero new display-driver TDRs**
on either run (the lifetime 4101 count held at 114 across both).

## The conclusion
**Vulkan 2 is the same physical card that hard-locked the system ~3 hours earlier** when
it was the display adapter (a single session produced no tokens; two hung the box,
manual reboot). Headless, that identical card runs the full serve loop flawlessly. So the
catastrophic failure was **display co-tenancy, not the card** — the compositor starving
under inference, not any defect in the B70 or denning. Remove the display burden (offload
it to a cheap dedicated GPU) and the B70 is a clean, well-behaved compute card.

This empirically validates the fix and the reframe: **on a fabric-less consumer desktop,
the path to safe multi-card serving is a dedicated (cheap, low-power) display GPU so the
compute cards stay headless.** The retracted "1 usable card" verdict is lifted *per card* —
both B70s are individually confirmed serving-clean.

## Safety note
With the display on the 2070, the blast radius shrank: even a worst-case headless-B70 TDR
would reset only that card's compute context (killing its inference job), **not** the
desktop — the display lives on the untouched 2070. The class of failure that required a
manual reboot is structurally gone for serving workloads.

## Next
Both cards hold solo → a **two-card** run (`--serve --cards 2`, Vulkan 1+2) now isolates
any *multi-card / system* interaction (shared PCIe, host RAM, the 2070's presence) from
single-card behavior. That is the genuine, safe two-card lap — the headline the display
card denied us, now reachable.

## Reproduce
```
python -m denning.denningd --serve --devices 1 --n 8
python -m denning.denningd --serve --devices 2 --n 8
```
driver 32.0.101.8826 (Arc) / 591.86 (NVIDIA display). 2070 SUPER @ Vulkan0 never served.
