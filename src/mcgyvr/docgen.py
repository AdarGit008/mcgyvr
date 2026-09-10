"""Render the config reference, the /mcgyvr skill and SETUP.md from their schemas.

``config.SCHEMA`` is declarative data — every key carries its kind, whether
it is required, its default and the prose explaining it. That makes the
reference a projection of the schema rather than a second description of it,
so a documented key and a validated key cannot drift apart. Hand-written
config docs drift the moment the schema moves; this file exists so that the
schema is the only description there is.

The reference is never kept (owner's ruling, 2026-09-05). Every run renders
it, checks it — the provenance marker is on it and every validated key is
named — and deletes it, so no copy sits in the checkout to be read in place
of the schema or to fall behind it. The skill, the examples beside it and
``SETUP.md`` are the documents that are written, because they are read from
disk; ``make docs-check`` refuses a committed one that differs from what its
schema renders.

Two constraints shape the rendering:

1. **Deterministic.** Same schema in, byte-identical document out. Nothing
   here reads the clock, the filesystem or the environment, and nothing
   iterates an unordered collection — the walk follows declaration order,
   which is the order a reader of the config file meets the keys. A
   generator that embeds a timestamp cannot be diffed against the skill it
   last wrote, which would cost exactly the drift check.
2. **No prose that lives only here.** Every description below comes from a
   ``Field``'s ``doc``. The fixed scaffolding is limited to structure and to
   explaining the value types, because those are properties of the loader,
   not of any one key.

The second document is the ``/mcgyvr`` skill (owner's ruling, 2026-09-03,
narrowed 2026-09-09, narrowed again 2026-09-09): the one explicitly-invoked
instruction an agent reads before it authors a contract — the packaged skill
ships ``disable-model-invocation: true``, so a fresh install never offloads
work until someone asks for it — generated the same way from
``contract.SCHEMA`` so the fields an agent is told about are the fields the
validator accepts, and **setup is not part of it**. The skill points at one
minimal example per task type, rendered beside it into
``skills/mcgyvr/references/examples.md``; each is checked by loading it
through the contract loader, so an example that stops validating is a build
failure and not a lesson in the wrong shape. The scaffolding here — the steps
— is the workflow, which is a property of the product and of no one key.

The third document is ``skills/mcgyvr/SETUP.md``, what a machine's owner reads
to stand the ladder up: the first run, and every key the one config file
accepts, rendered from ``config.SCHEMA``. It is written and kept, the way the
skill is, because it is read from disk rather than through the schema — and it
lives beside the skill it is not part of, so ``install.sh`` never copies it
into a harness.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from . import contract as contract_schema
from .config import CONFIG_FILENAME, SCHEMA, Field

# Matches CTX-08's marker pattern. It is an HTML comment so it renders as
# nothing, but survives in the source a would-be editor is looking at.
MARKER = (
    "<!-- Code generated from src/mcgyvr/config.py by `make docs`. DO NOT EDIT. -->"
)

# src/mcgyvr/docgen.py -> repo root. This is a repository maintenance tool run
# from a checkout, never from an installed wheel, so deriving the path is
# honest here in a way it would not be in shipped code.
REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = Path("skills/mcgyvr/SKILL.md")
SETUP_PATH = Path("skills/mcgyvr/SETUP.md")
EXAMPLES_PATH = Path("skills/mcgyvr/references/examples.md")
SKILL_MARKER = (
    "<!-- Code generated from src/mcgyvr/contract.py and src/mcgyvr/docgen.py by "
    "`make docs`. DO NOT EDIT. -->"
)

# What each kind accepts, as the loader enforces it. These describe the
# validator's behaviour, so they belong to the renderer rather than to any
# single Field.
_TYPES: tuple[tuple[str, str], ...] = (
    (
        "number",
        "A whole number. `true` is not a number, even though Python says it is.",
    ),
    (
        "text",
        "A non-empty string. An empty value is rejected rather than treated as "
        "unset — remove the key instead.",
    ),
    (
        "URL",
        "Text that carries a scheme: it must start with `http://` or `https://`.",
    ),
    ("boolean", "`true` or `false`, unquoted."),
    (
        "decimal number",
        "A number that may carry a fraction. Sizes written this way are in "
        "**GiB** — powers of 1024 — which is what the rest of mcgyvr measures "
        "in; a file a tool reports as 13.2 GB is 12.3 here.",
    ),
    (
        "one of ...",
        "Text drawn from a fixed set. Anything else is rejected, with the valid "
        "values named.",
    ),
    (
        "env var name",
        "The **name** of an environment variable (e.g. `ANTHROPIC_API_KEY`), "
        "never the value. Credentials are never written into this file; the "
        "orchestrator resolves the name at point of use and a task sandbox "
        "never sees the result.",
    ),
    ("list of text", "A YAML list of non-empty strings."),
    (
        "block",
        "A nested mapping with a fixed set of keys, documented in its own section.",
    ),
    (
        "block map",
        "A mapping whose keys you choose; every entry takes the same fixed set "
        "of keys.",
    ),
    (
        "list of blocks",
        "An ordered YAML list; every entry takes the same fixed set of keys.",
    ),
)

_KIND_LABELS: dict[str, str] = {
    "int": "number",
    "float": "decimal number",
    "str": "text",
    "url": "URL",
    "bool": "boolean",
    "env_name": "env var name",
    "str_list": "list of text",
    "block": "block",
    "block_map": "block map",
    "block_list": "list of blocks",
}


def _escape(text: str) -> str:
    """Make prose safe inside a markdown table cell."""
    return text.replace("|", "\\|")


def _type_label(field: Field) -> str:
    if field.kind == "enum":
        return "one of " + ", ".join(f"`{c}`" for c in field.choices)
    label = _KIND_LABELS[field.kind]
    # Both bounds, because a field that has a ceiling and shows only its floor
    # reads as unbounded above -- which for a share of something is the half
    # that matters.
    bounds = []
    if field.min_value is not None:
        bounds.append(f"min {field.min_value}")
    if field.max_value is not None:
        bounds.append(f"max {field.max_value}")
    if bounds:
        return f"{label} ({', '.join(bounds)})"
    return label


def _default_label(field: Field) -> str:
    """How a field reads when the config leaves it out.

    A required key has no default by construction. For the rest, absence is
    meaningful and is said so explicitly rather than shown as a blank cell:
    the loader distinguishes "unset" from "empty", and so must the reference.
    """
    if field.required:
        return "—"
    if field.kind in ("block", "block_map", "block_list"):
        return "—"
    if field.kind == "str_list":
        return "`[]`" if not field.default else f"`{list(field.default)}`"
    if field.default is None:
        return "unset"
    if field.kind == "bool":
        return f"`{str(field.default).lower()}`"
    return f"`{field.default}`"


def _describe(field: Field) -> str:
    """The field's own prose, plus its binding hint when it carries one."""
    text = field.doc
    if field.bind_hint:
        text = f"{text} To bind it: {field.bind_hint}."
    return _escape(text)


def _table(fields: Sequence[Field], prefix: str) -> list[str]:
    lines = [
        "| Key | Type | Required | Default | Description |",
        "| --- | --- | --- | --- | --- |",
    ]
    for field in fields:
        name = f"{prefix}{field.name}" if prefix else field.name
        required = "**yes**" if field.required else "no"
        lines.append(
            f"| `{name}` | {_type_label(field)} | {required} | "
            f"{_default_label(field)} | {_describe(field)} |"
        )
    lines.append("")
    return lines


def _section(field: Field, path: str, level: int, dotted: bool = False) -> list[str]:
    """Render one block-valued key, then any block-valued keys inside it.

    ``dotted`` names each key in the table by its full path rather than by its
    last segment. The reference leaves it off, because :func:`reference_problems`
    looks a leaf up under the heading of the block it belongs to and a dotted
    cell would never match. ``SETUP.md`` turns it on, because it is read start
    to finish by someone editing one file and `sandbox.mode` says which `mode`.
    """
    heading = "#" * level
    lines = [f"{heading} `{path}`", "", _escape(field.doc), ""]

    if field.kind == "block_map":
        lines += ["Each entry takes these keys:", ""]
    elif field.kind == "block_list":
        # Semicolon, not a full stop: the skill's own renderer opens a
        # `block_list` the same way, and one sentence shared between the two
        # documents is one sentence that can be updated in one of them.
        lines += ["An ordered list; each entry takes these keys:", ""]

    lines += _table(field.block, f"{path}." if dotted else "")

    for inner in field.block:
        if inner.block:
            lines += _section(inner, f"{path}.{inner.name}", level + 1, dotted)
    return lines


def render_reference() -> str:
    """The complete reference document, as text."""
    lines = [
        MARKER,
        "",
        "# Configuration reference",
        "",
        f"Every key `{CONFIG_FILENAME}` accepts.",
        "",
        "This page is generated from `SCHEMA` in `src/mcgyvr/config.py` — the same",
        "declaration the loader validates against. It is not a description of the",
        "config format kept alongside one; it is a projection of it, so a documented",
        "key and a validated key cannot disagree.",
        "",
        "Three properties hold across every key here, because the loader enforces",
        "them rather than documenting them and hoping:",
        "",
        "- **Unknown keys fail.** A typo'd key that is ignored is a config that",
        "  silently does something other than what it says.",
        "- **No silent defaults for things that must be bound.** A default ships only",
        "  when it is a real working value. Anything else is absent, and its absence",
        "  surfaces at the point of use naming the key and how to bind it.",
        "- **Credentials are never values.** Keys that would hold a secret take the",
        "  *name* of an environment variable. Writing a key in directly is rejected",
        "  by name, not with a generic error.",
        "",
        "## Value types",
        "",
        "| Type | Accepted |",
        "| --- | --- |",
    ]
    for name, rule in _TYPES:
        lines.append(f"| {name} | {_escape(rule)} |")
    lines += ["", "## Top-level keys", ""]
    lines += _table(SCHEMA, "")

    for field in SCHEMA:
        if field.block:
            lines += _section(field, field.name, 2)

    return "\n".join(lines).rstrip("\n") + "\n"


# --- SETUP.md ----------------------------------------------------------------

#: The three keys of the one config file `mcgyvr pool` reads back. They are
#: named here rather than described here: the bullet each one gets carries the
#: `Field`'s own `doc`, so the levers cannot say one thing in SETUP.md and
#: another in the schema the loader walks.
_LEVERS: tuple[str, ...] = ("sources", "ladder", "budgets")


def render_setup() -> str:
    """``SETUP.md``, as text: the first run, the levers, then every key.

    Unlike :func:`render_reference`, which is rendered, checked and deleted,
    this is a document that is written and kept: a machine's owner reads it
    from disk before there is a config to read anything else from. It is still
    a projection of :data:`SCHEMA` — the levers below are the schema's own
    prose, and the tables are the same walk the reference makes.
    """
    by_name = {field.name: field for field in SCHEMA}
    lines = [
        MARKER,
        "",
        "# Setting up mcgyvr",
        "",
        "First run, once per machine. Nothing here is read to author a contract;",
        f"this is how `{CONFIG_FILENAME}` comes to exist and what it can say.",
        "",
        "```",
        "mcgyvr init",
        "mcgyvr pool",
        "```",
        "",
        "`mcgyvr init` detects what is reachable and writes a config bound to it. It",
        "refuses to overwrite an existing config without `--force`, and prints what",
        "was decided and why, then what is *not* configured and what that costs.",
        "Backends on another machine come in with `--host` (repeatable).",
        "",
        "`mcgyvr pool` reads that config back: the usable rungs cheapest-first with",
        "their family, attempt budget and model; the escalation ceiling and where it",
        "came from; every skipped rung with the reason it was skipped; and the",
        "orchestrator and verifier models. `--probe` also asks each source whether it",
        "is answering — off by default, because it spends. Run it whenever a run",
        "picks a rung you did not expect.",
        "",
        "Three keys of that one config file are the levers, and `mcgyvr pool` is how",
        "you read all three:",
        "",
    ]
    for lever in _LEVERS:
        lines.append(f"- `{lever}` — {_escape(by_name[lever].doc)}")
    lines += [
        "",
        "`mcgyvr config` prints the resolved config; `mcgyvr detect` and",
        "`mcgyvr capabilities` say what a source is and what it can do.",
        "",
        "## Value types",
        "",
        "| Type | Accepted |",
        "| --- | --- |",
    ]
    for name, rule in _TYPES:
        lines.append(f"| {name} | {_escape(rule)} |")
    lines += ["", "## Top-level keys", ""]
    lines += _table(SCHEMA, "")

    for field in SCHEMA:
        if field.block:
            lines += _section(field, field.name, 2, dotted=True)

    return "\n".join(lines).rstrip("\n") + "\n"


# --- the /mcgyvr skill -------------------------------------------------------

_CONTRACT_KIND_LABELS: dict[str, str] = {
    "int": "number",
    "float": "decimal number",
    "str": "text",
    "str_list": "list of text",
    "glob_list": "list of globs",
    "block": "block",
    "block_list": "list of blocks",
}

#: One minimal valid contract per task type, in the catalog's order. Each is
#: loaded by ``tests/test_the_mcgyvr_skill_is_rendered_from_the_schema.py``;
#: an example that does not validate fails the suite.
EXAMPLES: dict[str, str] = {
    "format": """\
id: format-pkg
task_type: format
task: Reformat the module with the project's formatter.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
""",
    "import_sort": """\
id: sort-imports
task_type: import_sort
task: Order the module's imports with the project's import sorter.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
""",
    "lint_fix": """\
id: lint-pkg
task_type: lint_fix
task: Apply the linter's own autofixes to the module.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
""",
    "rename_symbol": """\
id: rename-fetch
task_type: rename_symbol
task: Rename fetch_page to fetch_document in the module.
target: src/pkg/messy.py
rename:
  from: fetch_page
  to: fetch_document
scope:
  allow: ["src/pkg/**"]
""",
    "docstring": """\
id: doc-fetch
task_type: docstring
task: Write the docstring for fetch_document, stating what it returns on a 404.
target: src/pkg/fetch.py
interface: "def fetch_document(url: str, *, timeout_s: float = 5.0) -> str"
stop_conditions:
  - The 404 behaviour cannot be read from the code.
limits:
  max_output_tokens: 512
scope:
  allow: ["src/pkg/fetch.py"]
""",
    "type_annotation": """\
id: annotate-fetch
task_type: type_annotation
task: Add type annotations to fetch_document and its helpers.
target: src/pkg/fetch.py
stop_conditions:
  - A helper's return type cannot be determined from its callers.
acceptance: ["mypy src/pkg/fetch.py"]
limits:
  max_output_tokens: 1024
scope:
  allow: ["src/pkg/fetch.py"]
""",
    "function_implementation": """\
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
limits:
  max_output_tokens: 1024
scope:
  allow: ["src/pkg/chunk.py"]
""",
    "test_scaffold": """\
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
limits:
  max_output_tokens: 1024
scope:
  allow: ["tests/test_chunk.py"]
""",
    "bug_fix": """\
id: fix-chunk-remainder
task_type: bug_fix
task: chunk drops the final short group when the length does not divide evenly; keep it.
target: src/pkg/chunk.py
interface: "def chunk(items: list[T], size: int) -> list[list[T]]"
stop_conditions:
  - The demonstrating test does not fail on the current code.
demonstration: ["pytest -q tests/test_chunk.py -k remainder"]
acceptance: ["pytest -q tests/test_chunk.py"]
limits:
  max_output_tokens: 1024
scope:
  allow: ["src/pkg/chunk.py"]
""",
}


def _contract_type_label(field: contract_schema.Field) -> str:
    if field.kind == "enum":
        choices = field.choices or (field.choices_from() if field.choices_from else ())
        return "one of " + ", ".join(f"`{c}`" for c in choices)
    label = _CONTRACT_KIND_LABELS[field.kind]
    # Both bounds, for the reason the config renderer states: a ceiling that
    # is not shown reads as no ceiling.
    bounds = []
    if field.min_value is not None:
        bounds.append(f"min {field.min_value}")
    if field.max_value is not None:
        bounds.append(f"max {field.max_value}")
    if bounds:
        return f"{label} ({', '.join(bounds)})"
    return label


def _contract_default_label(field: contract_schema.Field) -> str:
    if field.required:
        return "—"
    if field.kind in ("block", "block_list"):
        return "—"
    if field.kind in ("str_list", "glob_list"):
        return "`[]`" if not field.default else f"`{list(field.default)}`"
    if field.default is None:
        return "unset"
    if field.default == "":
        return "empty"
    return f"`{field.default}`"


def _contract_describe(field: contract_schema.Field) -> str:
    text = field.doc
    if field.hint:
        text = f"{text} {field.hint.rstrip('.')}."
    audience = "worker" if field.worker_facing else "orchestrator"
    return _escape(f"{text} ({audience}-facing)")


def _contract_table(fields: Sequence[contract_schema.Field], prefix: str) -> list[str]:
    lines = [
        "| Key | Type | Required | Default | Description |",
        "| --- | --- | --- | --- | --- |",
    ]
    for field in fields:
        name = f"{prefix}{field.name}"
        required = "**yes**" if field.required else "no"
        lines.append(
            f"| `{name}` | {_contract_type_label(field)} | {required} | "
            f"{_contract_default_label(field)} | {_contract_describe(field)} |"
        )
    lines.append("")
    return lines


def _contract_section(field: contract_schema.Field, path: str) -> list[str]:
    lines = [f"#### `{path}`", "", _escape(field.doc), ""]
    if field.kind == "block_list":
        lines += ["An ordered list. Each entry takes these keys:", ""]
    lines += _contract_table(field.block, f"{path}.")
    for inner in field.block:
        if inner.block:
            lines += _contract_section(inner, f"{path}.{inner.name}")
    return lines


def render_skill() -> str:
    """The ``/mcgyvr`` skill, as text: four steps, the schema, one example per type."""
    lines = [
        "---",
        "name: mcgyvr",
        'description: "Use whenever a scoped piece of coding work can be '
        "offloaded to mcgyvr: author a task contract, validate it, run it, read "
        "the result file, replan from the findings. Invoke it explicitly when "
        "you are about to delegate; the schema below is the only contract "
        'vocabulary."',
        "disable-model-invocation: true",
        "---",
        "",
        SKILL_MARKER,
        "",
        "# /mcgyvr",
        "",
        "Offload one scoped piece of coding work to mcgyvr. You author a *contract*",
        "(one target, one task, one way to judge it), mcgyvr gates every answer",
        "deterministically, and leaves the accepted file in the working tree. It",
        "never commits unless told to, and it never writes anything else into the",
        "repository.",
        "",
        "## Step 1 — author a contract",
        "",
        "One YAML file. Every key below is the contract schema in",
        "`src/mcgyvr/contract.py`, rendered by `make docs`; unknown keys are refused,",
        "and every rejection names the key and what a valid value looks like.",
        "Pick the `task_type` first: it decides what evidence the contract must",
        "carry. `mcgyvr catalog <type>` prints the type's guarantee.",
        "",
        "### Keys",
        "",
    ]
    lines += _contract_table(contract_schema.SCHEMA, "")
    for field in contract_schema.SCHEMA:
        if field.block:
            lines += _contract_section(field, field.name)
    lines += [
        "### One minimal example per task type",
        "",
        f"`{EXAMPLES_PATH}` carries one per type,",
        "each loaded through the contract validator by the test suite, so copying",
        "one is copying a shape that is known to validate. One file away, and it",
        "costs nothing until it is opened.",
        "",
    ]
    lines += [
        "## Step 2 — validate before spending anything",
        "",
        "```",
        "mcgyvr contract CONTRACT.yaml",
        "```",
        "",
        "Prints what the contract resolves to, or names the key that is wrong. Fix",
        "the contract; never guess a field. A contract a model executes must",
        "declare `limits.max_output_tokens`, or this and `run` refuse it (exit 2)",
        "and print the figure to start from: a reply cut at a cap nobody chose",
        "is spent silently.",
        "",
        "## Step 3 — run it, then read the result file",
        "",
        "```",
        "mcgyvr run CONTRACT.yaml --repo DIR [--config PATH] "
        "[--sandbox tempdir] [--commit]",
        "```",
        "",
        "The run refuses unless it can say who typed it: Claude Code and Pi sessions",
        "are detected from the environment, otherwise pass `--orchestrator ID`.",
        "The last stdout line is `result: <path>`:",
        "everything above it is scrollback, and everything the run came to is in",
        "that file, under mcgyvr's own journal directory — never in the repository.",
        "Read the file, not the scrollback. No `result:` line with exit 1 or 2 means",
        "the run never started (the contract did not load, the repo is not git, or",
        "no session could be named) or the result file could not be written; either",
        "way the reason is on stderr, and in the second case that line also says",
        "what the run came to. The file's keys:",
        "",
        "- `outcome` — one word, and what it leaves to do next:",
        "  - `accepted` — the work landed; nothing to replan.",
        "  - `rejected` — the deterministic gate refused the change; the",
        "    findings name the check a different contract has to answer.",
        "  - `delivery_refused` — judged acceptable, but the write to the tree",
        "    was refused; `detail` says what was in the way. Clear it, rerun.",
        "  - `ladder_spent` — everything this machine offers was tried and none",
        "    produced an acceptable change. Narrow the contract: raising a",
        "    number changes what it costs to fail, not whether it fails.",
        "  - `escalation_ceiling` — stopped at a ceiling on how far the work may",
        "    be moved up, with dearer tries never entered; that says it was not",
        "    allowed to try, not that it cannot. Rerun where those moves are",
        "    paid for.",
        "  - `attempt_ceiling` — stopped at what one task may spend, which",
        "    bounds the bill and not the ability. Rerun against a budget that",
        "    can pay for it.",
        "  - `nothing_to_run` — nothing on this machine offered to do this work",
        "    at all, so the machine stopped it and not the work. A different",
        "    contract cannot fix it: `skills/mcgyvr/SETUP.md` can.",
        "  - `declined_throughout` — everything offered stepped aside without",
        "    spending an attempt, so nothing claims a contract of this shape.",
        "    A different contract cannot fix this either; that same file can.",
        "  - `error` — an exception before any verdict was reached: the failure",
        "    is in the machinery, not the work. `detail` names the cause.",
        "- `attempts[]` — every try: `rung`, `attempt`, `verdict` (`passed`,",
        "  `failed`, `declined`, `error`), `detail`, `findings` (the gate's lines",
        "  behind a failure), `attempt_id`, `draw`, `draws`, `rows`. `draws` is the",
        "  breadth the attempt asked for (`breadth.draws`), whatever the verdict;",
        "  `rows` is how many of those draws left a journal row, which is `draws`",
        "  unless the attempt raised part-way and `0` for a try that declined or",
        "  raised before dispatching. `draw` is the draw the entry is about, and is",
        "  `null` — with `attempt_id` `null` beside it — on an `error` no single",
        "  dispatch caused: `rows: 0` means it raised before dispatching at all,",
        "  and anything more means it raised past draw `rows - 1`.",
        "- `findings` — the deterministic gate's findings for a contract that",
        "  dispatched nothing.",
        "- `committed`, `commit`, `branch`, `handoff` — where the work went. Without",
        "  `--commit` the accepted file is left in the working tree, uncommitted.",
        "- `target`, `contract`, `task_type`, `orchestrator`, `run`, `session_file`,",
        "  `journal`, `exit_code`.",
        "- `copy_errors` — a `--record DIR` copy that could not be written, and",
        "  why. Empty on almost every run. mcgyvr's own record under `journal`",
        "  is complete whatever this says; a copy is not a sink and its failure",
        "  does not stop a run.",
        "",
        "Every run is journaled under the config's `journal.dir` and nothing on",
        "the command line moves it — that one directory is where every run there",
        "has ever been can be counted, which is the only thing that makes the",
        "record worth keeping. Deterministic runs are there too, as a row naming",
        "the program that did the work with `tier: deterministic` and no prompt",
        "or reply beside it. `--record DIR` adds a complete second copy for your",
        "own use; `--result PATH` says where you read the result file.",
        "",
        "Exit codes: 0 accepted, 1 not accepted or error, 2 usage (including no",
        "session to file the run under).",
        "",
        "## Step 4 — replan from the findings, never retry the same contract",
        "",
        "A failed attempt already had its retries inside the run. When `outcome` is",
        "not `accepted`, read `attempts[].findings`: each line is one reason the gate",
        "refused. Write a *different* contract — narrower target, an acceptance",
        "command that states the requirement, a stop condition for what was",
        "ambiguous — and go back to step 2. Running the same contract again spends",
        "more on the same answer.",
        "",
        "`nothing_to_run` and `declined_throughout` are the exception: neither is",
        "fixable by writing a different contract, because both say this machine",
        "offered nothing that would do the work. Rewriting only relocates the same",
        "answer. Report it to whoever owns the machine; the remedy is in",
        "`skills/mcgyvr/SETUP.md`.",
        "",
        "When `outcome` is `accepted`, the change is in `target`, uncommitted.",
        "Review it there and commit it yourself. To have mcgyvr commit instead, run",
        "with `--commit` on a tree where `target` is clean: mcgyvr refuses to",
        "overwrite an edited or uncommitted target, so restore it first",
        "(`git checkout -- <target>`) rather than rerunning on top of the last run.",
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def render_examples() -> str:
    """The examples file, as text: one minimal contract per task type.

    A document that is written and kept, like the skill and ``SETUP.md``, and
    checked the same way: it is a projection of :data:`EXAMPLES`, which
    ``tests/test_the_mcgyvr_skill_is_rendered_from_the_schema.py`` loads
    through ``contract.load``, so an example that stops validating is still a
    build failure. It is one file away from the skill because an agent's
    context is the scarce thing and a file costs nothing until it is opened.
    """
    lines = [
        SKILL_MARKER,
        "",
        "# One minimal contract per task type",
        "",
        "Each loads through the contract validator; they are checked by the test",
        "suite, so copying one is copying a shape that is known to validate. The",
        "keys are documented in `SKILL.md`.",
        "",
    ]
    for task_type, text in EXAMPLES.items():
        lines += [f"## `{task_type}`", "", "```yaml", text.rstrip("\n"), "```", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def _keys(fields: Sequence[Field], prefix: str = "") -> list[str]:
    """Every key in the schema, at every depth, as dotted paths."""
    out: list[str] = []
    for field in fields:
        path = f"{prefix}.{field.name}" if prefix else field.name
        out.append(path)
        out.extend(_keys(field.block, path))
    return out


#: A section heading in the rendered reference: a level, and the dotted key it
#: documents. `## `sources`` opens the block `sources`; `### `ladder.tiers``
#: opens the block inside it. The two headings with no key — the document title
#: and `## Value types` — do not match, which is correct: they document nothing
#: the loader validates.
_HEADING = re.compile(r"^#+ +`([A-Za-z0-9_.]+)`\s*$", re.MULTILINE)

#: Where the top-level keys are tabled. It is the one block whose keys do not
#: live under a heading named for their parent, because they have no parent.
_TOP_LEVEL = "## Top-level keys"


def _sections(text: str) -> dict[str, str]:
    """The document split by heading: dotted key (or ``_TOP_LEVEL``) to body.

    A body runs to the next heading of ANY level, so a block's own table is not
    conflated with the tables of the blocks nested inside it. That is the whole
    of what makes the check below a whole-key check: `mode` found under
    `sandbox` is found in `sandbox`'s body and nowhere near `delivery`'s.
    """
    starts: list[tuple[int, int, str]] = []
    for match in _HEADING.finditer(text):
        starts.append((match.start(), match.end(), match.group(1)))
    for match in re.finditer(rf"^{re.escape(_TOP_LEVEL)}\s*$", text, re.MULTILINE):
        starts.append((match.start(), match.end(), _TOP_LEVEL))
    # Every heading, keyed or not, bounds a body — a keyed section must not run
    # on through `## Value types` and inherit whatever is tabled there.
    bounds = sorted(
        {match.start() for match in re.finditer(r"^#+ .*$", text, re.MULTILINE)}
    )
    out: dict[str, str] = {}
    for start, body_start, name in sorted(starts):
        after = [b for b in bounds if b > start]
        out[name] = text[body_start : after[0]] if after else text[body_start:]
    return out


def reference_problems(text: str) -> list[str]:
    """What is wrong with ``text`` as a reference for :data:`SCHEMA`.

    Nothing, when it is sound. Every key is checked **where it belongs**: a
    top-level key in the top-level table, and a nested key in the body of the
    section named for its parent block. The previous check compared only the
    last dotted segment against the whole document, and `mode`, `source`,
    `model`, `enabled`, `image`, `dir` and `attempts` all recur across blocks —
    so a whole block could stop rendering and `make docs-check` would pass on a
    namesake elsewhere. A check that cannot fail is worse than no check.
    """
    problems: list[str] = []
    if not text.startswith(MARKER):
        problems.append("the DO NOT EDIT marker is not the first line")
    sections = _sections(text)
    absent: set[str] = set()
    for path in _keys(SCHEMA):
        parent, _, leaf = path.rpartition(".")
        where = parent or _TOP_LEVEL
        body = sections.get(where)
        if body is None and parent:
            # Reported once for the block, not once per key inside it: a
            # missing section is one fault, and naming its twelve leaves would
            # bury it. Only for a NAMED block — a document with no top-level
            # table at all has no block to name, and every key it dropped is
            # reported by name below.
            if parent not in absent:
                absent.add(parent)
                problems.append(f"the `{parent}` block is not documented at all")
            continue
        if body is None:
            body = ""
        if f"`{leaf}`" not in body:
            problems.append(f"`{path}` is validated and not named")
    return problems


def check_reference(target: Path) -> list[str]:
    """Render the reference to ``target``, check it, and delete it.

    Returns what is wrong with it — nothing, when it is sound. The file is
    gone when this returns whatever the verdict: the schema is the reference,
    and a rendered copy that outlives its check becomes a second description
    of the config that then has to be kept current (owner ruling,
    2026-09-05). The check is the one a reader would make — the provenance
    marker is on it, and every key the loader validates is named under the
    block it belongs to.
    """
    rendered = render_reference()
    try:
        target.write_text(rendered, encoding="utf-8")
        text = target.read_text(encoding="utf-8")
    finally:
        target.unlink(missing_ok=True)
    return reference_problems(text)


def _write_or_check(target: Path, rendered: str, schema: str, check: bool) -> int:
    """Write ``rendered`` to ``target``, or report a committed copy that drifted.

    Returns 1 when ``check`` is on and the committed document is not what its
    schema renders, 0 otherwise. Both kept documents — the skill and
    ``SETUP.md`` — go through here, so a stale one fails ``make docs-check``
    whichever of the two schemas moved.
    """
    if not check:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        print(f"wrote {target}")
        return 0
    current = target.read_text(encoding="utf-8") if target.exists() else ""
    if current == rendered:
        return 0
    print(
        f"{target}: out of date with SCHEMA in {schema}.\n"
        f"The document is generated from it — a schema change needs it "
        f"regenerated in the same commit.\n"
        f"Run: make docs",
        file=sys.stderr,
    )
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.docgen",
        description=(
            "Render the configuration reference from the config schema, check it "
            "and delete it; write the /mcgyvr skill, its examples and SETUP.md, or "
            "check the committed ones."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if a committed document is not what the schemas render",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "where the reference is rendered for its check; deleted afterwards "
            "(default: a file under the temporary directory)"
        ),
    )
    parser.add_argument(
        "--skill-output",
        default=str(REPO_ROOT / SKILL_PATH),
        help="where to write the /mcgyvr skill (default: the checkout's copy)",
    )
    parser.add_argument(
        "--setup-output",
        default=str(REPO_ROOT / SETUP_PATH),
        help="where to write SETUP.md (default: the checkout's copy)",
    )
    parser.add_argument(
        "--examples-output",
        default=str(REPO_ROOT / EXAMPLES_PATH),
        help="where to write the examples file (default: the checkout's copy)",
    )
    args = parser.parse_args(argv)

    reference = (
        Path(args.output)
        if args.output is not None
        else Path(tempfile.gettempdir()) / f"mcgyvr-config-reference-{os.getpid()}.md"
    )
    problems = check_reference(reference)
    if problems:
        print(
            f"{reference}: the reference rendered from SCHEMA in "
            "src/mcgyvr/config.py fails its check, and was deleted:",
            *(f"  {problem}" for problem in problems),
            sep="\n",
            file=sys.stderr,
        )
    else:
        print(f"config reference: rendered to {reference}, checked, deleted")

    stale = _write_or_check(
        Path(args.skill_output), render_skill(), "src/mcgyvr/contract.py", args.check
    )
    stale += _write_or_check(
        Path(args.setup_output), render_setup(), "src/mcgyvr/config.py", args.check
    )
    stale += _write_or_check(
        Path(args.examples_output),
        render_examples(),
        "src/mcgyvr/contract.py",
        args.check,
    )
    return 1 if problems or stale else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
