# The training corpus after the rulers were retired (#240)

`manifest.json` is what `tools/finetune/build_dataset.py` emitted on
2026-08-10, the day [ADR-0020](../../../docs/decisions/0020-retire-the-rulers.md)
retired the five local instrument sets and released them for training. It is
kept because #240's last acceptance item asks for the release's value as a
*number* rather than as an expectation, and because a training set has to be
able to say which measurement sets it drew from — #189's could not, which is
how it came to train on the twenty contracts it was then scored on.

The two `.jsonl` splits are **not** kept. They are 5.7 MB of prompts and
replies already pinned byte-for-byte in
[`../worker-replies/golden.json`](../worker-replies/README.md), and the
manifest names every example by `(run, file, sha256)` — so the splits are
reproducible from this directory and the corpus, and storing them twice would
only create a second thing to keep in sync.

## Rebuild it

```
uv run --no-sync python tools/finetune/build_dataset.py --out <dir>
```

Defaults are the recorded ones: `--cap 40` per `(problem, language)` arm,
`--split-by problem`. The output is deterministic given the same corpus and the
same declaration, so a manifest that differs from this one means one of those
two moved.

## What it says

| | examples | problems | source |
|---|---:|---:|---|
| `pool-ts` | 506 | 147 | #197 problem pool |
| `pool-py` | 102 | 54 | #197 problem pool |
| `d1` | 665 | 20 | `bundle-ts`, retired and released |
| `d2` | 269 | 12 | `breadth-d2`, retired and released |
| `d3` | 2 | 2 | `breadth-d3`, retired and released |
| **total** | **1,544** | **184** | 63 runs, 1,405 train / 139 val |

By language: 1,442 TypeScript, 102 Python. The skew is rig time rather than
corpus composition (#226) — and it is worse here than in the pool alone,
because every released set except `bundle-py` is TypeScript.

**A problem is identified by its set as well as its id**, which the release
made load-bearing: `t01` names one problem in `d1` and a *different* problem in
`d2`, and before #240 that never mattered because neither was drawable. Keyed
on the bare id the two shared a single per-arm cap budget and one crowded out
the other — 213 examples' worth, and a `problems` count of 170 for 184 distinct
problems. Each example carries an `origin` for this reason.

**Released, by the set that produced the replies:** `bundle-ts` 8,432,
`breadth-d2` 468, `bundle-py` 105, `breadth-d1r` 36, `breadth-d3` 12, plus 120
that no single set can be attributed to — 9,173 replies, which is exactly the
count #230 walled off. Most of them never become examples: 6,726 replies did
not pass their checker, 1,927 are duplicate solutions, 1,516 exceed the per-arm
cap, and 105 are bundle-rig replies whose capture path this builder does not
read.

**Refused:** `humaneval-plus`, which is retired *and* permanently untrainable.
It accounts for **zero** replies here, because no HumanEval run ever wrote into
`records/measurements/` — the pilot that scored on it ran through EvalPlus. The
refusal is therefore a standing guard rather than a filter that fired, and the
declaration is what will make it fire if that ever changes.

**Unresolvable:** `breadth-2026-08-06`, 114 replies. The run recorded no tier
and its task ids fall in five sets at once, so the contracts behind its replies
cannot be identified and their prompts cannot be rebuilt. They are counted and
the run is named rather than guessed at.

## What this is not

It is not a decision to train. #221 owns that, and 1,544 examples over 184
problems is more material rather than evidence that a tune is worth running —
see [`docs/what-a-tune-may-train-on-2026-08-10.md`](../../../docs/what-a-tune-may-train-on-2026-08-10.md),
where "no usable source yet" is still an available finding.

It is also not a bench. Every example here comes from a set the project has
committed to never measuring on again, which is precisely what makes it safe to
draw from and precisely what makes it useless for deciding anything. The bench
is #225's material and #113's harness.
