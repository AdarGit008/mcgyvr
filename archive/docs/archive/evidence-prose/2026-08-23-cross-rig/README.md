# The cross-rig claim, re-taken with its conditions on the record — #329's rig arm

**2026-08-23.** One width-16 vLLM ramp per rig at 475 tokens, both launched
through the `vllm/vllm-openai:v0.26.0` container. 1,403 s wall, sequential, one
rig at a time (E14). Intent declared before the run:
`records/headers/2026-08-23-cross-rig-claim.json`.

## What it was for

The 2026-08-19 campaign read srv2 at 15.42x of a single stream at width 16 and
srv1 at 3.76x, and concluded "the gap is hardware, not configuration"
(`../calibration-2026-08-19/README.md:983-987`). The journal that sentence was
read off names no card, no driver, no launcher, no engine build and no weights
digest, and holds no launch row at all — so nothing recorded could tell a card
apart from a container image. #329 turned the claim into
`cross_host_contrast`, which refuses a contrast whose sides are not comparable.
This run is the journal that function can accept.

## The result

| | 2026-08-19 (launcher detected) | this run (launcher declared docker) |
|---|---|---|
| srv1 speedup | 3.76 · pip | **3.82** · container |
| srv2 speedup | 15.42 · container | **15.41** · container |
| srv1 `saturation_n` / `latency_plateau_n` | 16 / 8 | 16 / 8 |
| srv2 `saturation_n` / `latency_plateau_n` | 16 / 16 | 16 / 16 |

srv1's levels, n=1 through 24: 10.908, 34.557, 34.760, 34.854, 35.187, 35.531,
44.790, 45.593, 57.254 s. The 2026-08-19 run read 10.708 at n=1 and 45.466 at
n=16. **The launcher was worth 0.06 on a gap of 11.6**, which is inside the
run-to-run spread of the curve around it.

Both launch rows carry `weights_sha256`
`047d5b14da69a39eefe24f8bafa34278a336a08a93d757d70cd38c6b7c3d8c78`,
`serving_build` `vllm 0.26.0`, and `launcher_declared: true`. The identity
blocks name a GTX 1660 SUPER (6144 MiB, driver 580.173.02, cc 7.5) and an RTX
3060 (12288 MiB, 595.84, cc 8.6).

## What this settles, and what it does not

**Settles:** the deployment is not the explanation. It was the one alternative
that could be removed without buying hardware, and removing it moved the figure
by less than the noise.

**Does not settle:** what the slower side is made of. Card and driver move
together across these two rigs, and the container does not pin the driver —
inside srv2's container `nvidia-smi` reports the host's 595.84. Separating them
needs a third machine. `--enforce-eager` was on both, mandatory on srv1's
compute capability 7.5 and kept on srv2 for that reason.

**Not a confound, checked before the run:** the ramp declares
`gpu_memory_utilization 0.85`, which is 5,222 MiB on srv1 and 10,444 on srv2 —
the card-relative declaration ADR-0039 rules against. It does not bind here:
D7 predicted srv1 would cap at `kv_cache_max_concurrency` 5.314 and both rigs
measured `saturation_n` of exactly their configured 16, so the KV budget never
limited concurrency on either side. The fraction is kept so this stays a
re-take of the cell the sentence was read off.

## Two figures produced on the way

- **srv1's first container launch: 83.5 s**, against 33 s for its pip launch —
  the same engine, the same card, 2.5x the start time. srv2 launched in 93.1 s
  here against 109 s in D7. These are the first `START_TIMEOUT_S` points srv1
  has contributed on the container arm.
- **The weights digest ran inside the image on both hosts** for the first time
  (it follows the launcher): 7.5 s on srv1, 10.4 s on srv2.

## How to re-run it

```
uv run --no-sync python tools/bench/serving/calibrate.py \
  --phase ramp --engines vllm --hosts srv1,srv2 \
  --tokens 475 --widths 16 --launcher docker \
  --out records/evidence/<date>/ramp.jsonl
```

`--launcher` is #329's seam. Without it `vllm.launcher` detects, and detection
returns `pip` for any host answering `command -v vllm` — which srv1 does — so
the contrast would be pip against container with nothing on the row saying so.
`serving_build` does not catch that: both launchers answer `vllm 0.26.0`,
because the string is the package's version and not the build's. A declaration
is verified against the host and refuses rather than falling back.

## Checks

`tests/test_cross_rig_claim.py`. Arm 3 reads this journal through
`cross_host_contrast` and the `xfail(strict=True)` that stood over it from
2026-08-22 came off in the commit that added this directory.
`::test_both_sides_of_the_cross_rig_contrast_ran_the_launcher_the_run_declared`
holds both rows to `launcher_declared: true`, which is the part the contrast
function itself does not read.
