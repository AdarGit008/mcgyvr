---
name: mcgyvr
description: "Use whenever a scoped piece of coding work can be offloaded to mcgyvr: author a task contract, validate it, run it, read the result file, replan from the findings. Invoke it explicitly when you are about to delegate; the schema below is the only contract vocabulary."
disable-model-invocation: true
---

<!-- Code generated from src/mcgyvr/contract.py and src/mcgyvr/docgen.py by `make docs`. DO NOT EDIT. -->

# /mcgyvr

Offload one scoped piece of coding work to mcgyvr. You author a *contract*
(one target, one task, one way to judge it), mcgyvr gates every answer
deterministically, and leaves the accepted file in the working tree. It
never commits unless told to, and it never writes anything else into the
repository.

## Step 1 — author a contract

One YAML file. Every key below is the contract schema in
`src/mcgyvr/contract.py`, rendered by `make docs`; unknown keys are refused,
and every rejection names the key and what a valid value looks like.
Pick the `task_type` first: it decides what evidence the contract must
carry. `mcgyvr catalog <type>` prints the type's guarantee.

### Keys

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `version` | number (min 1) | no | `1` | Schema version this contract is written against. A contract declaring a version this build does not read is rejected rather than interpreted under the wrong rules. (orchestrator-facing) |
| `id` | text | **yes** | — | Identity: how this contract is referred to in records, telemetry and branch names. Letters, digits, dot, dash and underscore, up to 64 characters. e.g. fetch-helper-retry. (worker-facing) |
| `task_type` | one of `format`, `import_sort`, `lint_fix`, `rename_symbol`, `docstring`, `type_annotation`, `function_implementation`, `test_scaffold`, `bug_fix` | **yes** | — | What kind of work this is, from the declared vocabulary. The type decides what evidence the contract must carry, and therefore whether a glob target is legal. (worker-facing) |
| `task` | text | **yes** | — | What to do, in words, addressed to the worker. Self-contained: a worker sees this and the rest of the worker-facing fields, never the conversation that produced them. (worker-facing) |
| `target` | text | **yes** | — | Where the result goes. Exactly one literal repo-relative path for any task type a model executes — a model worker's output has one destination, and a pattern would leave it guessing. A glob is legal only for a task type that is executed deterministically. e.g. src/pkg/fetch.py. (worker-facing) |
| `target_content` | text | no | empty | The current content of `target`, verbatim, when the file already exists. Carried on the contract rather than read from the tree at dispatch so that a contract is self-contained and exactly reproducible: `parse(dumps(c))` round-trips the bytes a worker was actually sent. Empty means the target does not exist yet, or its content is not needed — a distinction deterministic execution never asks about, because a tool reads the file itself. Deriving `limits.max_output_tokens` from this is #17; the schema only gives it somewhere to read from. (worker-facing) |
| `interface` | text | no | empty | What the result must expose — the signature, the name, the shape a caller depends on. Stated separately from `task` because it is the machine-checkable half of done. (worker-facing) |
| `deps` | list of blocks | no | — | Dependencies the target needs, as signatures rather than source. (worker-facing) |
| `stop_conditions` | list of text | no | `[]` | Explicit triggers on which the worker must stop and report BLOCKED instead of guessing — scope creep, an unknown API, an ambiguous directive. Required for any task type a model executes: guessing is the documented small-model failure mode these exist to prevent (#94), and a worker with no stated stop condition has no licence to refuse. (worker-facing) |
| `output_schema` | one of `whole_file`, `unified_diff` | no | `whole_file` | The shape the worker must reply in, declared so a runner can hand the model format instructions rather than hoping for a convention. `whole_file` is the single-file output protocol; `unified_diff` is a patch against the target. (worker-facing) |
| `context` | block | no | — | Budgets governing what may be assembled into the worker's prompt. (worker-facing) |
| `scope` | block | **yes** | — | The writable surface the gate enforces. Not worker-facing: the worker is told its one target, and scope is how the gate judges what actually changed. (orchestrator-facing) |
| `acceptance` | list of text | no | `[]` | Shell commands that must pass for the change to be accepted — the strongest signal the gate has. Each must also pass on the *unchanged* tree (the preflight refuses a suite that is already red), which is exactly why a command meant to demonstrate a defect cannot live here: it goes in `demonstration`. Arbitrary shell from a contract, so they run inside the per-task sandbox, never on the machine you ran mcgyvr from. (orchestrator-facing) |
| `demonstration` | list of text | no | `[]` | Shell commands that demonstrate the defect: each must FAIL on the unchanged tree and pass after the change — the `failing_test_first` evidence, as a slot of its own because its baseline expectation is the opposite of `acceptance`'s (#183). Who authors it is #146's question; the schema only gives the answer somewhere to go. Runs in the same sandbox, under the same read-only rule. (orchestrator-facing) |
| `depends_on` | list of text | no | `[]` | Ids of the contracts that must complete before this one may run. Stated on the contract, so a plan can be ordered — and the parts of it that cannot run at all found — before a token is spent, the way `route.plan()` already is. A proposer's emission order is the order a model thought of things, not a dependency order, so ordering that is not written down here is ordering that does not exist. Not worker-facing: a worker is handed one task and never the plan around it, and a dependency that has landed is already in the tree it reads. e.g. ["write-fetch"]. (orchestrator-facing) |
| `risk` | one of `low`, `medium`, `high` | no | `medium` | How much a wrong answer costs, never a preference. A declared value bounds how cheaply the work may start and how cheaply it may be verified: `high` refuses the cheapest of either, `low` allows them. Deterministic classification from type, prompt and scope is #16; a declared value may raise that classification, never lower it. (orchestrator-facing) |
| `verification` | block | no | — | How the change is judged once the gate has passed. (orchestrator-facing) |
| `limits` | block | no | — | Hard ceilings on what one execution of this contract may spend. (orchestrator-facing) |
| `rename` | block | no | — | Which symbol becomes which, for `task_type: rename_symbol`. The one task type mcgyvr executes in-process rather than by running a program, and the only one whose input is not fully determined by `target`: a rename fans across every file that references the symbol, so the pair has to be said. Meaningless on any other type and ignored there. (orchestrator-facing) |

#### `deps`

Dependencies the target needs, as signatures rather than source.

An ordered list. Each entry takes these keys:

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `deps.path` | text | **yes** | — | Repo-relative path of the dependency this signature came from. (worker-facing) |
| `deps.signature` | text | **yes** | — | The function or class signature with its type annotations — NOT its body. Hierarchical context pruning measured signature-only dependency context as improving accuracy while cutting context roughly sixfold (#94, #96): a body invites copying, a signature states the interface. (worker-facing) |
| `deps.note` | text | no | empty | One sentence on how the target is expected to use this dependency. (worker-facing) |

#### `context`

Budgets governing what may be assembled into the worker's prompt.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `context.max_input_tokens` | number (min 1) | no | `4096` | Hard ceiling the assembled worker prompt must fit under. Declared on the contract rather than inferred at dispatch so that a prompt which will not fit is a contract-level failure, caught before anything is dispatched. (worker-facing) |

#### `scope`

The writable surface the gate enforces. Not worker-facing: the worker is told its one target, and scope is how the gate judges what actually changed.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `scope.allow` | list of globs | **yes** | — | Glob patterns the worker's change may touch. An empty allow list permits nothing (`mcgyvr.scope` fails closed), so a contract that declares none is rejected rather than silently unable to act. e.g. ["src/**/*.py"]. (orchestrator-facing) |
| `scope.forbid` | list of globs | no | `[]` | Glob patterns that override `allow`. Forbid wins ties, which is the safe direction for an autonomous gate. (orchestrator-facing) |

#### `verification`

How the change is judged once the gate has passed.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `verification.policy` | one of `gate_only`, `model` | no | `gate_only` | How the change is judged. `gate_only` accepts on the deterministic gate alone — the whole acceptance bar in a keyless install. `model` additionally requires a fresh-context reviewer to agree. (orchestrator-facing) |

#### `limits`

Hard ceilings on what one execution of this contract may spend.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `limits.max_output_tokens` | number (min 1) | no | unset | The cap this contract declares on the worker's reply. A reply cut off at the cap is a named failure and is never applied to a file. Declare it for any task type a model executes: `mcgyvr contract` and `mcgyvr run` refuse a model contract that leaves it out (exit 2) and print the figure the type's own evidence would derive (`output_cap`) as the value to start from. It is the one key in the schema with no static default: a single number for every type is wrong for at least one of them. Deriving it from the target's own content is #17. What this states is what the *work* is worth. (orchestrator-facing) |
| `limits.max_window_fraction` | decimal number (min 0.0, max 1.0) | no | unset | The largest share of the context window this contract may claim: its assembled prompt and `max_output_tokens` together, over the whole window. A different question from whether the two fit, which `context.max_input_tokens` already bounds — a contract that fits with nothing to spare leaves nothing to hold anything beside it and nothing to absorb an estimate that ran long. Declared here because it is a statement about this unit of work, and enforced wherever the work is executed. Unset means no share is enforced, which is not the same as 1.0: a contract that declared none is recorded as having declared none. e.g. 0.75 to leave a quarter of the window clear. (orchestrator-facing) |
| `limits.attempts` | number (min 1) | no | `2` | How many times the work may be retried before escalating. Retrying forever is how a cheap task becomes an expensive one. (orchestrator-facing) |

#### `rename`

Which symbol becomes which, for `task_type: rename_symbol`. The one task type mcgyvr executes in-process rather than by running a program, and the only one whose input is not fully determined by `target`: a rename fans across every file that references the symbol, so the pair has to be said. Meaningless on any other type and ignored there.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `rename.from` | text | no | empty | The symbol as it is written today. Stated rather than read out of `task`: mcgyvr renames every reference the index resolved across every file that holds one, and a name inferred from prose is a multi-file rewrite resting on a guess about English. A worker asked to guess would guess; a program must be told. e.g. fetch_page. (orchestrator-facing) |
| `rename.to` | text | no | empty | What the symbol becomes. Must be a legal identifier — the rename rewrites text, and a `to` that is not a name would produce a tree that no longer parses while reporting success. e.g. fetch_document. (orchestrator-facing) |

### One minimal example per task type

`skills/mcgyvr/references/examples.md` carries one per type,
each loaded through the contract validator by the test suite, so copying
one is copying a shape that is known to validate. One file away, and it
costs nothing until it is opened.

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
mcgyvr run CONTRACT.yaml --repo DIR [--config PATH] [--sandbox tempdir] [--commit]
```

The run refuses unless it can say who typed it: Claude Code and Pi sessions
are detected from the environment, otherwise pass `--orchestrator ID`.
The last stdout line is `result: <path>`:
everything above it is scrollback, and everything the run came to is in
that file, under mcgyvr's own journal directory — never in the repository.
Read the file, not the scrollback. No `result:` line with exit 1 or 2 means
the run never started (the contract did not load, the repo is not git, or
no session could be named) or the result file could not be written; either
way the reason is on stderr, and in the second case that line also says
what the run came to. The file's keys:

- `outcome` — one word, and what it leaves to do next:
  - `accepted` — the work landed; nothing to replan.
  - `rejected` — the deterministic gate refused the change; the
    findings name the check a different contract has to answer.
  - `delivery_refused` — judged acceptable, but the write to the tree
    was refused; `detail` says what was in the way. Clear it, rerun.
  - `ladder_spent` — everything this machine offers was tried and none
    produced an acceptable change. Narrow the contract: raising a
    number changes what it costs to fail, not whether it fails.
  - `escalation_ceiling` — stopped at a ceiling on how far the work may
    be moved up, with dearer tries never entered; that says it was not
    allowed to try, not that it cannot. Rerun where those moves are
    paid for.
  - `attempt_ceiling` — stopped at what one task may spend, which
    bounds the bill and not the ability. Rerun against a budget that
    can pay for it.
  - `nothing_to_run` — nothing on this machine offered to do this work
    at all, so the machine stopped it and not the work. A different
    contract cannot fix it: `skills/mcgyvr/SETUP.md` can.
  - `declined_throughout` — everything offered stepped aside without
    spending an attempt, so nothing claims a contract of this shape.
    A different contract cannot fix this either; that same file can.
  - `error` — an exception before any verdict was reached: the failure
    is in the machinery, not the work. `detail` names the cause.
- `attempts[]` — every try: `rung`, `attempt`, `verdict` (`passed`,
  `failed`, `declined`, `error`), `detail`, `findings` (the gate's lines
  behind a failure), `attempt_id`, `draw`, `draws`, `rows`. `draws` is the
  breadth the attempt asked for (`breadth.draws`), whatever the verdict;
  `rows` is how many of those draws left a journal row, which is `draws`
  unless the attempt raised part-way and `0` for a try that declined or
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
more on the same answer.

`nothing_to_run` and `declined_throughout` are the exception: neither is
fixable by writing a different contract, because both say this machine
offered nothing that would do the work. Rewriting only relocates the same
answer. Report it to whoever owns the machine; the remedy is in
`skills/mcgyvr/SETUP.md`.

When `outcome` is `accepted`, the change is in `target`, uncommitted.
Review it there and commit it yourself. To have mcgyvr commit instead, run
with `--commit` on a tree where `target` is clean: mcgyvr refuses to
overwrite an edited or uncommitted target, so restore it first
(`git checkout -- <target>`) rather than rerunning on top of the last run.
