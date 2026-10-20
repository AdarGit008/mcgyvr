"""Render the documents that are generated from mcgyvr's schemas.

`render_reference` and `render_setup` project the config `SCHEMA` into the
configuration reference and SETUP.md; `render_skill` and `render_examples`
project the contract schema into the /mcgyvr skill (one instruction generated
from that schema — setup is not part of it) and its examples file.
`main` renders the reference to a temporary file, checks it and deletes it, then
writes the other three — or, with `--check`, reports the ones that are out of
date without touching them.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from mcgyvr.catalog import catalog

from . import contract as contract_schema
from .config import FLEET_FILENAME, POLICY_FILENAME, RELIEF_FILENAME, SCHEMA, Field

# First line of every document generated from the config schema: the note that
# it is generated, which source it comes from, and the command that redraws it.
MARKER = (
    "<!-- Code generated from src/mcgyvr/config.py by `make docs`. DO NOT EDIT. -->"
)

# The checkout root, taken from this file's location (src/mcgyvr/docgen.py is
# two parents down), and the skill documents' paths inside it: where `main` writes
# and checks them unless an output flag names somewhere else.
REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = Path("skills/mcgyvr/SKILL.md")
SETUP_PATH = Path("skills/mcgyvr/SETUP.md")
EXAMPLES_PATH = Path("skills/mcgyvr/references/examples.md")
SKILL_MARKER = (
    "<!-- Code generated from src/mcgyvr/contract.py and src/mcgyvr/docgen.py by "
    "`make docs`. DO NOT EDIT. -->"
)

# The "Value types" table of both generated documents: for each type name a
# reader sees in a Type column, the rule the loader enforces on it, phrased for
# someone writing the config rather than for someone reading the validator.
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
        "A number that may carry a fraction.",
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
        "free-form block",
        "A nested mapping whose keys the schema does not fix.",
    ),
    (
        "map of numbers",
        "A mapping from names you choose to whole numbers.",
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
    "glob_list": "list of globs",
    "mapping": "free-form block",
    "int_map": "map of numbers",
    "block": "block",
    "block_map": "block map",
    "block_list": "list of blocks",
}


def _escape(text: str) -> str:
    """Escape a pipe, so the text cannot split the Markdown table cell it is in."""
    return text.replace("|", "\\|")


def _type_label(field: Field) -> str:
    if field.kind == "enum":
        return "one of " + ", ".join(f"`{c}`" for c in field.valid_choices())
    label = _KIND_LABELS[field.kind]
    # A numeric field's declared bounds are part of its type as a reader sees it:
    # "number (min 1)" says more than "number". A field with neither bound keeps the
    # bare label.
    bounds = []
    if field.min_value is not None:
        bounds.append(f"min {field.min_value}")
    if field.max_value is not None:
        bounds.append(f"max {field.max_value}")
    if bounds:
        return f"{label} ({', '.join(bounds)})"
    return label


def _default_label(field: Field) -> str:
    """Return the Default cell the reference should show for a field.

    A required field, and a block of any shape, shows an em dash rather than a
    value; a list shows `[]` when empty and its contents otherwise; a boolean is
    lowercased so it reads as YAML; a field with no default at all shows
    `unset`.
    """
    if field.required:
        return "—"
    if field.kind in ("block", "block_map", "block_list", "mapping", "int_map"):
        return "—"
    if field.kind == "str_list":
        return "`[]`" if not field.default else f"`{list(field.default)}`"
    if field.default is None:
        return "unset"
    if field.kind == "bool":
        return f"`{str(field.default).lower()}`"
    return f"`{field.default}`"


def _describe(field: Field) -> str:
    """Return the Description cell: the field's doc, plus how to bind it.

    A field carrying a `bind_hint` gets it appended as a sentence, because the
    hint is what to write for a key the config may leave out. The whole cell is
    escaped for its table row.
    """
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
    """Render one block field as a section, heading included.

    The body is the field's own doc, a line saying what each entry is when the
    field is a map or a list of blocks, a table of the block's keys, and a
    section one level deeper for every inner field that has keys of its own.
    With `dotted` each inner table key is written as its full dotted path;
    without it, keys are named as they appear inside the block.
    """
    heading = "#" * level
    lines = [f"{heading} `{path}`", "", _escape(field.doc), ""]

    if field.kind == "block_map":
        lines += ["Each entry takes these keys:", ""]
    elif field.kind == "block_list":
        lines += ["An ordered list; each entry takes these keys:", ""]

    lines += _table(field.block, f"{path}." if dotted else "")

    for inner in field.block:
        if inner.block:
            lines += _section(inner, f"{path}.{inner.name}", level + 1, dotted)
    return lines


def render_reference() -> str:
    """Render the configuration reference from the config `SCHEMA`.

    The marker, the prose about how the loader behaves, and the value-type table
    are fixed; the top-level key table and a section per block are projections of
    `SCHEMA`, so a key that is documented and a key that is validated cannot
    disagree.
    """
    lines = [
        MARKER,
        "",
        "# Configuration reference",
        "",
        f"Every key `{FLEET_FILENAME}`, `{POLICY_FILENAME}` and "
        f"`{RELIEF_FILENAME}` accept.",
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


# SETUP.md alone: the constants its prose and its notes are built from.

#: The three keys SETUP.md lists as the levers, whose effect `mcgyvr local_pool`
#: prints. Each bullet's text is the key's own schema doc, so the list cannot
#: drift from the field it describes; a name here that `SCHEMA` does not declare
#: raises `KeyError` at render time instead of printing a bullet with nothing
#: after it.
_LEVERS: tuple[str, ...] = ("units", "ladder", "max_escalations")

#: Paragraphs appended after a top-level block's section in SETUP.md, keyed by
#: that block's name: what a reader needs that the schema doc of a single key
#: has no room for. A block with no entry here ends at its own tables;
#: `_SETUP_NOTES` is only consulted for top-level fields with keys.
_SETUP_NOTES: dict[str, tuple[str, ...]] = {
    "jev": (
        "The measured model for this unit: lab record "
        "`records/evidence/2026-10-04-jev-mcorch`.",
    ),
}


def render_setup() -> str:
    """Render SETUP.md: how a machine comes to have a config, and what it says.

    The prose is fixed; the value types, the top-level key table and one section
    per block are rendered from `SCHEMA`, with inner keys named by full path, and
    the `_SETUP_NOTES` paragraphs are appended after the block they belong to.
    """
    by_name = {field.name: field for field in SCHEMA}
    lines = [
        MARKER,
        "",
        "# Setting up mcgyvr",
        "",
        "First run, once per machine. Nothing here is read to author a contract;",
        f"this is how `{FLEET_FILENAME}` and `{POLICY_FILENAME}` come to exist "
        f"and what they can say.",
        "",
        "```",
        "mcgyvr setup",
        "mcgyvr local_pool",
        "```",
        "",
        "`mcgyvr setup` reads each rig once and stages a setup bound to what it",
        "serves in a folder of the run's own, `$MCGYVR_DATA/setup/<run>/` (default",
        "`~/.local/state/mcgyvr/setup/<run>/`), kept as the record of that run; it",
        "writes nothing in the working directory. It prints what was decided and",
        "why, then what is *not* configured and what that costs.",
        "",
        "Run at a terminal with no flags, it asks which rigs serve — `local`,",
        "`remote` or `both` (Enter is `local`) — and, for `remote` or `both`,",
        "the ssh host(s) to read. It then asks the use case by letter (`[d]",
        "coding`, `[c] chat`, `[a] agent`; Enter or `d` is",
        "`coding`), whether to dedicate a unit to Jev (Enter is no), and, for",
        "`coding` with Jev on, whether to run mcorch on a unit (Enter is no):",
        "the questions `--use-case`, `--jev` and `--mcorch` answer. It plans a",
        "model of that use case for each rig, says whether its candidates came",
        "from the Hugging Face Hub, the cache of an earlier Hub read or the",
        "shipped catalog, asks before each download, writes the staged setup",
        "once and emits its launch specs once, and asks before it starts the",
        "serving containers through the door. It then samples the fleet: a read",
        "of every rig, a",
        "probe and a load of every unit, the use case's sample task (for",
        "`coding`, a one-function bug fix the deterministic gate must pass) and",
        "a Jev unit's one typed choice. A green sample is stamped, and on",
        "`Lock the fleet and name it live? [y/N]` it is locked, promoted and",
        "named live. A red sample is never locked; its reasons are printed.",
        "",
        "When the interactive setup finishes, it offers to append",
        '`export PATH="$HOME/.local/bin:$PATH"` to the login shell\'s rc file',
        "(`~/.bashrc`, `~/.zshrc`, `~/.profile`, or",
        "`~/.config/fish/config.fish`, by `$SHELL`), once you say yes; a file",
        "that already carries a `.local/bin` PATH line is left alone.",
        "",
        "A fleet that could not be sampled — its containers not started, or",
        "every unit hosted — is locked",
        "approved on no evidence only once you say so: setup says why and what",
        "that means, and asks `Lock it approved on no evidence? [y/N]`. With",
        "flags, setup binds the servers already answering and starts none, so",
        "nothing is sampled; `--accept-unsampled` is that acknowledgment, and",
        "without it nothing is locked. Backends on another machine come in with",
        "`--host` (repeatable).",
        "",
        "A locked fleet is promoted to a folder of its own under",
        "`$MCGYVR_HOME/fleets/` and named in `$MCGYVR_HOME/live.json`, with",
        "`serving.enable_sleep_wake` on and its launch specs in the staged folder",
        "(`serving.compose_dir`), so a request to a unit that is down wakes it",
        "through the door. That live fleet is the config every command reads,",
        "wherever it is run, unless `$MCGYVR_CONFIG` or `--config DIR` names",
        "another; a `fleet.yaml` in the working directory is not read. Setup",
        "stages in `PATH` or `--config DIR` when one is named, and there refuses",
        "to overwrite a setup without `--force`.",
        "",
        "A hosted API unit comes in with `--api` (repeatable), written as",
        "`model=<id>,address=<url>,api_key_env=<VAR>` — so a machine with no",
        "GPU and no local backend gets the same two files rather than a",
        "refusal. `api_key_env` is the NAME of the environment variable",
        "holding the key; the key itself is never written to either file.",
        "A machine with no local backend and no `--api` still refuses, because",
        "a config that dispatches nowhere is not a head start.",
        "",
        "What the config is for comes in with these, all optional:",
        "",
        "- `--use-case` — `coding` (the deterministic gate, the default), `chat`",
        "  or `agent`.",
        "- `--deployment` — `hybrid` (an API-tier orchestrator drives mcgyvr) or",
        "  `local-only` (mcgyvr is the backend); the default is `local-only` for",
        "  `chat` and `hybrid` otherwise.",
        "- `--priority` — compose the ladder for `throughput`, `quality` or",
        "  `cost` instead of the default ladder.",
        "- `--profile` — deprecated, removed in the release after next: use",
        "  `--priority`. A word naming a priority maps onto it, other text is",
        "  ignored, and either way it warns.",
        "- `--jev UNIT` — dedicate VRAM to a Jev unit, the written unit every",
        "  typed decision asks; it is never slept or woken.",
        "- `--mcorch UNIT` with `--window TOKENS` — serve that unit as the",
        "  conversational agent a harness points at (`mcgyvr mcorch serve`);",
        "  it needs `--jev`.",
        "- `--session-sandbox` — `tempdir` (the default) or `docker`: whether a",
        "  `chat` or `agent` run that runs no command gets a task container",
        "  (`sandbox.sessions`).",
        "",
        "`mcgyvr setup --help` has each one's full text.",
        "",
        "Two commands measure and plan before `mcgyvr setup` writes a config.",
        "`mcgyvr scan` measures this machine (free and total VRAM, available RAM,",
        "cores, timed memory bandwidth, free disk), records it as this machine's",
        "rig file (`localhost.json` in the rig-file folder, `$MCGYVR_RIGS`, by",
        "default `~/.mcgyvr/rigs`), says what moved since the last record, and",
        "exits 4 when a card, total RAM, the cores or the bandwidth moved.",
        "`mcgyvr recommend --profile coding --users N --host RIG` re-reads each",
        "rig over ssh and prints one JSON plan: which checkpoint and engine serve",
        "that profile, from `--model-store DIR` when a checkpoint there fits,",
        "otherwise from the use case's candidates on the Hugging Face Hub",
        "(ranked by downloads; the cache of an earlier read, then the shipped",
        "model catalog, when the Hub cannot be asked), says which answered,",
        "and names the host it goes on. `chat` and `agent` plan one unit: the",
        "biggest model that fits, at the most context that fits and at least",
        "8192 per user. It wakes and sleeps nothing, and writes nothing but that",
        "cache.",
        "",
        "A setup is two files in one directory, and `mcgyvr setup` writes both",
        "(staged under the data folder, as above):",
        "",
        f"- `{FLEET_FILENAME}` — what runs where: `units`, `rigs` and `fleets`.",
        f"- `{POLICY_FILENAME}` — how work moves over those units: `ladder` and "
        "every other top-level key below but `relief`.",
        "",
        f"A third file, `{RELIEF_FILENAME}`, holds `relief`: the units other",
        "people lend you through a hub. `mcgyvr rig rungs sync` writes it whole",
        "and nothing else does, so it is neither locked nor edited by hand.",
        "",
        "Each file refuses a key that belongs in the other. `rigs`, `fleets` and",
        "each unit's `unit_id` are not in the tables below: the fleet lock",
        "keys on them, and the run config drops them when it loads the",
        "setup. A `fleets` entry takes `layout` and `next`; a `rigs` entry is",
        "checked only as a block. `examples/fleet.yaml` shows all three.",
        "",
        "`mcgyvr local_pool` reads that config back: the usable rungs "
        "cheapest-first with",
        "their family, attempt budget and model; the escalation ceiling and where it",
        "came from; every skipped rung with the reason it was skipped; and the",
        "orchestrator and verifier models. `--probe` also asks each unit whether it",
        "is answering — off by default, because resolving a ladder should not need",
        "a network. Run it whenever a run picks a rung you did not expect.",
        "",
        "Three keys across the two files are the levers, and `mcgyvr local_pool` "
        "is how",
        "you read all three:",
        "",
    ]
    for lever in _LEVERS:
        lines.append(f"- `{lever}` — {_escape(by_name[lever].doc)}")
    lines += [
        "",
        "`mcgyvr config` prints the resolved config; `mcgyvr detect` shows what",
        "can run the work; `mcgyvr capabilities` shows the shipped capability table.",
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
            for note in _SETUP_NOTES.get(field.name, ()):
                lines += [note, ""]

    return "\n".join(lines).rstrip("\n") + "\n"


# The example contracts examples.md prints, keyed by name: one `code` contract a
# model has to satisfy, and one per deterministic operation, each named after the
# operation so `render_examples` can sort it by whether `catalog()` lists that
# name. A value is a whole YAML document held as a string, ready to drop into a
# fenced block verbatim; the test suite loads every one through the contract
# validator, so an example you copy is an example known to load.
_EXAMPLE_TEMPLATES: dict[str, str] = {
    "format": """\
id: format-pkg
task_type: code
operation: format
task: Reformat the module with the project's formatter.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
""",
    "import_sort": """\
id: sort-imports
task_type: code
operation: import_sort
task: Order the module's imports with the project's import sorter.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
""",
    "lint_fix": """\
id: lint-pkg
task_type: code
operation: lint_fix
task: Apply the linter's own autofixes to the module.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
""",
    "rename_symbol": """\
id: rename-fetch
task_type: code
operation: rename_symbol
task: Rename fetch_page to fetch_document in the module.
target: src/pkg/messy.py
rename:
  from: fetch_page
  to: fetch_document
scope:
  allow: ["src/pkg/**"]
""",
    "code": """\
id: impl-chunk
task_type: code
task: >-
  Implement chunk. Split a list into consecutive groups of at most size
  elements, preserving order; the last group is shorter when the length does
  not divide evenly. An empty list yields an empty list. Raise ValueError
  unless size is a positive integer.
target: src/pkg/chunk.py
interface: "def chunk(items: list[T], size: int) -> list[list[T]]"
stop_conditions:
  - Whether a size larger than the list is an error or one group is not stated.
demonstration: ["pytest -q tests/test_chunk.py"]
risk: low
limits:
  max_output_tokens: 4096
scope:
  allow: ["src/pkg/chunk.py"]
""",
}


def examples() -> dict[str, str]:
    """Return the example contracts as a copy, so callers cannot mutate them."""
    return dict(_EXAMPLE_TEMPLATES)


#: The example contracts, materialised once at import time by `examples()`.
EXAMPLES: dict[str, str] = examples()


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
    if field.kind == "bool":
        return f"`{str(field.default).lower()}`"
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
        if field.required and field.session_optional:
            required = f"**yes**, not for {_session_types()}"
        lines.append(
            f"| `{name}` | {_type_label(field)} | {required} | "
            f"{_contract_default_label(field)} | {_contract_describe(field)} |"
        )
    lines.append("")
    return lines


def _session_types() -> str:
    """Name the task types that run as a session, joined by `/`.

    A session has no target and no scope, so a key the schema marks
    session-optional is required for every other task type, and the contract
    tables say which types that leaves out.
    """
    return "/".join(f"`{t.name}`" for t in contract_schema.task_types() if t.session)


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
    """Render SKILL.md: the /mcgyvr skill's front matter, prose and four steps.

    The front matter, the walkthrough prose and the result-file key list are
    fixed; the contract key tables and their nested sections are rendered from
    the contract `SCHEMA`, and the deterministic operation names from
    `contract_schema.operations()`.
    """
    lines = [
        "---",
        "name: mcgyvr",
        'description: "Offload one scoped coding task to mcgyvr, a CLI that runs '
        "it on deterministic tools, local models or API models and keeps only "
        "what its deterministic gate accepts. Use it when a change has one "
        "target and a way to judge it (a scoped code edit whose evidence is "
        "derived from the contract, or a deterministic operation: format, "
        "import sort, lint fix, rename): "
        "author a task contract, validate it, run it, read the result file, "
        "replan from the findings. It never loads itself; invoke it with "
        '/mcgyvr. The schema below is the only contract vocabulary."',
        "disable-model-invocation: true",
        "---",
        "",
        SKILL_MARKER,
        "",
        "# /mcgyvr",
        "",
        "Offload one scoped piece of coding work to mcgyvr. You author a *contract*",
        "(one target, one task, one way to judge it), mcgyvr gates every answer",
        "deterministically, and leaves an accepted `code` change in the working",
        "tree. It never commits unless told to, and it never writes anything else",
        "into the repository.",
        "",
        f"A {_session_types()} run is a *session*: no `target`, no `scope`; the",
        "reply is the result file's `answer`, kept in mcgyvr's session log.",
        "One that declares no command gets no container unless the config's",
        "`sandbox.sessions` is `docker`.",
        "",
        "## Step 1 — author a contract",
        "",
        "One YAML file. Every key below is the contract schema in",
        "`src/mcgyvr/contract.py`, rendered by `make docs`; unknown keys are refused,",
        "and every rejection names the key and what a valid value looks like.",
        "Pick the `task_type` first. For `code`, evidence is derived from the "
        "contract's own fields, never chosen; `operation:` has a tool make the "
        "change instead. `mcgyvr catalog <type>` prints the type's guarantee.",
        "`mcgyvr delegate PROMPT [--repo DIR]` has the config's `orchestrator` draft",
        "validated contracts from a request instead and prints them; `--run` runs",
        "each one.",
        "",
        "### Keys",
        "",
    ]
    lines += _contract_table(contract_schema.SCHEMA, "")
    for field in contract_schema.SCHEMA:
        if field.block:
            lines += _contract_section(field, field.name)
    lines += [
        "### Deterministic operations",
        "",
        "Not task types: `task_type: code` with `operation:` "
        + ", ".join(f"`{op.name}`" for op in contract_schema.operations())
        + " has a tool make the change, never a model.",
        "",
        "### Minimal examples",
        "",
        f"`{EXAMPLES_PATH}` carries one `code` contract and one per operation,",
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
        "the contract; never guess a field. A `code` contract states",
        "`limits.max_output_tokens`, within its unit's ceiling, or `run` refuses it.",
        "",
        "## Step 3 — run it, then read the result file",
        "",
        "```",
        "mcgyvr run CONTRACT.yaml --repo DIR [--config PATH] "
        "[--sandbox tempdir] [--[no-]commit] [--branch NAME]",
        "```",
        "",
        "The run works on the repository as committed at HEAD: uncommitted edits",
        "and untracked files, including a test you just wrote, are not in the",
        "sandbox.",
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
        "  - `nothing_to_change` — a tool found nothing to do; exit 0.",
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
        "  behind a failure), `attempt_id`, `draw`, `draws`, `rows`, `relief`,",
        "  `model`, `address`. `draws` is the",
        "  breadth the attempt asked for (`breadth.draws`), whatever the verdict;",
        "  `rows` is how many of those draws left a journal row, which is `draws`",
        "  unless the attempt raised part-way and `0` for a try that declined or",
        "  raised before dispatching. `draw` is the draw the entry is about, and is",
        "  `null` — with `attempt_id` `null` beside it — on an `error` no single",
        "  dispatch caused: `rows: 0` means it raised before dispatching at all,",
        "  and anything more means it raised past draw `rows - 1`. `relief` is",
        "  `true` for a rung lent through a hub — recorded like any try, but",
        "  charged against the budget only when it passes — and `model`/`address`",
        "  name the unit that served it, so a relief try shows which borrowed",
        "  machine answered.",
        "- `assurance` — what an `accepted` result rests on, and `detail` says it",
        "  in a sentence: `deterministic` (a tool's change, on the gate),",
        "  `verified` (a reviewer agreed), `unverified` (no reviewer could be",
        "  asked; `detail` says why) or `unchecked` (a `chat` or `agent` reply:",
        "  no checks, no review). A reply is never reviewed.",
        "- `findings` — the deterministic gate's findings for a contract that",
        "  dispatched nothing.",
        "- `delivery` — where the work went: left uncommitted in the tree (the",
        "  default), the commit, or why it was refused (as `detail`).",
        "  `committed`, `commit`, `branch`, `handoff` are the commit as fields.",
        "- `answer` — a `chat` or `agent` reply; never written to the tree.",
        "- `session_record` — a session's record (question, answer, unit, times,",
        "  outcome) under `<journal>/sessions/`; `mcgyvr sessions [ID]` reads it.",
        "- `target`, `contract`, `task_type`, `orchestrator`, `run`, `session_file`,",
        "  `journal`, `exit_code`.",
        "- `copy_errors` — a `--record DIR` copy that could not be written, and",
        "  why. Empty on almost every run. mcgyvr's own record under `journal`",
        "  is complete whatever this says; a copy is not a sink and its failure",
        "  does not stop a run.",
        "- `notes` — the uncommitted and untracked paths the sandbox of HEAD",
        "  left out, what the baseline left behind (now cleaned up), and what",
        "  a rename renamed.",
        "",
        "Every run is journaled under the config's `journal.dir` and nothing on",
        "the command line moves it — that one directory is where every run can",
        "be counted. Deterministic runs are there too, as a row naming",
        "the program that did the work with `tier: deterministic` and no prompt",
        "or reply beside it. `--record DIR` adds a complete second copy for your",
        "own use; `--result PATH` says where you read the result file.",
        "",
        "Exit codes: 0 accepted or nothing to change, 1 not accepted or error,",
        "2 usage (including no session to file the run under), 3 a live fleet",
        "refused admission.",
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
        "When `outcome` is `accepted`, the change is in `target` (a rename's: in",
        "each file `delivery` names), uncommitted (a session changes nothing: its",
        "reply is `answer`).",
        "Review it there and commit it yourself. To have mcgyvr commit instead, run",
        "with `--commit` or `--branch NAME` on a tree where those files are",
        "clean: mcgyvr refuses to overwrite an edited or uncommitted file, so",
        "restore it first (`git checkout -- <target>`) rather than rerunning on",
        "top of the last run.",
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def render_examples() -> str:
    """Render examples.md: every example contract, split into two sections.

    A name `catalog()` lists as a deterministic operation goes under the
    operations heading and every other name under the one a model satisfies;
    within a section the order is the order of `_EXAMPLE_TEMPLATES`.
    """
    operation_names = {op.name for op in catalog().operations}
    type_examples = {
        name: text for name, text in examples().items() if name not in operation_names
    }
    operation_examples = {
        name: text for name, text in examples().items() if name in operation_names
    }
    lines = [
        SKILL_MARKER,
        "",
        "# One minimal `code` contract, and one per deterministic operation",
        "",
        "Each loads through the contract validator; they are checked by the test",
        "suite, so copying one is copying a shape that is known to validate. The",
        "keys are documented in `SKILL.md`.",
        "",
        "## A change a model makes",
        "",
    ]
    for name, text in type_examples.items():
        lines += [f"### `{name}`", "", "```yaml", text.rstrip("\n"), "```", ""]
    lines += [
        "## Deterministic operations (`task_type: code` with `operation:`)",
        "",
    ]
    for name, text in operation_examples.items():
        lines += [f"### `{name}`", "", "```yaml", text.rstrip("\n"), "```", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def _keys(fields: Sequence[Field], prefix: str = "") -> list[str]:
    """Return every key path in a schema, depth first, parents before children.

    A nested field's path is its ancestors' names joined by dots, which is the
    form the reference's headings and table keys use.
    """
    out: list[str] = []
    for field in fields:
        path = f"{prefix}.{field.name}" if prefix else field.name
        out.append(path)
        out.extend(_keys(field.block, path))
    return out


#: Reading a rendered document back, so its own text can be checked against the
#: schema it came from. `_HEADING` matches the heading `_section` emits: a level
#: of `#`s, a space, and a backticked key path. A heading of any other shape names
#: no section here; it only bounds one, which is how `_sections` finds where a
#: body ends.
_HEADING = re.compile(r"^#+ +`([A-Za-z0-9_.]+)`\s*$", re.MULTILINE)

#: The heading the top-level key table sits under, matched as text rather than by
#: the key-path pattern because it names no key.
_TOP_LEVEL = "## Top-level keys"


def _sections(text: str) -> dict[str, str]:
    """Map each section name in a rendered document to the body beneath it.

    A name is a backticked key path taken from a heading, or `_TOP_LEVEL` for the
    top-level table's heading. A body runs to the next heading of any kind, so a
    section carries its own tables and not its children's.
    """
    starts: list[tuple[int, int, str]] = []
    for match in _HEADING.finditer(text):
        starts.append((match.start(), match.end(), match.group(1)))
    for match in re.finditer(rf"^{re.escape(_TOP_LEVEL)}\s*$", text, re.MULTILINE):
        starts.append((match.start(), match.end(), _TOP_LEVEL))
    # The offset of every heading, whatever its shape: the first one after a
    # section start is where that section's body ends.
    bounds = sorted(
        {match.start() for match in re.finditer(r"^#+ .*$", text, re.MULTILINE)}
    )
    out: dict[str, str] = {}
    for start, body_start, name in sorted(starts):
        after = [b for b in bounds if b > start]
        out[name] = text[body_start : after[0]] if after else text[body_start:]
    return out


def reference_problems(text: str) -> list[str]:
    """Return what a rendered reference fails to document, in plain words.

    The DO NOT EDIT marker has to be the first line, and every key path in
    `SCHEMA` has to be named under its parent's section. An empty list means the
    document agrees with the schema.
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
            # The block itself is undocumented, so every key in it is missing for
            # one reason. Report the block once — `absent` keeps the rest of its
            # keys from repeating the finding — and say it is missing entirely,
            # which is a different repair from a section that forgot to name a
            # key it does document.
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
    """Render the reference into `target`, read it back, delete it, check it.

    The text is validated as the file on disk, and `target` is removed whether
    the check passed, failed or raised.
    """
    rendered = render_reference()
    try:
        target.write_text(rendered, encoding="utf-8")
        text = target.read_text(encoding="utf-8")
    finally:
        target.unlink(missing_ok=True)
    return reference_problems(text)


def _write_or_check(target: Path, rendered: str, schema: str, check: bool) -> int:
    """Write a rendered document, or in check mode compare it with the copy.

    Without `check` it creates the parent directory, writes the document and
    returns 0. With `check` it returns 0 when the file already holds what the
    schema renders, and 1 when the file is stale or missing, after naming the
    document and the schema it was generated from.
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
