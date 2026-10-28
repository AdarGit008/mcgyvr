---
name: mcgyvr-direct
description: "Run task contracts you wrote with mcgyvr, a CLI that runs each on deterministic tools, local models or API models and keeps only what its deterministic gate accepts. Pass contract files or a directory of them: mcgyvr vets each one as it vets a proposal, prints every refusal with what to change, and runs the rest in dependency order. Use it when a change has one target and a way to judge it, or for work /mcgyvr refused or could not finish: write the contracts, validate them, run them, read the result files, replan from the findings. It never loads itself; invoke it with /mcgyvr-direct <files|dir>. The schema below is the only contract vocabulary."
disable-model-invocation: true
---

<!-- Code generated from src/mcgyvr/contract.py and src/mcgyvr/docgen.py by `make docs`. DO NOT EDIT. -->

# /mcgyvr-direct

Run contracts you wrote. A *contract* is one target, one task and one way to
judge it; mcgyvr vets each one exactly as it vets a proposal from a prompt,
runs the ones that pass in the order their dependency tree allows, gates
every answer deterministically, and leaves an accepted `code` change in the
working tree. It never commits unless told to, and it never writes anything
else into the repository. No proposer is asked: refusals and spent work come
back to you.

## Step 1 — write the contracts

One YAML or JSON file per contract. Every key below is the contract schema in
`src/mcgyvr/contract.py`, rendered by `make docs`; unknown keys are refused,
and every rejection names the key and what a valid value looks like. Pick
the `task_type` first. For `code`, evidence is derived from the contract's
own fields, never chosen; `operation:` has a tool make the change instead.
`mcgyvr catalog <type>` prints the type's guarantee. A contract that needs
another's work names its id in `depends_on`.

### Keys

**`version`**
- type: number (min 1); optional, default `1`
- description: Schema version this contract is written against. A contract declaring a version this build
  does not read is rejected rather than interpreted under the wrong rules.

**`id`**
- type: text; required
- description: Identity: how this contract is referred to in records, telemetry and branch names.
  Letters, digits, dot, dash and underscore, up to 64 characters. e.g. fetch-helper-retry.
  (worker-facing)

**`task_type`**
- type: one of `code`; required
- description: What kind of work this is, from the declared vocabulary. The type decides what evidence
  the contract must carry and how its result is judged. (worker-facing)

**`operation`**
- type: one of `format`, `import_sort`, `lint_fix`, `rename_symbol`; optional, default empty
- description: A deterministic operation a tool performs instead of a model, for `task_type: code`; its
  own guarantee and evidence apply, and the target may be a glob.

**`task`**
- type: text; required
- description: What to do, in words, addressed to the worker. Self-contained: a worker sees this and the
  rest of the worker-facing fields, never the conversation that produced them. (worker-facing)

**`target`**
- type: text; required
- description: Where the result goes. Exactly one literal repo-relative path for any contract a model
  executes — a model worker's output has one destination, and a pattern would leave it guessing. A glob
  is legal only for a contract with a deterministic `operation`. e.g. src/pkg/fetch.py. (worker-facing)

**`target_content`**
- type: text; optional, default empty
- description: The current content of `target`, verbatim, when the file already exists. A contract that
  carries it is self-contained: `parse(dumps(c))` round-trips the bytes a worker is sent. Empty means the
  target does not exist yet, or the contract did not carry it: the worker is then given the file as the
  sandbox workspace holds it at dispatch, and a deterministic tool reads the file itself. (worker-facing)

**`interface`**
- type: text; optional, default empty
- description: What the result must expose — the signature, the name, the shape a caller depends on.
  Stated separately from `task` because it is the machine-checkable half of done. (worker-facing)

**`deps`**
- type: list of blocks; optional
- description: Dependencies the target needs, as signatures rather than source. (worker-facing)

**`stop_conditions`**
- type: list of text; optional, default `[]`
- description: Explicit triggers on which the worker must stop and report BLOCKED instead of guessing —
  scope creep, an unknown API, an ambiguous directive. Required when a model writes a `whole_file` reply,
  the one whose refusal is caught and escalated: guessing is the documented small-model failure mode
  these exist to prevent. Start from `<task_type> on <target> would require deciding something the
  contract does not state — report BLOCKED rather than guess`. (worker-facing)

**`output_schema`**
- type: one of `whole_file`, `unified_diff`; optional, default `whole_file`
- description: The shape the worker must reply in, declared so a runner can hand the model format
  instructions rather than hoping for a convention. `whole_file` is the single-file output protocol.
  `unified_diff` validates here and is refused before dispatch. (worker-facing)

**`sources`**
- type: list of text; optional, default `[]`
- description: Repo files given whole to the worker as `[1]`, `[2]`, …; a missing, binary or secret one
  is refused. (worker-facing)

**`context`**
- type: block; optional
- description: Budgets governing what may be assembled into the worker's prompt. (worker-facing)

**`scope`**
- type: block; required
- description: The writable surface the gate enforces. Not worker-facing: the worker is told its one
  target, and scope is how the gate judges what actually changed.

**`acceptance`**
- type: list of text; optional, default `[]`
- description: Commands, one per entry, split like a shell would split them (quotes respected) and
  executed directly with no shell: no `VAR=x` prefix, `&&`, pipes or redirects (`mcgyvr contract` refuses
  them; write `env VAR=x cmd`, or commit a script). Each must pass for the change to be accepted — the
  strongest signal the gate has — and also on the *unchanged* tree (the preflight refuses a suite that is
  already red), which is why a command meant to demonstrate a defect goes in `demonstration`. Arbitrary
  code from a contract: they run inside the per-task sandbox — a container in `docker` mode, a throwaway
  workspace on your own machine in `tempdir` mode.

**`demonstration`**
- type: list of text; optional, default `[]`
- description: Commands that demonstrate the defect: each must FAIL on the unchanged tree and pass after
  the change — the `failing_test_first` evidence, as a slot of its own because its baseline expectation
  is the opposite of `acceptance`'s. Written, run and sandboxed exactly like `acceptance`; what it leaves
  behind is cleaned up.

**`no_semantic_change`**
- type: boolean; optional, default `false`
- description: Whether the change must leave the parsed structure untouched apart from the region the
  task is allowed to touch. A flag rather than a task type: for `task_type: code` it derives the
  `no_semantic_change` evidence, and for every other type it is ignored. Defaults to false.

**`type_check`**
- type: boolean; optional, default `false`
- description: Whether the project's own type checker must pass on the changed target. A flag rather than
  a task type: for `task_type: code` it derives the `type_check` evidence, and for every other type it is
  ignored. Defaults to false.

**`depends_on`**
- type: list of text; optional, default `[]`
- description: Ids of the contracts that must complete before this one may run. Stated on the contract,
  so a plan can be ordered — and the parts of it that cannot run at all found — before a token is spent,
  the way `route.plan()` already is. A proposer's emission order is the order a model thought of things,
  not a dependency order, so ordering that is not written down here is ordering that does not exist. Not
  worker-facing: a worker is handed one task and never the plan around it, and a dependency that has
  landed is already in the tree it reads. e.g. ["write-fetch"].

**`verification`**
- type: block; optional
- description: How the change is judged once the gate has passed.

**`limits`**
- type: block; optional
- description: Hard ceilings on what one execution of this contract may spend.

**`start_rung`**
- type: text; optional, default empty
- description: The ladder rung this contract's climb starts on, decided ahead of time — what
  `mcgyvr.triage.triage_ahead` asks the `jev` unit, stored with the contract so every later run starts
  there without asking again. The rungs below it are skipped, not spent, and escalation goes on upward
  from it; it wins over the config's `triage`. A rung the ladder does not list, or one this contract's
  climb does not offer, is refused before anything is dispatched. Not worker-facing. e.g. local_qwen-14b.

**`rename`**
- type: block; optional
- description: Which symbol becomes which, for `operation: rename_symbol`. The one operation mcgyvr
  executes in-process rather than by running a program, and the only one whose input is not fully
  determined by `target`: a rename fans across every file that references the symbol, so the pair has to
  be said. Meaningless on any other contract and ignored there.

**`replan`**
- type: block; optional
- description: Where this contract came from when it was proposed in place of one whose ladder was spent:
  the id it replaces and the re-plan round. Written by the batch that re-planned it, never by hand. Not
  worker-facing.

#### `deps`

Dependencies the target needs, as signatures rather than source.

An ordered list. Each entry takes these keys:

**`deps.path`**
- type: text; required
- description: Repo-relative path of the dependency this signature came from. (worker-facing)

**`deps.signature`**
- type: text; required
- description: The function or class signature with its type annotations — NOT its body: a body invites
  copying, a signature states the interface. (worker-facing)

**`deps.note`**
- type: text; optional, default empty
- description: One sentence on how the target is expected to use this dependency. (worker-facing)

#### `context`

Budgets governing what may be assembled into the worker's prompt.

**`context.max_input_tokens`**
- type: number (min 1); optional, default `4096`
- description: Hard ceiling the assembled worker prompt must fit under. Declared on the contract rather
  than inferred at dispatch so that a prompt which will not fit is a contract-level failure, caught
  before anything is dispatched. (worker-facing)

#### `scope`

The writable surface the gate enforces. Not worker-facing: the worker is told its one target, and scope
is how the gate judges what actually changed.

**`scope.allow`**
- type: list of globs; required
- description: Glob patterns the worker's change may touch. An empty allow list permits nothing
  (`mcgyvr.scope` fails closed), so a contract that declares none is rejected rather than silently unable
  to act. e.g. ["src/**/*.py"].

**`scope.forbid`**
- type: list of globs; optional, default `[]`
- description: Glob patterns that override `allow`. Forbid wins ties, which is the safe direction for an
  autonomous gate.

#### `verification`

How the change is judged once the gate has passed.

**`verification.policy`**
- type: one of `gate_only`, `model`; optional, default `gate_only`
- description: How the change is judged. `gate_only` is honoured only for work a deterministic tool does;
  work a model does is raised to `model`, which asks a fresh-context reviewer to agree. An install with
  no reviewer labels such an acceptance unverified.

#### `limits`

Hard ceilings on what one execution of this contract may spend.

**`limits.max_output_tokens`**
- type: number (min 1); optional, default unset
- description: Not sent, and not needed: every model request is sent the most its unit can give — the
  unit's `output_tokens`, clamped to the room its `window` leaves once the prompt is paid for — so no
  contract caps a reply below what its unit serves. Still read, so a contract that states it loads; it
  caps nothing. A reply cut off at the unit's maximum is a named failure, never applied to a file.

**`limits.max_window_fraction`**
- type: decimal number (min 0.0, max 1.0); optional, default unset
- description: The largest share of the context window this contract's assembled prompt may claim, as
  charged, over the whole window. The reply is sent the unit's maximum within the room the prompt leaves,
  so this is what keeps that room from being crowded out: a prompt held to the share leaves the reply at
  least the rest. A different question from whether the prompt fits, which `context.max_input_tokens`
  already bounds. Declared here because it is a statement about this unit of work, and checked before the
  work is sent. The run's `max_window_fraction` caps it: the stricter of the two applies. Unset is not
  1.0: a contract that declared none is recorded as having declared none. e.g. 0.75 to leave the reply at
  least a quarter of the window.

**`limits.attempts`**
- type: number (min 1); optional, default `2`
- description: How many times the work may be retried before escalating. Retrying forever is how a cheap
  task becomes an expensive one.

#### `rename`

Which symbol becomes which, for `operation: rename_symbol`. The one operation mcgyvr executes in-process
rather than by running a program, and the only one whose input is not fully determined by `target`: a
rename fans across every file that references the symbol, so the pair has to be said. Meaningless on any
other contract and ignored there.

**`rename.from`**
- type: text; optional, default empty
- description: The symbol as it is written today. Stated rather than read out of `task`: mcgyvr renames
  every reference the index resolved across every file that holds one, and a name inferred from prose is
  a multi-file rewrite resting on a guess about English. A worker asked to guess would guess; a program
  must be told. e.g. fetch_page.

**`rename.to`**
- type: text; optional, default empty
- description: What the symbol becomes. Must be a legal identifier — the rename rewrites text, and a `to`
  that is not a name would produce a tree that no longer parses while reporting success. e.g.
  fetch_document.

#### `replan`

Where this contract came from when it was proposed in place of one whose ladder was spent: the id it
replaces and the re-plan round. Written by the batch that re-planned it, never by hand. Not
worker-facing.

**`replan.replaces`**
- type: text; optional, default empty
- description: The id of the contract this one was proposed in place of, when a batch handed that
  contract back to the orchestrator because its ladder was spent (`max_replans`). e.g. code-1f2e3d4c5b.

**`replan.round`**
- type: number (min 0); optional, default `0`
- description: Which re-plan this contract came from: 1 for one proposed in place of a contract nobody
  re-planned, one more than the contract it replaces otherwise. A batch re-plans a spent contract only
  while this is below `max_replans`, so the bound is read from the contract.

### Deterministic operations

Not task types: `task_type: code` with `operation:` `format`, `import_sort`, `lint_fix`, `rename_symbol`
has a tool make the change, never a model.

### Minimal examples

`references/examples.md` carries one `code` contract and one per
operation, each loaded through the contract validator by the test suite, so
copying one is copying a shape that is known to validate.

## Step 2 — validate before spending anything

```
mcgyvr contract CONTRACT.yaml
```

Prints what the contract resolves to, or names the key that is wrong. Fix
the contract; never guess a field. A `code` contract states no reply
cap: every request is sent the most its unit can give.

## Step 3 — vet and run the set

```
mcgyvr direct FILE... | DIR [--repo PATH] [flags]
```

A directory is read for its `*.json`, `*.yaml` and `*.yml` files. Each
contract is vetted as a proposal is: its target is a file the index holds,
each dependency's signature is in the index or in a contract of the set that
creates it, what the worker is shown fits its ceiling, and no other contract
states the same work; a file that does not load, two files giving one id,
and a contract waiting on a refused one are refused too. Every refusal is
printed on stderr as

```
  refused: <file>: <reason>
    change: <what_to_change>
```

The rest of the set runs. Change each refused file as its directive says
and run those files again, with what waits on them; not the whole set,
whose accepted changes are already in the tree. When no contract passes,
nothing runs and the exit is 3. `--output DIR` vets only: what passed is
written to `DIR/<id>.json` and nothing runs.

Every run works on the repository as committed at HEAD: uncommitted edits
and untracked files, including a test you just wrote, are not in the
sandbox. A batch refuses unless it can say who typed it: Claude Code and Pi
sessions are detected from the environment, otherwise pass `--session ID`.

### Flags that matter

- `--jobs N` — run up to N ready contracts at once, each settled as it ends and the next started as soon
  as it is ready (default: `auto` under use case mcgyvr-code, else 1, one at a time). N is capped at the
  fleet's total slots, the most dispatches its units take at once; `auto` or 0 is that cap. Two contracts
  whose scopes can write one file never run at once unless the policy says `same_file: parallel`, and a
  run's output is written whole when it ends. Runs beside each other share the fleet's slots, so one may
  wait for a rung, or pass a busy one by, as two runs typed in two terminals would.
- `--commit`, `--no-commit` — commit each accepted change, or not (--no-commit), whatever
  `delivery.commit` says.
- `--branch NAME` — commit each accepted change onto branch NAME; implies --commit.
- `--session ID` — the session the runs are filed under, resolved before any work (default: the session
  that typed this command, and a refusal, exit 2, when there is none); not needed with --output, which
  runs nothing.
- `--record DIR` — also journal each run under DIR, as a complete second copy.
- `--output DIR` — stop once the contracts are planned: write each one that passed vetting to
  DIR/<id>.json and run none of them, so `mcgyvr direct DIR` can run them later. Without it a prompt's
  contracts are printed on stdout and run from a temporary directory, and `direct` runs its files where
  they are.
- `--result PATH` — where *you* read the result file, when the set is one contract (`direct` with one
  file); mcgyvr keeps its own copy under the journal directory either way. Refused for more than one
  contract, and for a prompt, whose contracts are not known before it is planned.
- `--notes-from RESULT` — start a contract's climb with the failure notes of an earlier run of it: RESULT
  is that run's result file, and seeds the contract in the set whose id it names; give it once per
  contract. Its records are checked (same contract, the notes schema, repo-relative paths) and shown to
  the first attempt under a banner naming the earlier run, under `retry_notes: climb`; the result's
  `seeded` says what was read and handed. For a rerun on another ladder or machine. Refused for a prompt,
  whose contracts are proposed new and whose re-plans carry their own notes.

`mcgyvr direct -h` lists every flag. `--budget` is refused here: there is
no prompt to read.

### How it ended

- 0 — the contracts were planned (and, unless `--output`, every one that ran
  ended well).
- 1 — a failure: the config, the proposer or its reply, the repository, a
  run that did not land its change, or a crash; stderr says which.
- 2 — usage: a flag that cannot be honoured or has no meaning on this side, a
  contract path that is not there, or no session to file the runs under.
- 3 — refused: no proposer is configured, no contract came of the prompt or
  passed vetting, or a contract was held and never sent (`blocked`).

`--help` prints the same table.

## Step 4 — read the result files

Nothing on stdout points at a result. For a set of one contract, name where
you read it with `--result PATH`; for more, pass `--record DIR` and read
`DIR/results/<id>-<stamp>.json`. Either way mcgyvr keeps its own copy under
the config's `journal.dir`, in `results/`. The file's keys:

- `outcome` — one word, and what it leaves to do next:
  - `accepted` — the work landed; nothing to replan.
  - `rejected` — the deterministic gate refused the change; the
    findings name the check a different contract has to answer.
  - `delivery_refused` — judged acceptable, but the write to the tree
    was refused; `detail` says what was in the way. Clear it, rerun.
  - `nothing_to_change` — a tool found nothing to do; exit 0.
  - `ladder_spent` — everything this machine offers was tried and none
    produced an acceptable change. Raising a number changes what it
    costs to fail, not whether it fails. In a batch planned from a
    prompt (`mcgyvr "<prompt>"`) the contract goes back to the proposer
    with its failure notes and what comes back runs in its place, up to
    `max_replans` (default 1); `replanned` says what became of it. Under
    `mcgyvr direct` no proposer is asked and nothing re-plans it: you
    do, from the findings (Step 5).
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
  - `blocked` — held by the dependency tree (`dependents: hold`): a
    contract it waits on did not land, or landed without a symbol it
    needs, so it was never sent and no attempt was spent; exit 3.
    `blocked_by` says who and what. Rerun once that one lands.
  - `error` — an exception before any verdict was reached: the failure
    is in the machinery, not the work. `detail` names the cause.
- `attempts[]` — every try: `rung`, `attempt`, `verdict` (`passed`,
  `failed`, `declined`, `error`), `detail`, `findings` (the gate's lines
  behind a failure), `notes` (the record those lines are rendered from;
  below), `attempt_id`, `draw`, `draws`, `rows`, `relief`,
  `model`, `address`. `draws` is the
  breadth the attempt asked for (`breadth.draws`), whatever the verdict;
  `rows` is how many of those draws left a journal row, which is `draws`
  unless the attempt raised part-way and `0` for a try that declined or
  raised before dispatching. `draw` is the draw the entry is about, and is
  `null` — with `attempt_id` `null` beside it — on an `error` no single
  dispatch caused: `rows: 0` means it raised before dispatching at all,
  and anything more means it raised past draw `rows - 1`. `relief` is
  `true` for a rung lent through a hub — recorded like any try, but
  charged against the budget only when it passes — and `model`/`address`
  name the unit that served it, so a relief try shows which borrowed
  machine answered.
- `assurance` — what an `accepted` result rests on, and `detail` says it
  in a sentence: `deterministic` (a tool's change, on the gate),
  `verified` (a reviewer agreed), `unverified` (no reviewer could be
  asked; `detail` says why) or `unchecked` (a reply no check judges:
  no checks, no review). A reply is never reviewed.
- `findings` — why a change was refused, one line per reason: the
  deterministic gate's findings for a contract that dispatched nothing,
  or what refused the write on a `delivery_refused`.
- `delivery` — where the work went: left uncommitted in the tree (the
  default), the commit, or why it was refused (as `detail`).
  `committed`, `commit`, `branch`, `handoff` are the commit as fields.
- `target`, `contract`, `task_type`, `session` (the session the run is
  filed under; also written as `orchestrator`, its old key, for one
  release), `run`, `session_file`, `journal`, `exit_code`.
- `copy_errors` — a `--record DIR` copy that could not be written, and
  why. Empty on almost every run. mcgyvr's own record under `journal`
  is complete whatever this says; a copy is not a sink and its failure
  does not stop a run.
- `notes` — what the run said in passing (not failure notes): the
  uncommitted and untracked paths the sandbox of HEAD left out, what a
  tool printed as it worked (what a rename renamed), what the baseline
  left behind (now cleaned up), and a relief rung that duplicates a unit
  this install serves.
- `triage` — only under `triage: jev` or a contract's `start_rung`: the
  `rung` the climb started on and its `source` (`jev`, asked for this
  run, or `contract`); for `jev`, every rung's `probabilities`, its
  `confidence` and the `model` asked, or a `fallback` saying why the
  climb started on its first rung.
- `blocked_by` — only on a `blocked` result: the `reason`
  (`provider_failed`, `provider_not_landed`, `provider_landed_without`,
  `provider_blocked`, `cycle`, `unknown_dependency`, `unprovided`), the
  `providers` it waited on with the `outcome` and `result` each came
  to, the `needs` it had of them (`path`, `symbol`, and `creates`: to
  be created rather than changed) and the `chain` a hold came down
  through. A repository's live tree, which every batch on it joins
  while it has contracts in flight, is under `journal.dir` in
  `trees/<tree>.json`.
- `seeded` — only on a run started with `--notes-from RESULT`: `from`,
  the result read, `records`, the failure-notes records read from it,
  each with the `run` it was made in, and `handed`, how many the climb
  opened with (all under `retry_notes: climb`, else none).
- `replanned` — only on a `ladder_spent` result in a batch planned from a
  prompt with `max_replans` above 0: the `round`, the `max_replans` it was
  held to, the ids of the `contracts` proposed in its place (empty when it
  was not re-planned; each of those contract files carries `replan`: the
  id it `replaces` and its `round`) and a `detail` sentence, which
  `detail` repeats.

`attempts[].notes` is the failure-notes record of a failed try, `null` on
a try that left none. It is built from what the gate, the reviewer or the
reply parser observed — never from a model's account — so an optional
field is `null` where the check reported nothing for it. Its JSON Schema
is `references/failure-notes.schema.json`. The record:

**`schema`**
- type: `mcgyvr.failure_notes/1`
- description: The record's schema name and version.

**`rung`**
- type: text
- description: The rung the failed attempt ran on.

**`family`**
- type: text
- description: That rung's family: `deterministic`, `local` or `api`.

**`attempt`**
- type: number (min 1)
- description: The attempt's number on that rung, from 1.

**`checks`**
- type: list of text
- description: The checks that failed, in the order they ran.

**`notes`**
- type: list of blocks
- description: One entry per observation, in the order the checks reported them.

Each entry of its `notes`:

**`check`**
- type: text
- description: The check that raised it, as the gate names it: `lint`, `format`, `syntax`, `structure`,
  `typecheck`, `semantic`, `acceptance`, `scope`, `secret`, `structured-data`, `jev`, `verifier`,
  `reply`, ...

**`kind`**
- type: one of `finding`, `inconclusive`, `refusal`, `unreadable`
- description: `finding`: the check rejected the change. `inconclusive`: the rung ran and could not
  decide. `refusal`: a reviewer refused a change the gate passed. `unreadable`: the reply could not be
  read, so nothing was gated.

**`message`**
- type: text
- description: The check's own sentence. A path in the repository is repo-relative; any other absolute
  path, and the userinfo of any URL, is replaced by `<redacted>`.

**`path`**
- type: text or null
- description: The repo-relative file the note is about; null when the check keyed it by something that
  is not a file, such as an acceptance command, or named a file outside the repository.

**`line`**
- type: number or null
- description: The line in `path` the check placed it on; for a failing test, the line its definition
  starts on.

**`code`**
- type: text or null
- description: The check's own code for the kind of problem (`F401`, `E501`, mypy's `attr-defined`, ...).
  The acceptance rung's: `failed` for a failing test, or a failing command that named no test; `error`
  for a test whose fixture raised around it; `collection-error` for a test module that could not be
  collected — each prefixed `demonstration-` for a demonstrating command — and `timeout` and
  `tree-altering` for the command itself.

**`command`**
- type: text or null
- description: The command the check ran, when it ran one (acceptance, typecheck), shell-quoted, its
  paths treated as in `message`.

**`exit_code`**
- type: number or null
- description: That command's exit, or the exit of the tool an inconclusive rung ran; null when it was
  killed at the time limit or never ran.

**`test_id`**
- type: text or null
- description: The failing test's id (pytest's node id, `path::Class::test[param]`) when the check
  reports one as data: read from the JUnit XML report the acceptance rung asks pytest for, never out of a
  command's output.

**`symbol`**
- type: text or null
- description: The missing or undefined name, when the check reports it as data: the semantic rung's
  missing attribute, or the name in a test report's NameError, ImportError, ModuleNotFoundError or
  AttributeError, read only from the interpreter's fixed wording of that exception.

Every run is journaled under the config's `journal.dir` and nothing on
the command line moves it — that one directory is where every run can
be counted. Deterministic runs are there too, as a row naming
the program that did the work with `tier: deterministic` and no prompt
or reply beside it. `--record DIR` adds a complete second copy for your
own use. `--notes-from RESULT` starts a contract's climb with an earlier
run's failure notes, under a banner naming that run: for a rerun on another
ladder or machine, never instead of replanning.

## Step 5 — replan from the findings, never retry the same contract

A failed attempt already had its retries inside the run, and under
`mcgyvr direct` a spent ladder is not handed to a proposer: the next
contract is yours to write. When `outcome` is not `accepted`, read
`attempts[].findings`: each line is one reason the gate refused.
`attempts[].notes` is the same evidence as a record, one per failed
attempt in climb order: the check, the file and line, the tool's code, and
the command and its exit where the check ran one. Write a *different*
contract — narrower target, an acceptance command that states the
requirement, a stop condition for what was ambiguous — and go back to
Step 2. Running the same contract again spends more on the same answer.

`nothing_to_run` and `declined_throughout` are the exception: neither is
fixable by writing a different contract, because both say this machine
offered nothing that would do the work. Rewriting only relocates the same
answer. Report it to whoever owns the machine; the remedy is in
`skills/mcgyvr/SETUP.md`.

When `outcome` is `accepted`, the change is in `target` (a rename's: in
each file `delivery` names), uncommitted. Review it there and commit it
yourself. To have mcgyvr commit instead, run with `--commit` or
`--branch NAME` on a tree where those files are clean: mcgyvr refuses to
overwrite an edited or uncommitted file, so restore it first
(`git checkout -- <target>`) rather than rerunning on top of the last run.
