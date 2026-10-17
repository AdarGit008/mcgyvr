"""Render the config reference, the /mcgyvr skill and SETUP.md from their schemas.

``config.SCHEMA`` is declarative data — every key carries its kind, whether
it is required, its default and the prose explaining it. That makes the
reference a projection of the schema rather than a second description of it,
so a documented key and a validated key cannot drift apart. Hand-written
config docs drift the moment the schema moves; this file exists so that the
schema is the only description there is.

The reference is never kept. Every run renders it, checks it — the provenance
marker is on it and every validated key is named — and deletes it, so no copy
sits in the checkout to be read in place of the schema or to fall behind it. The
skill, the examples beside it and ``SETUP.md`` are the documents that are
written, because they are read from disk; ``make docs-check`` refuses a
committed one that differs from what its schema renders.

Two constraints shape the rendering:

1. **Deterministic.** Same schema in, byte-identical document out. Nothing
   here reads the clock, the filesystem or the environment, and nothing
   iterates an unordered collection — the walk follows declaration order,
   which is the order a reader of the config file meets the keys. A
   generator that embeds a timestamp cannot be diffed against the skill it
   last wrote, which would cost exactly the drift check.
2. **Key descriptions are never written here.** Every key's description
   comes from a ``Field``'s ``doc``. The workflow steps, the first-run text
   and the value types are scaffolding written in this file, and nothing
   checks them against the code.

The second document is the ``/mcgyvr`` skill: the one explicitly-invoked
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
to stand the ladder up: the first run, and every key the two setup files
(``fleet.yaml`` and ``policy.yaml``) accept, rendered from ``config.SCHEMA``.
It is written and kept, the way the skill is, because it is read from disk
rather than through the schema — and it lives beside the skill it is not part
of, so ``install.sh`` never copies it into a harness.
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

# An HTML comment, so it renders as nothing but survives in the source a
# would-be editor is looking at.
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
    "mapping": "free-form block",
    "int_map": "map of numbers",
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


# --- SETUP.md ----------------------------------------------------------------

#: The three lever keys, across `fleet.yaml` and `policy.yaml`, that
#: `mcgyvr local_pool` reads back. They are named here rather than described here:
#: the bullet each one gets carries the
#: `Field`'s own `doc`, so the levers cannot say one thing in SETUP.md and
#: another in the schema the loader walks.
_LEVERS: tuple[str, ...] = ("units", "ladder", "max_escalations")

#: Prose SETUP.md adds under a block's own section, after its key table, keyed
#: by the block's name. It is advice to the machine's owner, not schema: the
#: loader never reads it, no default follows from it, and it names what was
#: measured and where, so the reader can weigh it. Paragraphs, each one string.
_SETUP_NOTES: dict[str, tuple[str, ...]] = {
    "jev": (
        "The measured recommendation for the unit is Qwen3.5-4B (Q4_K_M, about "
        "3.4 GB), owner ruling of 2026-10-04 on the jev-mcorch run "
        "(lab evidence `2026-10-04-jev-mcorch`): it reads "
        "mcorch's J1 intent at 0.97 and J2 ready_to_run at 0.88, and judges the "
        "reviewer's verdict at AUROC 0.77 (satisfies_task 0.81). Qwen3.5-9B "
        "scores higher on judging code (verdict AUROC 0.86) at 5.7 GB, for a "
        "card with the room. Models of 3B and under are not usable in this role.",
    ),
}


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
        "coding`, `[c] chat`, `[a] agent`, `[m] media-gen`; Enter or `d` is",
        "`coding`), whether to dedicate a unit to Jev (Enter is no), and, for",
        "`coding` with Jev on, whether to run mcorch on a unit (Enter is no):",
        "the questions `--use-case`, `--jev` and `--mcorch` answer. It plans a",
        "model for each rig, asks before each download, writes the staged setup",
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
        "A fleet that could not be sampled — its containers not started, every",
        "unit hosted, or `media-gen`, which has no sample yet — is locked",
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
        "- `--use-case` — `coding` (the deterministic gate, the default), `chat`,",
        "  `agent` or `media-gen`.",
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
        "otherwise from the shipped model catalog. It writes, wakes and sleeps",
        "nothing.",
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


# --- the /mcgyvr skill -------------------------------------------------------

_CONTRACT_KIND_LABELS: dict[str, str] = {
    "int": "number",
    "float": "decimal number",
    "str": "text",
    "bool": "boolean",
    "str_list": "list of text",
    "glob_list": "list of globs",
    "block": "block",
    "block_list": "list of blocks",
}

# One minimal contract per deterministic operation and one model-executed
# ``code`` contract, keyed by the catalog entry each runs under. The ``code``
# one states ``limits.max_output_tokens``, as every model-written contract
# must (owner, 2026-10-14): one that states none is refused by `mcgyvr run`.
# The deterministic ones state none — a tool does the work, and no model is
# called whose reply could be capped.
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
    """One minimal valid contract per deterministic operation, and one `code`.

    Each example is loaded by
    ``tests/test_the_mcgyvr_skill_is_rendered_from_the_schema.py``; an example
    that does not validate fails the suite.
    """
    return dict(_EXAMPLE_TEMPLATES)


#: :func:`examples` as built at import, for readers that want a mapping.
EXAMPLES: dict[str, str] = examples()


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
            f"| `{name}` | {_contract_type_label(field)} | {required} | "
            f"{_contract_default_label(field)} | {_contract_describe(field)} |"
        )
    lines.append("")
    return lines


def _session_types() -> str:
    """The task types whose runs are sessions, as the skill spells them."""
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
    """The ``/mcgyvr`` skill, as text: four steps, the schema, one example per type."""
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
        "  behind a failure), `attempt_id`, `draw`, `draws`, `rows`. `draws` is the",
        "  breadth the attempt asked for (`breadth.draws`), whatever the verdict;",
        "  `rows` is how many of those draws left a journal row, which is `draws`",
        "  unless the attempt raised part-way and `0` for a try that declined or",
        "  raised before dispatching. `draw` is the draw the entry is about, and is",
        "  `null` — with `attempt_id` `null` beside it — on an `error` no single",
        "  dispatch caused: `rows: 0` means it raised before dispatching at all,",
        "  and anything more means it raised past draw `rows - 1`.",
        "- `assurance` — what an `accepted` result rests on, and `detail` says it",
        "  in a sentence: `deterministic` (a tool's change, on the gate),",
        "  `verified` (a reviewer agreed), `unverified` (no reviewer could be",
        "  asked; `detail` says why), `checked` (a `media` reply that passed",
        "  its checks) or `unchecked` (a `chat` or `agent` reply: no checks,",
        "  no review). A reply is never reviewed.",
        "- `findings` — the deterministic gate's findings for a contract that",
        "  dispatched nothing.",
        "- `delivery` — where the work went: left uncommitted in the tree (the",
        "  default), the commit, or why it was refused (as `detail`).",
        "  `committed`, `commit`, `branch`, `handoff` are the commit as fields.",
        "- `answer` — a `chat`, `agent` or `media` reply; never written to the tree.",
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
    """The examples file, as text: one minimal ``code`` contract, plus one per
    deterministic operation.

    A document that is written and kept, like the skill and ``SETUP.md``, and
    checked the same way: it is a projection of :func:`examples`, which
    ``tests/test_the_mcgyvr_skill_is_rendered_from_the_schema.py`` loads
    through ``contract.load``, so an example that stops validating is still a
    build failure. It is one file away from the skill because an agent's
    context is the scarce thing and a file costs nothing until it is opened.
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
    """Every key in the schema, at every depth, as dotted paths."""
    out: list[str] = []
    for field in fields:
        path = f"{prefix}.{field.name}" if prefix else field.name
        out.append(path)
        out.extend(_keys(field.block, path))
    return out


#: A section heading in the rendered reference: a level, and the dotted key it
#: documents. `## `units`` opens the block `units`; a block nested inside one
#: opens as `### `parent.child``. The two headings with no key — the document title
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
    section named for its parent block. A leaf name alone is not enough:
    `mode`, `model`, `enabled`, `image`, `unit` and `draws` recur across blocks,
    so a check against the whole document would pass on a namesake while a
    whole block had stopped rendering.
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

    Returns what is wrong with it — nothing, when it is sound. The file is gone
    when this returns whatever the verdict: the schema is the reference, and a
    rendered copy that outlives its check becomes a second description of the
    config that then has to be kept current. The check is the one a reader would
    make — the provenance marker is on it, and every key the loader validates is
    named under the block it belongs to.
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
    schema renders, 0 otherwise. All three kept documents — the skill, its
    examples and ``SETUP.md`` — go through here, so a stale one fails
    ``make docs-check`` whichever of the two schemas moved.
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
