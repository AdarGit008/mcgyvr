"""Render the configuration reference from the schema that validates it.

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
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

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
        help="where to write (default: the checkout's copy of the reference)",
    )
    args = parser.parse_args(argv)

    rendered = render_reference()
    target = Path(args.output)

    if args.check:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current == rendered:
            return 0
        print(
            f"{target}: out of date with the config schema.\n"
            f"The reference is generated from SCHEMA in src/mcgyvr/config.py — "
            f"a schema change needs it regenerated in the same commit.\n"
            f"Run: make docs",
            file=sys.stderr,
        )
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
