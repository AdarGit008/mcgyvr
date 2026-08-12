# ADR-0024 — comparable measurements come from one rig and one build

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: ADR-0019 (a contrast's power assumes the arms differ in one thing; this
names a second thing they were differing in)
Date: 2026-08-11

## Context

The project's rig note has always been that the worker is configuration and not
part of the experiment: an endpoint is a hostname, a tunnel port, somebody's
machine, and none of it belongs in the repository. That is right about *where*
a model is served and wrong about *what* serves it.

#225's scaffold ablation ran the 3B against srv1 and the 7B against srv2. Both
hosts were reachable, both served the model asked for, and the run manifests
recorded endpoint, protocol and model for each. Neither recorded that srv1 was
running ollama 0.32.4 and srv2 was running 0.32.5, or that one has a 6 GB GTX
1660 SUPER and the other a 12 GB RTX 3060. The one cross-model contrast the
campaign most wanted to draw therefore had a serving difference folded into it
that nothing on disk could reveal.

`strata.json` already caveats those two cells as "two experiments reported side
by side, not a contrast." This record removes the need for the caveat rather
than restating it.

## What the two rigs actually are

| | srv1 | srv2 |
|---|---|---|
| GPU | GTX 1660 SUPER, **6 GB** | RTX 3060, **12 GB** |
| CPU | i5-9600K, 6c/6t | i9-10900F, 10c/20t |
| RAM | 32 GB, dual channel @ 3200 | 32 GB, single channel @ 2933 |
| models held | ≤ 7B (largest blob 4.7 GB) | the whole ladder, to 36.3 GB |

The binding constraint is **VRAM, not memory bandwidth**. srv1's 6 GB caps it
near 7B-quantized. The earlier reading — that srv1's higher system-RAM
bandwidth (21.8 vs 13.3 GB/s) made it the better host for larger models — is
wrong twice over: that figure only matters once a model spills to CPU, and srv1
cannot hold the larger models in the first place.

**srv2's capability is a strict superset of srv1's.** srv1 contributes no model
srv2 cannot serve; what it contributes is parallel capacity at the small end.

## Decision

> **DECIDED (2026-08-11, owner).**
>
> 1. **srv2 is the measurement rig.** Every number that will be compared to
>    another number is served from it — one GPU, one ollama build, the whole
>    ladder.
> 2. **srv1 is capacity.** It runs 1.5B and 3B sweeps for throughput. Rates
>    produced there are not compared across hosts.
> 3. **The serving build is run identity.** `run.json` records it, and a resume
>    into a directory served by a different build is refused exactly as a
>    changed temperature or cap is refused.
> 4. **The recorder derives it; no caller passes it.** `--condition` was a
>    caller-supplied identity field, it reached dispatch and never
>    `record_run`, and eight manifests described a render nobody had run. A
>    field derived from the world at the point of recording cannot be forgotten
>    by a fourth driver.

## Consequences

- **A manifest written before the field existed adopts the current value
  rather than refusing.** The build those runs were served by is not recoverable
  either way, and a spurious refusal on every directory already on disk would
  buy nothing. The protection is for runs made from here on.
- **An endpoint that will not name its build records `null`.** The probe is
  best-effort against a host that may not be ollama at all. Unknown is a value;
  a guess is not.
- **The ceiling question inherits this.** If the ladder later reaches a 20B or
  30B MoE worker, it reaches it on srv2, which is where the ladder already is.
- **This does not withdraw the "worker is configuration" rule.** Where a model
  is served stays out of the repository — the endpoint is still redacted. What
  joins the experiment is the *build*, because two builds are two instruments.
