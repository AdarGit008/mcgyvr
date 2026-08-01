"""Compose detection and proposal into a written config.

The first thing a stranger runs, and the command the v1 release criterion is
written around: clean machine, no key, no Docker, and the result is a config
that supports a real local task.

Three properties are enforced here rather than left to habit:

1. **Non-interactive.** The output is a file plus a printed account of what
   was decided and why. Nothing prompts, so an agent can invoke it.
2. **Idempotent.** Re-running reports a delta and does not overwrite. Hand
   edits are the expected state of this file — it is the one file the
   product asks a person to maintain — so clobbering them silently would be
   the worst thing this command could do. Writing over them requires
   ``force``, and the delta says exactly what would change.
3. **Honest about what is missing.** No API key, no Docker and no GPU are
   all supported, and each is reported with what it costs rather than
   quietly degraded.

The generated file's comments are rendered from ``config.SCHEMA`` — the same
declarations the loader validates against. A comment cannot drift from the
rule it describes, because there is only one of each.
"""

from __future__ import annotations

import re
import textwrap
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcgyvr.capability import CapabilityTable
from mcgyvr.capability import load as load_table
from mcgyvr.config import SCHEMA, SCHEMA_VERSION, Config, ConfigError, Field
from mcgyvr.config import load as load_config
from mcgyvr.config import parse as parse_config
from mcgyvr.detect import Detection, detect
from mcgyvr.propose import AvailableSource, Proposal, propose

COMMENT_WIDTH = 78

# A YAML scalar is safe bare only if it cannot be read as anything else. A
# model id like `qwen2.5-coder:7b` carries a colon and a URL carries both a
# colon and slashes, so most values here need quoting.
_BARE_SAFE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")
_RESERVED = frozenset({"true", "false", "null", "yes", "no", "on", "off", "~"})


@dataclass(frozen=True)
class Delta:
    """One difference between the config on disk and what would be written."""

    key: str
    current: Any
    proposed: Any

    def __str__(self) -> str:
        return f"{self.key}: {_show(self.current)} -> {_show(self.proposed)}"


@dataclass(frozen=True)
class InitResult:
    path: Path
    created: bool
    written: bool
    deltas: tuple[Delta, ...] = ()
    decisions: tuple[str, ...] = ()
    limits: tuple[str, ...] = ()
    loadable: bool = True
    content: str = ""


def _show(value: Any) -> str:
    if value is None:
        return "(unset)"
    return repr(value)


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if _BARE_SAFE.match(text) and text.lower() not in _RESERVED:
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _comment(text: str, indent: int) -> list[str]:
    pad = " " * indent
    width = max(COMMENT_WIDTH - indent, 30)
    return [f"{pad}# {line}" for line in textwrap.wrap(text, width=width)]


def _render_leaf(spec: Field, value: Any, indent: int) -> list[str]:
    pad = " " * indent
    lines = _comment(spec.doc, indent)
    if value is None or value == []:
        # Unset and optional. Shown commented so the key is discoverable
        # without being bound to a value nobody chose.
        hint = spec.bind_hint or "unset"
        lines.append(f"{pad}# {spec.name}:  # {hint}")
        return lines
    if spec.kind == "str_list":
        lines.append(f"{pad}{spec.name}:")
        lines.extend(f"{pad}  - {_scalar(item)}" for item in value)
        return lines
    lines.append(f"{pad}{spec.name}: {_scalar(value)}")
    return lines


def _render_fields(
    fields: Sequence[Field], data: Mapping[str, Any], indent: int
) -> list[str]:
    lines: list[str] = []
    for spec in fields:
        value = data.get(spec.name)
        if spec.kind == "block":
            lines.extend(_comment(spec.doc, indent))
            lines.append(f"{' ' * indent}{spec.name}:")
            lines.extend(_render_fields(spec.block, value or {}, indent + 2))
        elif spec.kind == "block_map":
            lines.extend(_comment(spec.doc, indent))
            lines.append(f"{' ' * indent}{spec.name}:")
            for name, block in (value or {}).items():
                lines.append(f"{' ' * (indent + 2)}{name}:")
                lines.extend(_render_fields(spec.block, block, indent + 4))
        elif spec.kind == "block_list":
            lines.extend(_comment(spec.doc, indent))
            lines.append(f"{' ' * indent}{spec.name}:")
            for item in value or []:
                lines.extend(_render_list_item(spec.block, item, indent + 2))
        else:
            lines.extend(_render_leaf(spec, value, indent))
        lines.append("")
    return lines


def _render_list_item(
    fields: Sequence[Field], item: Mapping[str, Any], indent: int
) -> list[str]:
    pad = " " * indent
    lines: list[str] = []
    for position, spec in enumerate(fields):
        value = item.get(spec.name)
        if value is None:
            continue
        marker = "- " if position == 0 else "  "
        lines.append(f"{pad}{marker}{spec.name}: {_scalar(value)}")
    return lines


def render(data: Mapping[str, Any], decisions: Sequence[str] = ()) -> str:
    """Render a config file: values from ``data``, comments from the schema."""
    lines = [
        "# mcgyvr configuration — one file to edit.",
        "#",
        "# Generated by `mcgyvr init`, and safe to edit by hand: re-running",
        "# init reports what it would change rather than overwriting you.",
        "#",
        "# Comments below are rendered from the same schema the loader",
        "# validates against, so they cannot drift from what is enforced.",
        "#",
        "# Credentials are never values here. A key is named by the",
        "# environment variable that holds it, never written in this file.",
    ]
    if decisions:
        lines.append("#")
        lines.append("# What init decided on this machine:")
        for decision in decisions:
            lines.extend(
                f"#   {line}"
                for line in textwrap.wrap(decision, width=74, subsequent_indent="    ")
            )
    if not data.get("sources") or not data.get("ladder", {}).get("tiers"):
        lines.extend(
            [
                "#",
                "# NOTE: nothing local was reachable, so this file has no source",
                "# and no rung. It will NOT load until you bind both — that is",
                "# deliberate: a config that dispatches nowhere would fail later",
                "# and further from the cause. Uncomment and adjust:",
                "#",
                "#   sources:",
                "#     ollama:",
                '#       base_url: "http://localhost:11434"',
                "#       api: ollama",
                "#   ladder:",
                "#     tiers:",
                "#       - name: worker_local_qwen2.5-coder-7b",
                "#         source: ollama",
                '#         model: "qwen2.5-coder:7b"',
            ]
        )
    lines.append("")
    lines.extend(_render_fields(SCHEMA, data, 0))
    text = "\n".join(lines).rstrip("\n")
    return text + "\n"


def build(detection: Detection, proposal: Proposal) -> dict[str, Any]:
    """The config data implied by what was detected and proposed."""
    sources = {
        backend.name: {
            "base_url": backend.base_url,
            "api": backend.api,
            "max_parallel": 1,
        }
        for backend in detection.backends
    }
    tiers = [
        {"name": rung.name, "source": rung.source, "model": rung.model}
        for rung in proposal.rungs
    ]
    return {
        "version": SCHEMA_VERSION,
        "sources": sources,
        "ladder": {"tiers": tiers},
        "orchestrator": {"source": None, "model": None},
        "verifier": {"enabled": False, "source": None, "model": None},
        "sandbox": {
            "mode": "docker" if detection.docker else "tempdir",
            "image": None,
            "setup": [],
        },
        "delivery": {"mode": "pull_request", "token_env": None},
        "budgets": {"max_escalations": 1, "task_timeout_s": 900},
    }


def _sources_for(detection: Detection) -> list[AvailableSource]:
    return [
        AvailableSource(
            name=backend.name,
            backend=backend.name,
            models_present=frozenset(backend.models),
        )
        for backend in detection.backends
    ]


def _decisions(detection: Detection, proposal: Proposal) -> tuple[str, ...]:
    decisions: list[str] = []
    if detection.gpus:
        gpu = detection.gpus[0]
        decisions.append(f"GPU {gpu.name} with {gpu.vram_gb:g} GB, via {gpu.how}.")
    for backend in detection.backends:
        decisions.append(
            f"Source '{backend.name}' at {backend.base_url} speaking "
            f"{backend.api}; {len(backend.models)} model(s) already pulled."
        )
    for rung in proposal.rungs:
        presence = (
            "already pulled"
            if rung.already_present
            else f"needs a ~{rung.weights_gb:g} GB pull"
        )
        decisions.append(
            f"{rung.name} -> {rung.model} on {rung.source}: "
            f"{rung.quality:.1%} HumanEval+ pass@1, {rung.vram_gb:g} GB, "
            f"{presence}."
        )
    return tuple(decisions)


def _limits(detection: Detection, proposal: Proposal) -> tuple[str, ...]:
    """What is NOT configured, and what that costs. Never silent.

    The proposal's own notes belong here rather than among the decisions:
    "no backend answered" and "needs a 9 GB pull" are both statements about
    what this install cannot do yet, not about what was chosen.
    """
    limits = list(detection.notes) + list(proposal.notes)
    if proposal.is_local_empty:
        limits.append(
            "No local rung is bound, so nothing can run without an API "
            "source. Bind one under `sources` and point `ladder.tiers` at it."
        )
    limits.append(
        "No API provider is configured. This is a supported install: the "
        "deterministic gate is the acceptance bar, and verification is off "
        "rather than on-and-unbound. Bind `orchestrator` and set "
        "`verifier.enabled: true` once you have a key."
    )
    if not detection.docker:
        limits.append(
            "sandbox.mode is `tempdir`, the explicitly weaker mode. "
            "Acceptance commands are arbitrary shell from a contract, so "
            "install Docker before running contracts you did not write."
        )
    return tuple(limits)


def _flatten(data: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten to dotted keys so a delta can name exactly what changed."""
    if isinstance(data, Mapping):
        out: dict[str, Any] = {}
        for key, value in data.items():
            out.update(_flatten(value, f"{prefix}.{key}" if prefix else str(key)))
        return out
    if isinstance(data, list):
        out = {}
        for index, value in enumerate(data):
            out.update(_flatten(value, f"{prefix}.{index}"))
        return out
    return {prefix: data}


def diff(current: Config, proposed: Mapping[str, Any]) -> tuple[Delta, ...]:
    """What would change if the proposal were written over ``current``."""
    have = _flatten(current.data)
    want = _flatten(proposed)
    keys = sorted(set(have) | set(want))
    return tuple(
        Delta(key, have.get(key), want.get(key))
        for key in keys
        if have.get(key) != want.get(key)
    )


def initialize(
    path: Path,
    *,
    force: bool = False,
    detection: Detection | None = None,
    table: CapabilityTable | None = None,
) -> InitResult:
    """Write a config for this machine, or report what a rewrite would change.

    ``detection`` and ``table`` are injectable so the whole command can be
    exercised against machines nobody here owns.
    """
    found = detection if detection is not None else detect()
    capability = table if table is not None else load_table()
    proposal = propose(
        capability,
        vram_gb=found.largest_vram_gb,
        sources=_sources_for(found),
    )
    data = build(found, proposal)
    decisions = _decisions(found, proposal)
    limits = list(_limits(found, proposal))
    content = render(data, decisions)

    # Parse our own output. It normalizes the proposal the same way a loaded
    # config is normalized — without which a delta reports defaults the file
    # never mentioned as changes — and it means init cannot quietly emit
    # something the loader would reject.
    try:
        normalized: Mapping[str, Any] = parse_config(content).data
        loadable = True
    except ConfigError as exc:
        normalized = data
        loadable = False
        limits.insert(
            0,
            f"The generated file does not load yet: {exc} Bind a source and a "
            f"rung — the commented example at the top of the file shows the "
            f"shape.",
        )

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return InitResult(
            path=path,
            created=True,
            written=True,
            decisions=decisions,
            limits=tuple(limits),
            loadable=loadable,
            content=content,
        )

    deltas: tuple[Delta, ...]
    try:
        current = load_config(path)
    except ConfigError as exc:
        # A config that will not parse is still someone's file — and on a
        # machine with nothing reachable it is this command's own previous
        # output, incomplete by design. Either way there is no field-level
        # delta to show, so say which it is instead of inventing one, and
        # still refuse to overwrite without force.
        reason = str(exc).split(".")[0]
        deltas = (
            Delta(
                str(path), f"does not parse ({reason})", "a freshly generated config"
            ),
        )
    else:
        deltas = diff(current, normalized)

    if force:
        path.write_text(content, encoding="utf-8")
        return InitResult(
            path=path,
            created=False,
            written=True,
            deltas=deltas,
            decisions=decisions,
            limits=tuple(limits),
            loadable=loadable,
            content=content,
        )

    return InitResult(
        path=path,
        created=False,
        written=False,
        deltas=deltas,
        decisions=decisions,
        limits=tuple(limits),
        loadable=loadable,
        content=content,
    )
