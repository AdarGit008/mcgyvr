# The instrument behind CLM-0004

The Python task set, the harness that ran it and the shell script that drove
both, copied out of [`AdarGit008/local-ai`](https://github.com/AdarGit008/local-ai)
at [`6d8c11d6`](https://github.com/AdarGit008/local-ai/tree/6d8c11d6) — the
commit that produced `../data/context_exp/`.

## Why it is here

`../data/context_exp/` has been vendored since 2026-08-02: the 160 rows, the
three bundles and the write-up. What was never here is **the thing that
generated them**. #167 is what that cost. CLM-0012 measured the JS/TS bundle
flat and could not say whether the reading was about the *language* or about
the *serving stack*, because the clean control — CLM-0004's own Python ladder,
re-run on a reachable rig — needed a task set that had been left in another
repository. Rebuilding twenty Python tasks from their ids would have been
authoring a new instrument and calling it a replication.

It had not been left anywhere unreachable. `mvp/instrumentation/` was still
there, and the whole of it is 50 KB.

| File | What it is |
|---|---|
| `context_tasks.py` | The 20 tasks: `id`, `type`, the rendered contract, the acceptance script and the reference solution, one dict each |
| `context_exp.py` | The harness — bundle as system prompt, one dispatch per cell, acceptance in a temp directory, one remediation round, resume-safe rows |
| `run_context_exp.sh` | The driver that ran the four conditions against a `llama-server` endpoint |

## Which commit, and why not HEAD

The run is dated 2026-07-28 and both Python files have been touched since, so
HEAD is not the artefact. What is vendored is `6d8c11d6` — the commit the run
was made at.

The difference turns out not to matter, and that is checkable rather than
assumed:

- **`context_tasks.py`** differs from HEAD only in ruff's quote normalisation
  (`'''` → `"""`, 72 lines). Loading both and serialising `TASKS` produces
  identical output — same ids, same types, same contracts, same acceptance
  scripts, same references. **The task set has not drifted since it was
  measured.**
- **`context_exp.py`** differs by ruff's line wrapping plus one docstring added
  under local-ai's own #51, noting that its `extract_code` is deliberately a
  standalone copy. No expression changed.
- **`run_context_exp.sh`** is byte-identical at both commits.

That check is the reason this copy can be called the original instrument
instead of a later version of it.

## What it is used for

Two things, and they are not the same thing:

1. **`context_exp.py` runs as it stands**, against an endpoint it was never
   pointed at. That is #167's control: the tasks, the acceptance, the prompt
   assembly and the extractor are all the ones CLM-0004 measured, so the
   serving stack is the only thing that changed.
2. **`context_tasks.py` is the source the ported task set was written from.**
   `tools/bundle/python/tasks/` carries the same twenty tasks as mcgyvr
   contracts, so they can run through the same rig the JS/TS arm did. The
   acceptance scripts and reference solutions there are copied from this file
   verbatim; the contracts are not, because mcgyvr renders its own user message
   from structured fields rather than accepting a pre-rendered one.

## Integrity

`../MANIFEST.json` carries a sha256 per file and `pinned_commit` for these
three, which postdate its `source_commit`. `tests/test_claims.py` recomputes
every digest.

## Running it

`context_exp.py` needs `requests` and an OpenAI-compatible endpoint, and it
takes `--base-url`, `--model`, `--conditions`, `--tasks`, `--out` and
`--no-remediate`. What it does **not** take is a bundle directory: it computes
one as `parents[2]/data/context_exp/bundles`, which is a fact about a local-ai
checkout's shape.

Running it from here therefore means rebuilding that shape around it rather than
editing it — the two Python files under `mvp/instrumentation/` and the three
vendored bundles under `data/context_exp/bundles/`, in a temporary tree. Editing
two path constants would have been easier and would have forfeited the only
property this arm has: that nothing about the instrument changed. See
`records/measurements/python-bundle-2026-08-07/README.md` for the exact
invocation and what came out.
