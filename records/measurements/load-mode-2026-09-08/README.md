# `--load-mode none` against mmap on srv1 — a null, and what the null is about

Taken 2026-09-08, after `serving.fit` learned to derive a loading mode
(`okf/must-read/touching-rigs.md`, `records/measurements/wake-2026-09-08/`).
The question: on srv1 as it stands, what does `--load-mode none` buy?

**Nothing measurable. Not throughput, not wake.** And it costs 8.4 GiB of
reclaimable memory. The +63% that motivated the flag was measured on
2026-08-25 against a blob 2.5 GB *larger* than its host's RAM; srv1's blob fits
its host, so there is nothing for the flag to fix here.

## What ran

Four arms — mmap, none, mmap, none — because the rig's own drift is larger than
the effect being looked for, and only a repeat shows that. Each arm is a full
`serve down` / `serve up` through the door, an assertion that the container's
`StartedAt` actually moved, a check of the argv the rig is really running, one
discarded warm-up and three measured samples: 160 tokens, `temperature 0`,
`cache_prompt false`, identical prompt. `ab.sh` is the script, `run.txt` the
transcript.

| arm | argv | wake | samples (tok/s) | mean | RAM used / avail |
|---|---|---|---|---|---|
| mmap | (default) | 128.6 s | 33.00 / 32.99 / 32.91 | **32.97** | 1,631 / 13,761 MiB |
| none | `--load-mode none` | 119.7 s | 33.08 / 23.95 / 33.08 | **33.08**\* | 10,072 / 5,320 MiB |
| mmap | (default) | 115.7 s | 31.41 / 31.44 / 31.40 | **31.42** | 1,626 / 13,766 MiB |
| none | `--load-mode none` | 120.3 s | 31.31 / 31.30 / 31.35 | **31.32** | 10,016 / 5,377 MiB |

\* the 23.95 is an outlier of the kind
`records/measurements/serving-concurrency-2026-09-06/` warns about; the mean is
of the two clean samples, and including it would only strengthen the null.

**Read it paired, not pooled.** Early pair: mmap 32.97 against none 33.08, +0.3%
for unmapped. Late pair: 31.42 against 31.32, −0.3%. **The rig moved 5% between
the pairs and the loading mode moved it 0.3% within them** — the effect is an
order of magnitude below the noise it sits in. Wake is the same story: 128.6 and
115.7 mapped against 119.7 and 120.3 unmapped, which is one distribution.

The earlier single-sample comparison (116.9 s unmapped against 128 s mapped) was
one draw from each of those; it should not have been quoted as a difference.

## What is not a null: the memory shape

| | mapped | unmapped |
|---|---|---|
| RAM used | 1.6 GiB | **9.8 GiB** |
| RAM available | 13.4 GiB | **5.2 GiB** |

Mapped, the weights live in page cache the kernel can reclaim; unmapped they are
anonymous and it cannot. That is the *point* of the flag where a blob overflows
RAM — nothing can evict the experts mid-token — and it is a straight loss where
the blob fits, because the host gives up 8 GiB of flexibility for no speed.

## What this says about the rule

The arms in `serving.fit` are right; **the threshold between them is not.** It
sends a model unmapped when `blob + 2 GiB headroom > MemAvailable`, and srv1
crossed that line by **0.11 GiB** — a 12.31 GiB blob against the 14.2 GiB the
2026-09-05 scan recorded. Both measurements this fleet has taken say the trigger
should be the blob genuinely not fitting:

* 2026-08-25: blob 18.56 GB, RAM 16 GB — **does not fit**, mmap thrashes, `none`
  is +63%.
* 2026-09-08 (here): blob 12.31 GiB, available 14.2 GiB — **fits**, mmap is fine,
  `none` is ±0.3% and −8.4 GiB of reclaimable memory.

Nothing measured supports a headroom on the *mapping* decision. Keep it on the
refusal — that one gates a launch — and map while the blob fits.

## A hazard this turned up

`MemAvailable` reads 13.4 GiB with the unit mapped and 5.2 GiB with it unmapped,
so **the decision's input depends on the decision**. `emit` reads a recorded
scan (`~/.local/state/mcgyvr/scans/`, srv1's from 2026-09-05) rather than a live
one, which is what kept this from biting today; a scan taken while a unit serves
unmapped would refuse the model that is running. The bench already knows the
shape of this — `mmap_gate` evaluates after the previous cell tears down — and
the product does not.
