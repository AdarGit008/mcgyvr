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
3. **Honest about what is missing.** No API key and no Docker are both
   supported, and each is reported with what it costs rather than quietly
   degraded. Nothing to dispatch to is NOT supported: rather than write a
   config that cannot load, init refuses and says what to bind. A file that
   dispatches nowhere is not a head start — it is a misconfiguration that
   surfaces later and further from its cause.

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
from mcgyvr.detect import DEFAULT_PROBE_TARGETS, Detection, detect, targets_for
from mcgyvr.propose import AvailableSource, Proposal, propose

COMMENT_WIDTH = 78

# A YAML scalar is safe bare only if it cannot be read as anything else. A
# model id like `qwen2.5-coder:7b` carries a colon and a URL carries both a
# colon and slashes, so most values here need quoting.
_BARE_SAFE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")
_RESERVED = frozenset({"true", "false", "null", "yes", "no", "on", "off", "~"})


class InitError(Exception):
    """There is nothing to write a working config from.

    Raised instead of writing a config that cannot load. A file that
    dispatches nowhere is not a head start — it is a misconfiguration that
    surfaces later and further from its cause, which is exactly what the
    loader's fail-loud rule exists to prevent (ADR-0001; ``mcgyvr.config``).
    """


def _nothing_to_bind(detection: Detection, why: ConfigError) -> str:
    """Say what was tried, what is missing, and what to do about it."""
    if detection.backends:
        found = ", ".join(f"{b.name} at {b.base_url}" for b in detection.backends)
        situation = (
            f"Reachable backends: {found} — but nothing in the capability "
            f"table can be bound to them, and none of them reports holding a "
            f"measured model."
        )
    else:
        situation = "No local backend answered on any default endpoint."

    vram = (
        f"{detection.largest_vram_gb:g} GB of VRAM"
        if detection.largest_vram_gb is not None
        else "no GPU this build can see"
    )
    return (
        f"Refusing to write a config that cannot load.\n\n"
        f"{situation} With {vram}, no rung can be proposed, and a config "
        f"with no source or no rung dispatches nowhere.\n\n"
        f"The loader would reject it with: {why}\n\n"
        f"Fix one of these, then re-run:\n"
        f"  - start a local backend (ollama, llama-server, vLLM, LM Studio, "
        f"TGI) and re-run, or\n"
        f"  - name the rig that serves your models, if it is not this one\n"
        f"    (`mcgyvr init --host srv1 --host srv2`), or\n"
        f"  - write the file by hand and bind an API source:\n\n"
        f"      version: 1\n"
        f"      sources:\n"
        f"        anthropic:\n"
        f'          base_url: "https://api.anthropic.com"\n'
        f"          api: openai\n"
        f"          api_key_env: ANTHROPIC_API_KEY\n"
        f"      ladder:\n"
        f"        tiers:\n"
        f"          - name: api_claude-opus-5\n"
        f"            source: anthropic\n"
        f"            model: claude-opus-5\n"
    )


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
    lines.append("")
    lines.extend(_render_fields(SCHEMA, data, 0))
    text = "\n".join(lines).rstrip("\n")
    return text + "\n"


def build(detection: Detection, proposal: Proposal) -> dict[str, Any]:
    """The config data implied by what was detected and proposed."""
    sources = {
        backend.name: {
            "base_url": backend.base_url,
            # How work will be DISPATCHED, which is not always how the backend
            # was ASKED what it holds. For Ollama they differ on purpose: the
            # native path enumerates pulled models but is the one CAV-01
            # measured at 32.3% against a true 84.1% (#164).
            "api": backend.binds_as,
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
        "delivery": {"mode": "branch", "token_env": None},
        "budgets": {"max_escalations": 1, "task_timeout_s": 900},
        # Written out at its default rather than left for the renderer to show
        # commented. An omitted key renders as `# draws:  # unset`, which is
        # true of the file and false of the behaviour: the loader fills 1 in.
        # A knob whose off position is a number is better read than inferred.
        "breadth": {"draws": 1},
    }


def _sources_for(detection: Detection) -> list[AvailableSource]:
    """Detected backends as proposal inputs.

    ``backend`` is the kind of server (``ollama``, ``vllm``) and drives the
    table's ``requires_backend`` check; ``name`` is what the source will be
    called in the config, which for a multi-host sweep is qualified with the
    machine. They are the same string on a single-host sweep and must not be
    conflated: qualifying a name is a config concern, and matching a backend
    requirement is a capability one.
    """
    return [
        AvailableSource(
            name=backend.name,
            backend=backend.kind,
            models_present=frozenset(backend.models),
            host=backend.host,
        )
        for backend in detection.backends
    ]


def _decisions(detection: Detection, proposal: Proposal) -> tuple[str, ...]:
    decisions: list[str] = []
    if detection.gpus:
        gpu = detection.gpus[0]
        scope = (
            " — this machine's card, which is not what the remote rungs below run on"
            if detection.has_remote_backend
            else ""
        )
        decisions.append(
            f"GPU {gpu.name} with {gpu.vram_gb:g} GB, via {gpu.how}{scope}."
        )
    for backend in detection.backends:
        where = "here" if backend.is_local else f"on {backend.host}"
        decisions.append(
            f"Source '{backend.name}' {where} at {backend.base_url} speaking "
            f"{backend.binds_as}; {len(backend.models)} model(s) already pulled."
        )
        if backend.bound_on_another_protocol:
            decisions.append(
                f"  '{backend.name}' answered as {backend.api} but is bound as "
                f"{backend.binds_as}: the same port serves both, with the same "
                f"model ids. CAV-01 measured the native path scoring "
                f"qwen2.5-coder:7b at 32.3% against a true 84.1%, so work "
                f"dispatched on it carries a quality caveat and cannot serve a "
                f"measurement at all. Detection still asks natively, because "
                f"that is the only listing that includes models pulled but not "
                f"loaded."
            )
    for rung in proposal.rungs:
        presence = (
            "already pulled"
            if rung.already_present
            else f"needs a ~{rung.weights_gb:g} GB pull"
        )
        machine = f" on {rung.host}" if rung.host else ""
        decisions.append(
            f"{rung.name} -> {rung.model} on {rung.source}{machine}: "
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
    hosts: Sequence[str] = (),
) -> InitResult:
    """Write a config for this install, or report what a rewrite would change.

    ``detection`` and ``table`` are injectable so the whole command can be
    exercised against machines nobody here owns.

    ``hosts`` names the machines to sweep for backends; empty means this one.
    It is ignored when ``detection`` is supplied, because the caller has then
    already decided what was found — honouring both would be two answers to
    one question, and the network one would win a test that meant to stay
    offline.
    """
    found = (
        detection
        if detection is not None
        else detect(targets_for(hosts) if hosts else DEFAULT_PROBE_TARGETS)
    )
    capability = table if table is not None else load_table()
    proposal = propose(
        capability,
        vram_gb=found.largest_vram_gb,
        sources=_sources_for(found),
    )
    data = build(found, proposal)
    decisions = _decisions(found, proposal)
    limits = _limits(found, proposal)
    content = render(data, decisions)

    # Parse our own output before anything is written. It normalizes the
    # proposal the same way a loaded config is normalized — without which a
    # delta reports defaults the file never mentioned as changes — and it is
    # what makes it impossible for init to emit a config the loader rejects.
    try:
        normalized: Mapping[str, Any] = parse_config(content).data
    except ConfigError as exc:
        raise InitError(_nothing_to_bind(found, exc)) from exc

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return InitResult(
            path=path,
            created=True,
            written=True,
            decisions=decisions,
            limits=limits,
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
            limits=limits,
            content=content,
        )

    return InitResult(
        path=path,
        created=False,
        written=False,
        deltas=deltas,
        decisions=decisions,
        limits=limits,
        content=content,
    )
