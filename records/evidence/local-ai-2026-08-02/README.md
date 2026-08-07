# Vendored evidence — local-ai, 2 August 2026

Raw measurement data copied out of
[`AdarGit008/local-ai`](https://github.com/AdarGit008/local-ai) so the claims in
`records/claims/` resolve from **this** repository rather than from a moving
branch in another one.

## Why it is here rather than linked

ADR-0004 makes a citation load-bearing. The failure it was written against —
found by the #109 audit — was roughly twenty-five citations pointing into a
directory that was gitignored in the source repository and had never been
readable by anyone. A commit permalink is a real improvement on that, and every
URL in the register is pinned to a sha. But a permalink still resolves through a
third party: it does not survive the repository being deleted, made private, or
having its history rewritten, and local-ai is an unarchived personal repository
that is still shipping.

`CLM-0004` was the acute case. It is this repository's only medium-confidence
empirical claim and it cited a single local-ai permalink; the 160 runs behind the
number were not here at all. Copying them is cheap now and impossible later,
which is the whole of #118's first bullet.

## What supports what

| Path | Supports |
|---|---|
| `data/context_exp/` | `CLM-0004` — bundle size vs first-pass acceptance. `summary_2026-07-28.md` is the write-up; `results_q3b.jsonl` and `results_qwen3.jsonl` are the 160 raw runs (2 models × 4 conditions × 20 tasks); `bundles/` are the three prompt bundles the conditions differ by |
| `research/context_size_experiment_2026-07-28.md` | `CLM-0004` — the experiment design, written before the run |
| `instrument/` | `CLM-0004` — the task set and harness that produced `data/context_exp/`, recovered under #167 and pinned to the commit the run was made at. See [`instrument/README.md`](instrument/README.md) |
| `data/humaneval_plus_*.jsonl` | `CLM-0005` — the stored completions both rates were measured on. Also the generation behind `data/capability-table.json`, cited by `CLM-0001` and `CLM-0003` |
| `data/humaneval_plus_summary_2026-07-26.md` | `CLM-0001`, `CLM-0005` — the original run's own pass rates, which are what make the re-evaluation checkable rather than self-reported |
| `premise/premise.jsonl` | `CLM-0005` — one row per completion with its `ast.parse` verdict |
| `premise/*_eval_results.json` | `CLM-0005` — EvalPlus per-task pass/fail over those same completions |
| `premise/measurement-record.json` | `CLM-0005` — the rig's own output record, carrying the argv and commit it ran at |

## Integrity

`MANIFEST.json` carries a sha256 per file and the source commit
(`55a084ecf74a3027bd90f3a4f95fb570812e34b7`). `tests/test_claims.py` recomputes
every digest, so a copy that drifts from what was measured fails the suite rather
than quietly becoming the new truth.

Two files postdate that manifest and are pinned separately, to
[`d201ea1`](https://github.com/AdarGit008/local-ai/tree/d201ea1): `premise/`'s
rows and eval results, produced by the run that measured them.

`instrument/`'s three files are pinned separately too, to
[`6d8c11d6`](https://github.com/AdarGit008/local-ai/tree/6d8c11d6) — the commit
the 2026-07-28 run was made at, which is not local-ai's HEAD. The manifest
records that as `instrument_commit` and per-entry `pinned_commit`.

The three `bundles/` entries carried `bytes` but no `sha256` and so were being
skipped by the digest test. They now carry one, because #167's Python arm uses
those files directly as its conditions: `c2.md` is `src/mcgyvr/prompts/python.md`
byte for byte, and an unpinned condition would leave the arm's ladder
uncheckable.

## Re-running

Everything here regenerates from a checkout of local-ai at `d201ea1`:

```
uv run python tools/mcgyvr_evidence.py --out <dir> premise --semantic
uv run python tools/mcgyvr_evidence.py --out <dir> vendor
```

The measurements this directory does **not** carry are the ones whose n did not
support their conclusion — breadth, repair, tokens, scope and deps were run on
the same date and are deliberately not vendored or cited here. They live at
`d201ea1` under `data/mcgyvr_evidence/2026-08-02/` and are pending a re-run
against task sets that can discriminate. A number without an n that supports it
is not evidence, and vendoring it here would imply otherwise.
