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

### Keys

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `version` | number (min 1) | no | `1` | Schema version this contract is written against. A contract declaring a version this build does not read is rejected rather than interpreted under the wrong rules. (orchestrator-facing) |
| `id` | text | **yes** | — | Identity: how this contract is referred to in records, telemetry and branch names. Letters, digits, dot, dash and underscore, up to 64 characters. e.g. fetch-helper-retry. (worker-facing) |
| `task_type` | one of `format`, `import_sort`, `lint_fix`, `rename_symbol`, `docstring`, `type_annotation`, `function_implementation`, `test_scaffold`, `bug_fix` | **yes** | — | What kind of work this is, from the declared vocabulary. The type decides whether the deterministic tier can execute the contract outright, and therefore whether a glob target is legal. (worker-facing) |
| `task` | text | **yes** | — | What to do, in words, addressed to the worker. Self-contained: a worker sees this and the rest of the worker-facing fields, never the conversation that produced them. (worker-facing) |
| `target` | text | **yes** | — | Where the result goes. Exactly one literal repo-relative path for any task type a model executes — a model worker's output has one destination, and a pattern would leave it guessing. A glob is legal only for a task type the deterministic tier executes outright. e.g. src/pkg/fetch.py. (worker-facing) |
| `target_content` | text | no | empty | The current content of `target`, verbatim, when the file already exists. Carried on the contract rather than read from the tree at dispatch so that a contract is self-contained and exactly reproducible: `parse(dumps(c))` round-trips the bytes a worker was actually sent. Empty means the target does not exist yet, or its content is not needed — a distinction the deterministic tier never asks about, because a tool reads the file itself. Deriving `limits.max_output_tokens` from this is #17; the schema only gives it somewhere to read from. (worker-facing) |
| `interface` | text | no | empty | What the result must expose — the signature, the name, the shape a caller depends on. Stated separately from `task` because it is the machine-checkable half of done. (worker-facing) |
| `deps` | list of blocks | no | — | Dependencies the target needs, as signatures rather than source. (worker-facing) |
| `stop_conditions` | list of text | no | `[]` | Explicit triggers on which the worker must stop and report BLOCKED instead of guessing — scope creep, an unknown API, an ambiguous directive. Required for any task type a model executes: guessing is the documented small-model failure mode these exist to prevent (#94), and a worker with no stated stop condition has no licence to refuse. (worker-facing) |
| `output_schema` | one of `whole_file`, `unified_diff` | no | `whole_file` | The shape the worker must reply in, declared so a runner can hand the model format instructions rather than hoping for a convention. `whole_file` is the single-file output protocol; `unified_diff` is a patch against the target. (worker-facing) |
| `context` | block | no | — | Budgets governing what may be assembled into the worker's prompt. (worker-facing) |
| `scope` | block | **yes** | — | The writable surface the gate enforces. Not worker-facing: the worker is told its one target, and scope is how the gate judges what actually changed. (orchestrator-facing) |
| `acceptance` | list of text | no | `[]` | Shell commands that must pass for the change to be accepted — the strongest signal the gate has. Each must also pass on the *unchanged* tree (the preflight refuses a suite that is already red), which is exactly why a command meant to demonstrate a defect cannot live here: it goes in `demonstration`. Arbitrary shell from a contract, so they run inside the per-task sandbox, never on the host. (orchestrator-facing) |
| `demonstration` | list of text | no | `[]` | Shell commands that demonstrate the defect: each must FAIL on the unchanged tree and pass after the change — the `failing_test_first` evidence, as a slot of its own because its baseline expectation is the opposite of `acceptance`'s (#183). Who authors it is #146's question; the schema only gives the answer somewhere to go. Runs in the same sandbox, under the same read-only rule. (orchestrator-facing) |
| `depends_on` | list of text | no | `[]` | Ids of the contracts that must complete before this one may run. Stated on the contract, so a plan can be ordered — and the parts of it that cannot run at all found — before a token is spent, the way `route.plan()` already is. A proposer's emission order is the order a model thought of things, not a dependency order, so ordering that is not written down here is ordering that does not exist. Not worker-facing: a worker is handed one task and never the plan around it, and a dependency that has landed is already in the tree it reads. e.g. ["write-fetch"]. (orchestrator-facing) |
| `risk` | one of `low`, `medium`, `high` | no | `medium` | How much a wrong answer costs. A floor on how cheap the work may start and how cheaply it may be verified, never a preference. Deterministic classification from type, prompt and scope is #16; a declared value may raise that classification, never lower it. (orchestrator-facing) |
| `verification` | block | no | — | How the change is judged once the gate has passed. (orchestrator-facing) |
| `limits` | block | no | — | Hard ceilings on what one execution of this contract may spend. (orchestrator-facing) |

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
| `context.max_input_tokens` | number (min 1) | no | `4096` | Hard ceiling the assembled worker prompt must fit under. Declared on the contract rather than inferred at dispatch so that a prompt which will not fit is a contract-level failure, caught before a rung is spent. (worker-facing) |

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
| `verification.policy` | one of `gate_only`, `model` | no | `gate_only` | How the change is judged. `gate_only` accepts on the deterministic gate alone — the whole acceptance bar in a keyless install. `model` additionally requires a fresh-context verifier to agree. (orchestrator-facing) |

#### `limits`

Hard ceilings on what one execution of this contract may spend.

| Key | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `limits.max_output_tokens` | number (min 1) | no | unset | Hard cap on the worker's reply, enforced in the runner. A reply cut off at the cap is a named failure and is never applied to a file. Left out, it is derived from what the task type's own required evidence says the reply has to be (`output_cap`) — which is why this is the one key in the schema with no static default: a single number for every type is wrong for at least one of them. Deriving it further from the target's own content is #17. (orchestrator-facing) |
| `limits.attempts` | number (min 1) | no | `2` | How many times a rung may be retried before escalating. Retrying forever on one rung is how a cheap task becomes an expensive one. (orchestrator-facing) |

### One minimal example per task type

Each example loads through the contract validator; they are checked by the
test suite, so copying one is copying a shape that is known to validate.

#### `format`

```yaml
id: format-pkg
task_type: format
task: Reformat the module with the project's formatter.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
```

#### `import_sort`

```yaml
id: sort-imports
task_type: import_sort
task: Order the module's imports with the project's import sorter.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
```

#### `lint_fix`

```yaml
id: lint-pkg
task_type: lint_fix
task: Apply the linter's own autofixes to the module.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
```

#### `rename_symbol`

```yaml
id: rename-fetch
task_type: rename_symbol
task: Rename fetch_page to fetch_document in the module.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
```

#### `docstring`

```yaml
id: doc-fetch
task_type: docstring
task: Write the docstring for fetch_document, stating what it returns on a 404.
target: src/pkg/fetch.py
interface: "def fetch_document(url: str, *, timeout_s: float = 5.0) -> str"
stop_conditions:
  - The 404 behaviour cannot be read from the code.
scope:
  allow: ["src/pkg/fetch.py"]
```

#### `type_annotation`

```yaml
id: annotate-fetch
task_type: type_annotation
task: Add type annotations to fetch_document and its helpers.
target: src/pkg/fetch.py
stop_conditions:
  - A helper's return type cannot be determined from its callers.
acceptance: ["mypy src/pkg/fetch.py"]
scope:
  allow: ["src/pkg/fetch.py"]
```

#### `function_implementation`

```yaml
id: impl-chunk
task_type: function_implementation
task: >-
  Implement chunk. Split a list into consecutive groups of at most size
  elements, preserving order; the last group is shorter when the length does
  not divide evenly. An empty list yields an empty list. Raise ValueError
  unless size is a positive integer.
target: src/pkg/chunk.py
interface: "def chunk(items: list[T], size: int) -> list[list[T]]"
stop_conditions:
  - Whether a size larger than the list is an error or one group is not stated.
acceptance: ["pytest -q tests/test_chunk.py"]
risk: low
scope:
  allow: ["src/pkg/chunk.py"]
```

#### `test_scaffold`

```yaml
id: test-chunk
task_type: test_scaffold
task: Write tests for chunk covering the empty list, an exact division and a remainder.
target: tests/test_chunk.py
interface: "def chunk(items: list[T], size: int) -> list[list[T]]"
deps:
  - path: src/pkg/chunk.py
    signature: "def chunk(items: list[T], size: int) -> list[list[T]]"
stop_conditions:
  - The expected result for a remainder group is not stated.
acceptance: ["pytest -q tests/test_chunk.py"]
scope:
  allow: ["tests/test_chunk.py"]
```

#### `bug_fix`

```yaml
id: fix-chunk-remainder
task_type: bug_fix
task: chunk drops the final short group when the length does not divide evenly; keep it.
target: src/pkg/chunk.py
interface: "def chunk(items: list[T], size: int) -> list[list[T]]"
stop_conditions:
  - The demonstrating test does not fail on the current code.
demonstration: ["pytest -q tests/test_chunk.py -k remainder"]
acceptance: ["pytest -q tests/test_chunk.py"]
scope:
  allow: ["src/pkg/chunk.py"]
```

## Step 2 — validate before spending anything

```
mcgyvr contract CONTRACT.yaml
```

Prints what the contract resolves to, or names the key that is wrong. Fix
the contract; never guess a field.

## Step 3 — run it, then read the result file

```
mcgyvr run CONTRACT.yaml --repo DIR [--sandbox tempdir] [--commit]
```

The run refuses unless it can say who typed it: Claude Code and Pi sessions
are detected from the environment, otherwise pass `--orchestrator ID`. A
ladder run needs a config (`mcgyvr init`, or `--config PATH`); the
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
