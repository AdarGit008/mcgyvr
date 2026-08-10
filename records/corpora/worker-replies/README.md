# Worker-reply corpus — golden verdicts over every captured reply

`golden.json` is the data; this file is why it contains what it contains.

Recompute and diff against the pinned copy:

```
uv run --no-sync python tools/replies/pin.py --check
```

`tests/test_reply_corpus.py` runs the same recomputation offline on every
suite run. As of the #230 re-pin it reports **12,331 replies over 88 runs**:
11,932 parses and 399 refusals.

## Why a corpus at all

[#184](https://github.com/AdarGit008/mcgyvr/issues/184): the measurement rigs
generate `parse_reply`'s exact input distribution — real worker replies, on
real hardware, at real cost — and the JS/TS sweep ran the parser over 160 of
them, kept an error code for the ones that failed, and discarded the
population. #174 (a well-formed refusal that parsed as file content) is what
that discard costs: the hand-authored fixture set is bounded by what its
author imagined, and the one population that isn't so bounded was being
thrown away where it was free.

## What is kept, and where

Per [ADR-0016](../../../docs/decisions/0016-fixtures-capture-what-the-parser-reads.md),
the corpus is **the raw text the parser receives, never the run that produced
it** — reply bodies survive every change except a change to the reply format
itself, which is the one event a parser's corpus should be sensitive to. The
reply files stay in the run directories that captured them:

| rig | capture | joined to its row by |
|---|---|---|
| `tools/breadth/measure.py` | `<run>/candidates/<task>/<arm>-<draw>.txt` | `(task, arm, draw)` |
| `tools/bundle/measure.py` | `<run>/replies/<task>-<condition>-<attempt>.txt` | `(task, condition)` + attempt |

There is no copy step: every measurement run is a corpus contribution, and a
curation step is a step that gets skipped. What lives here is `golden.json`
alone — for each reply, its sha256, the model, the stop reason its own row
recorded (the parser's verdict depends on it), and the pinned outcome: a
content sha and info string for a parse, a refusal code for a refusal.

**Refusals are corpus, not noise.** A reply the parser could not handle is
pinned with the failure as its expected outcome, until someone improves the
parser and re-pins deliberately. Excluding failures would reintroduce the
author-imagination bound the corpus exists to escape.

## Which instrument a reply came from

[#230](https://github.com/AdarGit008/mcgyvr/issues/230): this corpus is walked
by `tools/finetune/build_dataset.py` on its way to a training set, so a run
over a measurement set joins the training path at the moment it lands. That is
how the #189 pilot came to train on 622 examples from `d1` — which **is**
`tools/bundle/tasks/`, half the floor instrument.

So every run is classified against `tools/instruments.json` and the verdict is
written into the document, under `instruments.runs`:

```json
"breadth-campaign-2026-08-06/srv1/qwen2.5-coder-3b/sweep-d1": {
  "sets": ["bundle-ts"], "primary": "bundle-ts",
  "why": "bundle-ts: tier 'd1' is declared as it"
}
```

**It is a stamp, not an exclusion.** 9,173 of the 12,331 replies here are
instrument material, and they stay: ADR-0016 requires the parser to be measured
on the population it actually faces, and dropping three quarters of it to
protect a *different* consumer would curate this corpus back to the shapes that
happen to be safe for fine-tuning. The training path refuses what the stamp
names; this corpus keeps it.

What is not optional is the verdict itself. A run stating no tier, no contract
digests and no task id cannot be classified, and an unclassifiable run is not a
clean one — it refuses to pin.

## Re-pinning

`uv run --no-sync python tools/replies/pin.py` regenerates `golden.json` from
disk; the diff shows in git and is reviewed like any other change. The three
events that force it apart:

- **A run captured new replies** — the ordinary case; the corpus grows
  monotonically and the diff is additions.
- **The parser's verdict on a real reply moved** — the event the corpus
  exists to make loud; the diff is the evidence for the parser change's
  review.
- **A reply file was edited or lost** — corpus rot; restore the file rather
  than re-pinning around it.
- **A set was declared in `tools/instruments.json`** — the stamps are only as
  good as their date, so declaring a set makes this file stale until it is
  re-pinned. The dataset builder treats a stamp that disagrees with the
  declaration as fatal rather than resolving it the permissive way, which is
  what makes the staleness loud instead of silent.

A reply with no row in its run's `results.jsonl`, or whose bytes disagree
with the sha its row recorded, refuses to pin: a fixture that cannot say
where it came from is the thing this corpus replaces.
