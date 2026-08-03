# Token-estimator error band — 3 August 2026

What [#117](https://github.com/AdarGit008/mcgyvr/issues/117) asks for: the error
of `orchestrator.read.estimate_tokens` — four characters per token, and it says
so — against the real tokenizers of the models the shipped capability table
measures. `units.jsonl` is one row per string the estimator was asked to count;
`summary.json` is the bands. Registered as **CLM-0011**.

Re-run:

```
uv sync --frozen --group measure
uv run python tools/tokens/measure.py --out records/measurements/tokens-2026-08-03
```

It fetches each frame at its pinned sha and each tokenizer from the model's own
repository. **No model is called** — a tokenizer is a vocabulary file, and
nothing here generates. `tokenizers` is in the `measure` dependency group, which
is not a default group, so `make setup` and CI never install it: the product
must not acquire a tokenizer, because that would defeat the point of having a
model-free proxy at all.

## The corpus is captured, not constructed

#117 says to measure "through the injectable `estimate` seam — the seam exists
for exactly this", and that is literally the method. A recording `estimate` is
passed to the real `explore()`, so **every string measured is a string
production actually asked the estimator to count**, produced by the real region
planner over real repositories. Nothing reimplements a window and no text was
hand-picked. Queries are each frame's own exported names, sorted and capped at
40 per frame — derived from the repository rather than chosen.

Frames are [`reach-2026-08-02`](../../corpora/reach-2026-08-02/)'s, reused rather
than re-pinned: one mature repository per launch language plus this one, already
enumerated and justified.

| frame | language | read regions | worker views |
|---|---|---|---|
| `pallets/click` | Python | 1,143 | 40 |
| `AdarGit008/mcgyvr` | Python | 646 | 40 |
| `immerjs/immer` | JS/TS | 478 | 40 |
| **total** | | **2,267** | **120** |

**n = 2,387 units**, median 930 characters.

## What is *not* measured

#117 asks for "a corpus of actual worker prompts". **There are none.** #25 owns
prompt assembly and is open; `check_prompt_fits` has no production caller yet.
So the corpus is the two things the estimator is applied to *today* — read
regions (the exploration budget) and worker-view documents (what the decomposer
sizes `context.max_input_tokens` from). The band is therefore a band over
prompt **content**. Whatever fixed wrapper #25 adds is unmeasured, and being
mostly prose its ratio should sit nearer the prose end than the code end — but
that is a prediction, not a measurement, and it is why this record says so
instead of implying coverage it does not have.

## Three vocabularies, not four

`identical_vocabularies` in `summary.json` reports
`[["qwen2.5-coder", "qwen3-coder"]]` — computed from the counts, not read off a
model card. Qwen3-Coder-30B-A3B ships Qwen2.5-Coder's 151,643-token vocabulary
and produced **identical counts on all 2,387 units**. Reporting both as
independent evidence would have inflated what the band rests on.

| vocabulary | tokenizer measured | vocab size |
|---|---|---|
| `qwen2.5-coder` (= `qwen3-coder`) | `Qwen/Qwen2.5-Coder-7B-Instruct` | 151,643 |
| `deepseek-coder-v2` | `deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct` | 100,000 |
| `gpt-oss` | `openai/gpt-oss-20b` | 199,998 |

## The band, signed

Signed because the directions are not interchangeable: **over-estimation costs
context**, **under-estimation costs a rejected request**. Error is
`(estimated − real) / real`, so negative is under-estimation.

| scope | vocabulary | n | median | p05 | p95 | under-estimated |
|---|---|---|---|---|---|---|
| overall | qwen2.5-coder | 2,387 | −0.8% | −17.6% | +16.3% | 51.4% |
| overall | deepseek-coder-v2 | 2,387 | **−17.9%** | **−31.1%** | +0.0% | **94.9%** |
| overall | gpt-oss | 2,387 | −0.5% | −16.9% | +16.4% | 51.1% |
| Python | qwen2.5-coder | 1,869 | +2.2% | −14.9% | +17.6% | 43.3% |
| Python | deepseek-coder-v2 | 1,869 | −17.1% | −28.9% | +0.6% | 94.0% |
| JS/TS | qwen2.5-coder | 518 | −7.9% | −22.9% | +5.9% | 80.7% |
| JS/TS | deepseek-coder-v2 | 518 | −21.6% | −35.2% | −7.2% | 98.3% |
| worker views | qwen2.5-coder | 120 | −11.8% | −16.1% | −5.8% | **100.0%** |
| worker views | deepseek-coder-v2 | 120 | −20.2% | −23.6% | −14.2% | **100.0%** |

Three things carry the result.

**The proxy is not unbiased, and the bias depends on the vocabulary.** On Qwen
and gpt-oss it is near-centred (median under 1%); on DeepSeek-Coder-V2 it
under-counts by ~18% at the median and under-counts on 95% of units. A 100,000-
token vocabulary simply splits the same text into more tokens than a 151,643- or
199,998-token one. Nothing about "four characters per token" knows which model
is on the other end.

**It is language-dependent.** JS/TS under-counts where Python is roughly
centred — −7.9% against +2.2% on Qwen. #117 asked for the band per language,
and the answer is that they are genuinely different populations.

**Worker-view documents are under-counted 100% of the time**, on every
vocabulary. That is the text `check_prompt_fits` will enforce against and the
text the decomposer already sizes from, so the bias is systematic exactly where
it matters most — dense JSON with signatures inside it is the shape the proxy
handles worst.

## The tail, and a wrong guess recorded

The extreme unit is **−73.3%**: an immer JS region, 3,456 characters, estimated
864 tokens, actually ~3,236 — about **1.07 characters per token**.

The obvious guess was non-ASCII text. **It is wrong**, and `non_ascii_share` is
a column so it could be checked rather than assumed: that unit is 0.0% non-ASCII.
Only 4 of 2,387 units carry any meaningful non-ASCII at all (they do skew worse,
median −22% to −26%, but n = 4 supports nothing).

The tail is dense **structured-literal** content — code shaped like data. The
densest whole file in that frame is `__tests__/patch.js` at 2.77 characters per
token, a fixture of `{op, path, value}` object literals; a 25-line window can
land on a patch denser than the file average. Punctuation-heavy literals
tokenize near one character per token, and four-characters-per-token has no way
to know.

The band is otherwise stable across size: 200–1,000 chars and 1,000–4,000 chars
give the same medians to within a point.

## What this does not settle

The residual. A 32% reserve sized on the worst vocabulary's p05 leaves a
measured ~5% of units still under-reserved — **stated**, where before it was
unquantified, which is the whole of the improvement. Closing that residual means
either a real tokenizer at the seam (which #117 forbids as a runtime dependency)
or a per-vocabulary reserve, which needs the rung to say which vocabulary it
serves. `Rung` is "a name and a model, and by construction nothing else"
(`pool.py`), so that is a design change, not a constant.
