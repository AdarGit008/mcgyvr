"""Render the config reference and the /mcgyvr skill from the schemas behind them.

``config.SCHEMA`` is declarative data — every key carries its kind, whether
it is required, its default and the prose explaining it. That makes the
reference a projection of the schema rather than a second description of it,
so a documented key and a validated key cannot drift apart. Hand-written
config docs drift the moment the schema moves; this file exists so that
drift is a build failure instead.

Two constraints shape the rendering:

1. **Deterministic.** Same schema in, byte-identical document out. Nothing
   here reads the clock, the filesystem or the environment, and nothing
   iterates an unordered collection — the walk follows declaration order,
   which is the order a reader of the config file meets the keys. A
   generator that embeds a timestamp cannot be diffed against its committed
   output, which would cost exactly the check this issue is about.
2. **No prose that lives only here.** Every description below comes from a
   ``Field``'s ``doc``. The fixed scaffolding is limited to structure and to
   explaining the value types, because those are properties of the loader,
   not of any one key.

The second document is the ``/mcgyvr`` skill (owner's ruling, 2026-09-03): the
one passive, always-on instruction an agent reads before it authors a
contract, generated the same way from ``contract.SCHEMA`` so the fields an
agent is told about are the fields the validator accepts. The skill carries
one minimal example per task type; each is checked by loading it through the
contract loader, so an example that stops validating is a build failure and
not a lesson in the wrong shape. The scaffolding here — the four steps — is
the workflow, which is a property of the product and of no one key.
"""

from __future__ import annotations

import argparse
import sys
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
REFERENCE_PATH = Path("archive/docs/config-reference.md")
SKILL_PATH = Path("skills/mcgyvr/SKILL.md")
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
    if field.min_value is not None:
        return f"{label} (min {field.min_value})"
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


def _section(field: Field, path: str, level: int) -> list[str]:
    """Render one block-valued key, then any block-valued keys inside it."""
    heading = "#" * level
    lines = [f"{heading} `{path}`", "", _escape(field.doc), ""]

    if field.kind == "block_map":
        lines += ["Each entry takes these keys:", ""]
    elif field.kind == "block_list":
        lines += ["An ordered list. Each entry takes these keys:", ""]

    lines += _table(field.block, "")

    for inner in field.block:
        if inner.block:
            lines += _section(inner, f"{path}.{inner.name}", level + 1)
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


# --- the /mcgyvr skill -------------------------------------------------------

_CONTRACT_KIND_LABELS: dict[str, str] = {
    "int": "number",
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
scope:
  allow: ["src/pkg/chunk.py"]
""",
}


def _contract_type_label(field: contract_schema.Field) -> str:
    if field.kind == "enum":
        choices = field.choices or (field.choices_from() if field.choices_from else ())
        return "one of " + ", ".join(f"`{c}`" for c in choices)
    label = _CONTRACT_KIND_LABELS[field.kind]
    if field.min_value is not None:
        return f"{label} (min {field.min_value})"
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
        'description: "Use whenever coding work can be delegated to a local model '
        "ladder: author a task contract, validate it, run it, read the result file, "
        "replan from the findings. Always on; the schema below is the only "
        'contract vocabulary."',
        "---",
        "",
        SKILL_MARKER,
        "",
        "# /mcgyvr",
        "",
        "Offload one scoped piece of coding work to mcgyvr's worker ladder. You author",
        "a *contract* (one target, one task, one way to judge it), mcgyvr climbs its",
        "ladder of local models cheapest-first, gates every answer deterministically,",
        "and leaves the accepted file in the working tree. It never commits unless",
        "told to, and it never writes anything else into the repository.",
        "",
        "## Step 1 — author a contract",
        "",
        "One YAML file. Every key below is the contract schema in",
        "`src/mcgyvr/contract.py`, rendered by `make docs`; unknown keys are refused,",
        "and every rejection names the key and what a valid value looks like.",
        "Pick the `task_type` first: it decides which family may start the work and",
        "what evidence the contract must carry. `mcgyvr catalog <type>` prints the",
        "type's guarantee.",
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
        "Each example loads through the contract validator; they are checked by the",
        "test suite, so copying one is copying a shape that is known to validate.",
        "",
    ]
    for task_type, text in EXAMPLES.items():
        lines += [f"#### `{task_type}`", "", "```yaml", text.rstrip("\n"), "```", ""]
    lines += [
        "## Step 2 — validate before spending anything",
        "",
        "```",
        "mcgyvr contract CONTRACT.yaml",
        "```",
        "",
        "Prints what the contract resolves to, or names the key that is wrong. Fix",
        "the contract; never guess a field.",
        "",
        "## Step 3 — run it, then read the result file",
        "",
        "```",
        "mcgyvr run CONTRACT.yaml --repo DIR [--sandbox tempdir] [--commit]",
        "```",
        "",
        "The run refuses unless it can say who typed it: Claude Code and Pi sessions",
        "are detected from the environment, otherwise pass `--orchestrator ID`. A",
        "ladder run needs a config (`mcgyvr init`, or `--config PATH`); the",
        "deterministic floor does not. The last stdout line is `result: <path>`:",
        "everything above it is scrollback, and everything the run came to is in",
        "that file, under mcgyvr's own journal directory — never in the repository.",
        "Read the file, not the scrollback. No `result:` line with exit 1 or 2 means",
        "the run never started (the contract did not load, the repo is not git, or",
        "no session could be named) or the result file could not be written; either",
        "way the reason is on stderr, and in the second case that line also says",
        "what the run came to. The file's keys:",
        "",
        "- `outcome` — `accepted`, `rejected` (deterministic gate),",
        "  `delivery_refused` (accepted, but the write to the tree was refused; see",
        "  `detail`), or the word the ladder halted on (`ladder_spent`,",
        "  `escalation_ceiling`, `attempt_ceiling`, `nothing_to_run`,",
        "  `declined_throughout`, `error`).",
        "- `attempts[]` — every rung tried: `rung`, `attempt`, `verdict` (`passed`,",
        "  `failed`, `declined`, `error`), `detail`, `findings` (the gate's lines",
        "  behind a failure), `attempt_id`, `draw`, `draws`, `rows`. `draws` is the",
        "  breadth the attempt asked for (`breadth.draws`), whatever the verdict;",
        "  `rows` is how many of those draws left a journal row, which is `draws`",
        "  unless the attempt raised part-way and `0` for a rung that declined or",
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
        "the ladder on the same answer.",
        "",
        "When `outcome` is `accepted`, the change is in `target`, uncommitted.",
        "Review it there and commit it yourself. To have mcgyvr commit instead, run",
        "with `--commit` on a tree where `target` is clean: mcgyvr refuses to",
        "overwrite an edited or uncommitted target, so restore it first",
        "(`git checkout -- <target>`) rather than rerunning on top of the last run.",
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m mcgyvr.docgen",
        description="Generate the configuration reference from the config schema.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed reference is not what the schema renders",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / REFERENCE_PATH),
        help="where to write the reference (default: the checkout's copy)",
    )
    parser.add_argument(
        "--skill-output",
        default=str(REPO_ROOT / SKILL_PATH),
        help="where to write the /mcgyvr skill (default: the checkout's copy)",
    )
    args = parser.parse_args(argv)

    documents = (
        (Path(args.output), render_reference(), "SCHEMA in src/mcgyvr/config.py"),
        (Path(args.skill_output), render_skill(), "SCHEMA in src/mcgyvr/contract.py"),
    )

    if args.check:
        stale = 0
        for target, rendered, source in documents:
            current = target.read_text(encoding="utf-8") if target.exists() else ""
            if current == rendered:
                continue
            stale += 1
            print(
                f"{target}: out of date with {source}.\n"
                f"The document is generated from it — a schema change needs it "
                f"regenerated in the same commit.\n"
                f"Run: make docs",
                file=sys.stderr,
            )
        return 1 if stale else 0

    for target, rendered, _ in documents:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        print(f"wrote {target}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
