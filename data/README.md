# Shipped data

Three files ship as data rather than as code:
`capability-table.json` (estimates, by card class, of what a model costs to
serve, below), `task-catalog.json` (the vocabulary of what mcgyvr can be
asked to do, after it) and `numbers.json` (estimates mcgyvr sizes and judges
a machine with, and what many other such numbers in its code are, at the end
of this file).

## Capability data

`capability-table.json` holds estimates of what a model costs to serve.
`mcgyvr capabilities` lists them, and `mcgyvr emit` sizes a unit from the row
whose `id` equals the unit's model, unless a unit in fleet.yaml declares that
model, for example under `launch` or as `room_mib`. `mcgyvr init` does not read
the table: it binds the models running servers list. The estimates exist so that
serving can be sized **without benchmarking the user's machine**, which would
turn an install into a benchmarking session.

## What its numbers are

Every figure in the table is an **estimate**. None is a reading of your
machine.

- **A card class.** Each speed figure names the card class it is
  given for (`card_class`), and each class is declared once in
  `card_classes` with an id, a label and the nominal memory of its cards.
- **One card per class.** One card was read for each class, so a class is a
  rough guide. Speed depends on the card, not only on its memory: two cards
  with the same memory can differ a lot.
- **Through another server program.** Each figure's `backend` says which
  server program it was taken through. Most were taken through one this
  product does not run, with a file of the same model, usually of the same
  quantisation type; a reading's `note` says when it was not. That file is
  not necessarily the one you will serve.
- **Ratios more than absolutes.** Read the speed figures as ratios between
  models (which is faster, and by roughly how much) rather than as the speed
  your card will reach.
- **No provenance here.** Where and when the figures were taken is not
  recorded in the product.
- **No quality figure.** The table says what a model costs to serve, never
  how well it does the work, so it ranks no model above another.

Speed is generation rate in tokens per second; a figure's `note` says
when it is not a single request (one vLLM figure is an aggregate at 16
concurrent requests).

A row that carries `not_for_fit` is never listed as fitting a card
(`mcgyvr capabilities --vram`), and `mcgyvr capabilities` marks it; the key's
text says why, for example that the row's memory figure is not the model's
own footprint.

## Harness caveats

The table carries a `harness_caveats` block: ways a naive run of a reading
or a benchmark goes wrong. They are kept rather than deleted because
the failures are instructive and repeatable, and `mcgyvr capabilities` prints
each one's summary. One of them bears on the fit listing:

- **CAV-04** — a marginal fit on a card can run markedly slower rather than
  fail, which makes it look like a working binding.

## Revising the estimates

There is no regeneration script: the file is edited by hand when the project
revises its estimates. No mcgyvr command writes it. When taking
new figures, use an OpenAI-compatible endpoint (llama-server or vLLM) rather
than a backend-native generate API, and pin the quantisation explicitly —
CAV-01 and CAV-02 are both consequences of not doing so.


# The decomposition catalog — validation

`task-catalog.json` is the vocabulary of what mcgyvr can be asked to do (#15).
Each entry states what accepting it promises (`guarantee`), which family of the
ladder it may start on (`starts_on`), and what evidence a contract of that type
must carry (`required_evidence`).

It is data, not code, for a reason with teeth: adding a task type must be an
edit to this file and nothing else. `tests/test_catalog.py` proves that by
inventing a type (`sql_migration`) in a temporary file and driving it through
contract validation — a test that only passes while the code is genuinely
generic over the vocabulary.

## Why a family, not a rung

An entry says it starts on `deterministic`, `local` or `api` rather than naming
a rung. Rung names are chosen by whoever wrote the config, so a catalog naming
them would only be valid on the machine it was written for. A family resolves
against any ladder — a rung is `api` exactly when its unit declares an
`api_key_env` — and it is a *floor*: a dearer rung satisfies a cheaper family,
never the reverse.

The start is the *type's* floor only; escalation climbs from it (#24), and
that is not decided here.

## How the inherited vocabulary was validated

The starting list came from local-ai's triage map and was inherited, not
validated. The evidence available to judge it was coding-benchmark scores,
and their limits decide most of the answers: such a benchmark scores short,
self-contained function synthesis against a stated signature, and says nothing
about multi-hunk edits or about behaviour on a repository the model can see.
The product ships no such score.

So `function_implementation` is the one entry such scores bear on directly
— it is that shape exactly — and `docstring` is warranted by measurement only
weakly, leaning on `no_semantic_change`, a structural comparison the gate makes
without running anything. Every other entry is carried on a *structural*
argument, recorded per entry in its `warrant` field: the evidence is a tool's
output (`format`, `import_sort`, `lint_fix`), the index's own resolution
(`rename_symbol`), a checker's verdict (`type_annotation`), or a scope boundary
that removes the failure mode (`test_scaffold` cannot make a test pass by
editing what it tests).

`bug_fix` is the honest weak spot, and its `warrant` says so: nothing measured
covers diagnosis. What makes a cheap attempt safe to make anyway is
`failing_test_first` — with a demonstration required up front, a worker that did
not understand the defect produces a change that visibly fails rather than a
plausible one that lands.

## What was removed, and why

Removals live in the `excluded` block rather than being deleted, for the same
reason the capability table keeps its harness caveats: the next person to
reach for `multi_file_refactor` should find out why it is absent instead of
rediscovering it. Both the loader and `mcgyvr catalog <name>` surface the reason
rather than reporting "unknown type".

They fall into three groups:

- **Structurally unservable.** `multi_file_refactor` — the worker output
  protocol is one file's complete content in one fenced block (#25), so no model
  rung can emit a coordinated multi-file change at all. `rename_symbol` is the
  one multi-file operation the catalog carries, and it is deterministic
  precisely because the index resolves the references instead of a model
  guessing them.
- **No acceptance evidence exists.** `interface_design` has no command that can
  fail, so the gate cannot accept it and a model verifier would be the only
  judge — spending expensive tokens to decide whether expensive tokens were well
  spent. `comment_addition` has nothing the gate can distinguish from no change
  at all. `config_edit` has no language adapter (the gate's adapters are
  Python and JavaScript/TypeScript only), so acceptance would rest on the file
  still parsing.
- **Not a distinct guarantee.** `algorithm_implementation` differs from
  `function_implementation` only in how hard the prompt is.
  `simple_bug_fix`/`complex_bug_fix` encode difficulty in the type name, and
  difficulty is already what escalation (#24) climbs over — a second copy in
  the vocabulary is a copy that can disagree with the first.
  `string_literal_edit` is an exact edit at a known location — a tool's job,
  not a kind of work to route.


# The numbers that size and judge a machine

The `numbers` block of `numbers.json` holds numbers mcgyvr needs and
cannot read off the machine or the model: how far a healthy unit's warm decode and prefill speed may fall
from one start to the next (per tolerance class), and how much host memory a
llama.cpp server holds beyond the experts it keeps there. `mcgyvr.derived`
reads it; the build copies it into the package, so an installed mcgyvr finds
it without a checkout.

Every entry of that block is an estimate, and says so: what it estimates, what mcgyvr does
with it, its unit, its key, and a note on what the value is not. It is a
starting value shipped with mcgyvr, not a reading of your machine. Keys come
from closed spaces the code names (the tolerance classes, the engines a unit
may name), so no entry is keyed by a machine's name, and any machine has a key.

Your own value replaces an estimate. Write it in `~/.mcgyvr/numbers.yaml`,
under the number's name and then its key:

```yaml
prefill_class_pct:
  vllm: 12
runtime_resident_gb:
  llama.cpp: 2.5
```

The file is YAML; write each value as a plain decimal number, such as `12` or
`2.5`.

A setting for a number or key mcgyvr does not know, or a value that is not a
finite number inside its unit's bounds (a percent above 0 and below 100, GiB 0
or more), is refused by name, even when another number was asked. A number
of that block that neither file states is refused by name too: none of them
falls back to a default in code.

## What many other numbers are

Many numbers mcgyvr sizes, judges, refuses, waits or picks with are still
written in its code. The `constants` block says what many of them are, each
under where it lives (the file, then the name, the class and attribute, or the
function and its parameter):

- a **fact**: true on any machine, and it names what makes it so from a short
  closed list (a definition or arithmetic, such as how many bytes make a GiB;
  the specification of a format, protocol or tool, such as the port an engine
  listens on when told nothing else; where a count starts; or the layout of
  the package or its checkout);
- a **choice** of mcgyvr: the setting that changes it (a config key, a
  contract field or a command line flag), or, when there is none, a reason
  from a short closed list (a protocol or tool default; a code or version
  other programs or files read; the method a stored reading was made with; a
  rule over mcgyvr's own shipped data; what a caller that names none gets,
  where mcgyvr's own callers name one; how much of a text mcgyvr itself
  shows, carries or reads, and at what width, never a budget for a model's
  whole reply or whole input; a weight, threshold or cut of mcgyvr's own
  ranking of files and symbols; how often or how many times mcgyvr tries its
  own step again; or a
  duplicate of another entry, which it names);
- an **estimate**: a value another machine may prove wrong. Each one still in
  code names the number id planned for it in the `numbers` block, where it can
  be set in your `numbers.yaml` like the others, and the setting that changes
  it today where one exists. Until it moves, `numbers.yaml` cannot set it.

A test parses the files of mcgyvr's code and fails on a number `constants`
does not classify, on an entry that no longer matches the code, and on a file
of the package it has not been told about. Which files it judges, and why the
others are not judged, is kept beside that test and does not ship. It sees
numbers named at the top of a file, in a class, or as a parameter's default; a
number written inside a function where it is used is not seen, and the way to
bring it under the check is to name it. The kinds and reasons are listed in
`mcgyvr.derived`.
