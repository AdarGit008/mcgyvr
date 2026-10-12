---
name: mcgyvr
description: "Use whenever coding work can be delegated to a local model ladder: author a task contract, validate it, run it, read the result file, replan from the findings. Always on; the schema below is the only contract vocabulary."
---

<!-- Code generated from src/mcgyvr/contract.py and src/mcgyvr/docgen.py by `make docs`. DO NOT EDIT. -->

# /mcgyvr

Offload one scoped piece of coding work to mcgyvr's worker ladder. You author
a *contract* (one target, one task, one way to judge it), mcgyvr climbs its
ladder of local models cheapest-first, gates every answer deterministically,
and leaves the accepted file in the working tree. It never commits unless
told to, and it never writes anything else into the repository.

## Step 1 — author a contract

One YAML file. Every key below is the contract schema in
`src/mcgyvr/contract.py`, rendered by `make docs`; unknown keys are refused,
and every rejection names the key and what a valid value looks like.
Pick the `task_type` first: it decides which family may start the work and
what evidence the contract must carry. `mcgyvr catalog <type>` prints the
type's guarantee.

(The contract keys and per-type examples this copy carried are cut: they
named a task vocabulary that no longer exists, and the upgrade under test
reads only that this is a real SKILL.md carrying the setup step.)

## Step 2 — validate before spending anything

```
mcgyvr contract CONTRACT.yaml
```

Prints what the contract resolves to, or names the key that is wrong. Fix
the contract; never guess a field. A contract a model executes must
declare `limits.max_output_tokens`, or this and `run` refuse it (exit 2)
and print the figure to start from: a reply cut at a cap nobody chose
is spent silently.

## Step 3 — run it, then read the result file

```
mcgyvr run CONTRACT.yaml --repo DIR [--sandbox tempdir] [--commit]
```

The run refuses unless it can say who typed it: Claude Code and Pi sessions
are detected from the environment, otherwise pass `--orchestrator ID`. A
ladder run needs a config (`mcgyvr setup`, or `--config PATH`); the
deterministic floor does not. The last stdout line is `result: <path>`:
everything above it is scrollback, and everything the run came to is in
that file, under mcgyvr's own journal directory — never in the repository.
Read the file, not the scrollback. No `result:` line with exit 1 or 2 means
the run never started (the contract did not load, the repo is not git, or
no session could be named) or the result file could not be written; either
way the reason is on stderr, and in the second case that line also says
what the run came to. The file's keys:

- `outcome` — `accepted`, `rejected` (deterministic gate),
  `delivery_refused` (accepted, but the write to the tree was refused; see
  `detail`), or the word the ladder halted on (`ladder_spent`,
  `escalation_ceiling`, `attempt_ceiling`, `nothing_to_run`,
  `declined_throughout`, `error`).
- `attempts[]` — every rung tried: `rung`, `attempt`, `verdict` (`passed`,
  `failed`, `declined`, `error`), `detail`, `findings` (the gate's lines
  behind a failure), `attempt_id`, `draw`, `draws`, `rows`. `draws` is the
  breadth the attempt asked for (`breadth.draws`), whatever the verdict;
  `rows` is how many of those draws left a journal row, which is `draws`
  unless the attempt raised part-way and `0` for a rung that declined or
  raised before dispatching. `draw` is the draw the entry is about, and is
  `null` — with `attempt_id` `null` beside it — on an `error` no single
  dispatch caused: `rows: 0` means it raised before dispatching at all,
  and anything more means it raised past draw `rows - 1`.
- `findings` — the deterministic gate's findings for a contract that
  dispatched nothing.
- `committed`, `commit`, `branch`, `handoff` — where the work went. Without
  `--commit` the accepted file is left in the working tree, uncommitted.
- `target`, `contract`, `task_type`, `orchestrator`, `run`, `session_file`,
  `journal`, `exit_code`.
- `copy_errors` — a `--record DIR` copy that could not be written, and
  why. Empty on almost every run. mcgyvr's own record under `journal`
  is complete whatever this says; a copy is not a sink and its failure
  does not stop a run.

Every run is journaled under the config's `journal.dir` and nothing on
the command line moves it — that one directory is where every run there
has ever been can be counted, which is the only thing that makes the
record worth keeping. Deterministic runs are there too, as a row naming
the program that did the work with `tier: deterministic` and no prompt
or reply beside it. `--record DIR` adds a complete second copy for your
own use; `--result PATH` says where you read the result file.

Exit codes: 0 accepted, 1 not accepted or error, 2 usage (including no
session to file the run under).

## Step 4 — replan from the findings, never retry the same contract

A failed attempt already had its retries inside the run. When `outcome` is
not `accepted`, read `attempts[].findings`: each line is one reason the gate
refused. Write a *different* contract — narrower target, an acceptance
command that states the requirement, a stop condition for what was
ambiguous — and go back to step 2. Running the same contract again spends
the ladder on the same answer.

When `outcome` is `accepted`, the change is in `target`, uncommitted.
Review it there and commit it yourself. To have mcgyvr commit instead, run
with `--commit` on a tree where `target` is clean: mcgyvr refuses to
overwrite an edited or uncommitted target, so restore it first
(`git checkout -- <target>`) rather than rerunning on top of the last run.
