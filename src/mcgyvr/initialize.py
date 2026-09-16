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
from mcgyvr.config import (
    BREADTH_FIELDS,
    CLEANUP_FIELDS,
    DELIVERY_FIELDS,
    FLEET_FILENAME,
    JOURNAL_FIELDS,
    POLICY_FILENAME,
    SCHEMA,
    Config,
    ConfigError,
    Field,
)
from mcgyvr.config import load as load_config
from mcgyvr.config import parse as parse_config
from mcgyvr.detect import DEFAULT_PROBE_TARGETS, Detection, detect, targets_for
from mcgyvr.propose import API, AvailableSource, Proposal, binding_name, propose

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
    loader's fail-loud rule exists to prevent (; ``mcgyvr.config``).
    """


class ApiSpecError(Exception):
    """A ``--api`` value does not say what a hosted unit is.

    Separate from :class:`InitError`, which means the machine had nothing to
    write a config from. This one means the operator's own words could not be
    read, and the remedy is to retype them rather than to change the machine.
    """


@dataclass(frozen=True)
class ApiUnit:
    """A hosted unit the operator asked for, by the unit's own schema keys.

    Three facts, spelled exactly as :data:`mcgyvr.config.UNIT_FIELDS` spells
    them, so the flag and the file it writes cannot drift into two
    vocabularies for one thing.

    ``api_key_env`` is the NAME of an environment variable, never a key. The
    value is not accepted here, not read here and never written: it is
    resolved at the moment of dispatch by :meth:`mcgyvr.pool.Endpoint.credential`,
    which is what keeps a secret out of this file, out of a repr and out of
    every error message that quotes an address.
    """

    model: str
    address: str
    api_key_env: str

    @property
    def name(self) -> str:
        """What the ladder calls this unit.

        Minted by the one function that names a tier, with the ``api``
        locality — so a hosted rung is named by the same rule as a local one,
        and the model segment is normalized into something that is safe as a
        YAML key a human edits.
        """
        return binding_name(self.model, locality=API)


#: What a ``--api`` value may say. They are the unit's own schema keys rather
#: than a second set of words for the same three facts.
API_SPEC_KEYS: tuple[str, ...] = ("model", "address", "api_key_env")


def parse_api_unit(spec: str) -> ApiUnit:
    """One ``--api`` value as an :class:`ApiUnit`, or a refusal saying why.

    The shape is ``key=value`` pairs separated by commas, which is the form
    this repository already passes named facts in (``mcgyvr.fleet.read``, the
    door's export lines). Every key is required and an unknown one is refused
    rather than ignored, for the reason the loader refuses an unknown config
    key: a value that is silently dropped is a setting the operator believes
    they made.
    """
    stated: dict[str, str] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        key, sep, value = part.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key or not value:
            raise ApiSpecError(
                f"--api: {part!r} is not `key=value`. A hosted unit is stated "
                f"as `{','.join(f'{k}=<{k}>' for k in API_SPEC_KEYS)}`."
            )
        if key not in API_SPEC_KEYS:
            raise ApiSpecError(
                f"--api: {key!r} is not something a hosted unit says. "
                f"Accepted: {', '.join(API_SPEC_KEYS)}."
            )
        if key in stated:
            raise ApiSpecError(
                f"--api: {key!r} is given twice in one unit. Repeat `--api` "
                f"to bind a second unit; a unit is one process at one address."
            )
        stated[key] = value

    missing = [key for key in API_SPEC_KEYS if key not in stated]
    if missing:
        raise ApiSpecError(
            f"--api: {', '.join(missing)} not given. A hosted unit needs all "
            f"of {', '.join(API_SPEC_KEYS)} — `model` is the id the provider "
            f"serves, `address` its base URL including scheme, and "
            f"`api_key_env` the NAME of the environment variable holding your "
            f"key, never the key itself."
        )
    return ApiUnit(
        model=stated["model"],
        address=stated["address"],
        api_key_env=stated["api_key_env"],
    )


def _api_setup_rejected(api_units: Sequence[ApiUnit], why: ConfigError) -> str:
    """A refusal for a setup that *was* asked for and still does not load.

    Distinct from :func:`_nothing_to_bind` because the situation is: the
    operator named units and the composition of them was rejected. Telling
    them "no local backend answered, start one" would send them to fix a
    machine that was never the problem.

    The values they typed are deliberately not echoed. One of them is the name
    of a credential variable, and a mistyped one is the case where somebody
    pasted the key itself — quoting it back would put a secret in a terminal
    and a scrollback, which is the whole hazard the `api_key_env` rule exists
    to end.
    """
    named = ", ".join(unit.name for unit in api_units)
    return (
        f"Refusing to write a config that cannot load.\n\n"
        f"`--api` asked for {len(api_units)} hosted unit(s) — {named} — and "
        f"the setup composed from them is not one the loader accepts.\n\n"
        f"The loader would reject it with: {why}\n\n"
        f"Check what `--api` was given: `model` is the id the provider "
        f"serves, `address` its base URL including scheme, and `api_key_env` "
        f"the NAME of the environment variable holding your key — never the "
        f"key itself."
    )


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
        f"{situation} With {vram}, no unit can be proposed, and a config "
        f"with no unit or no ladder dispatches nowhere.\n\n"
        f"The loader would reject it with: {why}\n\n"
        f"Fix one of these, then re-run:\n"
        f"  - start a local backend (llama-server, vLLM, LM Studio, "
        f"TGI) and re-run, or\n"
        f"  - name the rig that serves your models, if it is not this one\n"
        f"    (`mcgyvr init --host srv1 --host srv2`), or\n"
        f"  - bind a hosted API unit, which needs no GPU and no backend:\n\n"
        f"      mcgyvr init --api model=claude-opus-5,"
        f"address=https://api.anthropic.com,api_key_env=ANTHROPIC_API_KEY\n\n"
        f"    That writes the same two files any other init writes. "
        f"`api_key_env`\n"
        f"    names the environment variable holding your key; the key itself "
        f"is\n"
        f"    never written to either file.\n"
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


FLEET_FIELDS: tuple[Field, ...] = tuple(
    f for f in SCHEMA if f.name in ("profile", "units")
)
POLICY_FIELDS: tuple[Field, ...] = tuple(
    f for f in SCHEMA if f.name not in ("profile", "units")
)


def _header(title: str, decisions: Sequence[str] = ()) -> list[str]:
    lines = [
        f"# mcgyvr {title} — one of the two files that define a setup.",
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
    return lines


def render_fleet(data: Mapping[str, Any], decisions: Sequence[str] = ()) -> str:
    """Render ``fleet.yaml``: the profile and the units (what runs where)."""
    lines = _header(FLEET_FILENAME, decisions)
    lines.extend(_render_fields(FLEET_FIELDS, data, 0))
    return "\n".join(lines).rstrip("\n") + "\n"


def render_policy(data: Mapping[str, Any]) -> str:
    """Render ``policy.yaml``: the ladder and the policy over it."""
    lines = _header(POLICY_FILENAME)
    lines.extend(_render_fields(POLICY_FIELDS, data, 0))
    return "\n".join(lines).rstrip("\n") + "\n"


def render(data: Mapping[str, Any], decisions: Sequence[str] = ()) -> str:
    """Both files as one text, for a caller that wants the whole proposal."""
    return render_fleet(data, decisions) + "\n" + render_policy(data)


def _defaults(fields: Sequence[Field], *names: str) -> dict[str, Any]:
    """The schema's own default for each named key.

    `init` writes these keys out rather than leaving the renderer to show them
    commented, so the file says what the loader does. Restating the *value*
    here makes the file say what the loader used to do: `cleanup.enabled`
    drifted exactly that way and shipped repair-and-regate turned off against
    the ruling that turned it on. So a static key is read from the schema and
    never spelled twice — a moved default reaches a new install by moving.
    """
    by_name = {field.name: field for field in fields}
    return {name: by_name[name].default for name in names}


def build(
    detection: Detection,
    proposal: Proposal,
    *,
    api_units: Sequence[ApiUnit] = (),
) -> dict[str, Any]:
    """The fleet data implied by what was detected, proposed and asked for.

    A unit carries the whole fact: its address and engine, the model it
    serves, its width, and the room it needs on the card. There is no
    separate ``sources``/``models``/``tiers`` split to keep consistent — the
    unit is the one term.

    ``api_units`` are the hosted units the operator named on the command line.
    They are not detected and not proposed, because neither question applies:
    a hosted endpoint answers whether or not this machine has a card, and no
    capability measurement here describes it. They enter as units like any
    other, which is what makes the result the same two files any other init
    writes rather than a second kind of output.
    """
    backends = {backend.name: backend for backend in detection.backends}
    units: dict[str, Any] = {}
    for rung in proposal.rungs:
        backend = backends.get(rung.source)
        unit: dict[str, Any] = {
            "address": backend.base_url if backend is not None else "",
            "model": rung.model,
            "width": 1,
        }
        if backend is not None and backend.kind == "vllm":
            unit["engine"] = "vllm"
        unit["rig"] = backend.name if backend is not None else rung.source
        if rung.vram_gb:
            unit["room_mib"] = round(rung.vram_gb * 1024)
        units[rung.name] = unit
    for api in api_units:
        # The same whole fact, minus the two a hosted endpoint does not have:
        # no `rig`, because it is not a machine in your fleet, and no
        # `room_mib`, because it occupies no card of yours. `api_key_env` is a
        # variable NAME; the key is never held here.
        units[api.name] = {
            "address": api.address,
            "model": api.model,
            "api_key_env": api.api_key_env,
            "width": 1,
        }
    return {
        # Written at its default so the file says which setup it is. The
        # value is the schema's, never spelled here (see `_defaults`).
        **_defaults(SCHEMA, "profile", "max_escalations", "task_timeout_s"),
        "units": units,
        # Local rungs first, hosted ones last. A ladder is written
        # cheapest-first, and a rung is `api` exactly when its unit declares a
        # credential (`catalog.Catalog.family_of`) — so the hosted units are
        # the dear end of this ladder by the same rule that names the family.
        "ladder": [rung.name for rung in proposal.rungs]
        + [api.name for api in api_units],
        "fanout": "none",
        "orchestrator": {"unit": None, "model": None},
        "verifier": {"enabled": False, "unit": None, "model": None},
        "sandbox": {
            "mode": "docker" if detection.docker else "tempdir",
            "image": None,
            "setup": [],
        },
        "delivery": _defaults(DELIVERY_FIELDS, "mode"),
        # Written out at its default rather than left for the renderer to show
        # commented. An omitted key renders as `# draws:  # unset`, which is
        # true of the file and false of the behaviour: the loader fills 1 in.
        # A knob whose off position is a number is better read than inferred.
        "breadth": _defaults(BREADTH_FIELDS, "draws"),
        "cleanup": _defaults(CLEANUP_FIELDS, "enabled"),
        # Spelled out for the same reason: the journal is where a user's runs
        # are recorded, and a key they can see is a key they can move.
        "journal": _defaults(JOURNAL_FIELDS, "dir"),
    }


def _sources_for(detection: Detection) -> list[AvailableSource]:
    """Detected backends as proposal inputs.

    ``backend`` is the kind of server (``vllm``, ``llama-server``) and drives the
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


def _decisions(
    detection: Detection,
    proposal: Proposal,
    api_units: Sequence[ApiUnit] = (),
) -> tuple[str, ...]:
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
            f"Backend '{backend.name}' {where} at {backend.base_url} speaking "
            f"{backend.api}; {len(backend.models)} model(s) already pulled."
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
    for api in api_units:
        decisions.append(
            f"{api.name} -> {api.model} at {api.address}: bound because "
            f"`--api` asked for it, not because anything was detected. Its "
            f"key is read from ${api.api_key_env} at dispatch and is never "
            f"written to these files."
        )
    return tuple(decisions)


def _limits(
    detection: Detection,
    proposal: Proposal,
    api_units: Sequence[ApiUnit] = (),
) -> tuple[str, ...]:
    """What is NOT configured, and what that costs. Never silent.

    The proposal's own notes belong here rather than among the decisions:
    "no backend answered" and "needs a 9 GB pull" are both statements about
    what this install cannot do yet, not about what was chosen.
    """
    limits = list(detection.notes) + list(proposal.notes)
    if api_units:
        # What a bound API unit costs, said where every other cost is said.
        # The old note claimed no provider was configured, which stops being
        # true the moment `--api` binds one — and a limit that is false is
        # worse than no limit, because it is read as a checked fact.
        named = ", ".join(f"{u.name} (${u.api_key_env})" for u in api_units)
        limits.append(
            f"Hosted units are bound and every dispatch to one spends money: "
            f"{named}. Each needs its variable exported — `mcgyvr pool` skips "
            f"a rung whose variable is unset and says so. `orchestrator` and "
            f"`verifier` are still unbound; bind them and set "
            f"`verifier.enabled: true` to spend a hosted unit on those too."
        )
    else:
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


def _distinct_api_units(api_units: Sequence[ApiUnit]) -> tuple[ApiUnit, ...]:
    """The asked-for units, refusing two that would mint one name.

    Two units of the same model name the same rung, and a ladder cannot list a
    rung twice. The loader would catch it — but it would arrive as a schema
    complaint about a duplicate ladder entry, which describes the file rather
    than the mistake, so it is named here where the operator's own words still
    exist to point at.
    """
    seen: dict[str, ApiUnit] = {}
    for unit in api_units:
        clash = seen.get(unit.name)
        if clash is not None:
            raise InitError(
                f"--api names {unit.name!r} twice: model {clash.model!r} at "
                f"{clash.address} and model {unit.model!r} at {unit.address} "
                f"mint one unit name, and a ladder lists a rung once. Bind "
                f"one here and add the other by hand — after this run there "
                f"is a working file to add it to."
            )
        seen[unit.name] = unit
    return tuple(seen.values())


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
    api_units: Sequence[ApiUnit] = (),
) -> InitResult:
    """Write a config for this install, or report what a rewrite would change.

    ``detection`` and ``table`` are injectable so the whole command can be
    exercised against machines nobody here owns.

    ``hosts`` names the machines to sweep for backends; empty means this one.
    It is ignored when ``detection`` is supplied, because the caller has then
    already decided what was found — honouring both would be two answers to
    one question, and the network one would win a test that meant to stay
    offline.

    ``api_units`` are hosted units the operator asked for. They are additive
    to whatever was detected rather than a mode: a machine with a local
    backend and a key gets both, in one ladder, which is the escalation this
    product exists to run. A machine with neither still refuses — an empty
    ladder is refused by the self-parse below, exactly as it always was, and
    nothing here special-cases around that check.
    """
    found = (
        detection
        if detection is not None
        else detect(targets_for(hosts) if hosts else DEFAULT_PROBE_TARGETS)
    )
    asked = _distinct_api_units(api_units)
    capability = table if table is not None else load_table()
    proposal = propose(
        capability,
        vram_gb=found.largest_vram_gb,
        sources=_sources_for(found),
    )
    data = build(found, proposal, api_units=asked)
    decisions = _decisions(found, proposal, asked)
    limits = _limits(found, proposal, asked)
    fleet_content = render_fleet(data, decisions)
    policy_content = render_policy(data)

    # Parse our own output before anything is written. It normalizes the
    # proposal the same way a loaded config is normalized, and it makes it
    # impossible for init to emit files the loader rejects.
    try:
        normalized: Mapping[str, Any] = parse_config(
            fleet_content, policy_content, path=path
        ).data
    except ConfigError as exc:
        # Two refusals, because they are two situations with two remedies. If
        # units were asked for, the machine was never the problem and saying
        # "start a local backend" would send someone to fix the wrong thing.
        if asked:
            raise InitError(_api_setup_rejected(asked, exc)) from exc
        raise InitError(_nothing_to_bind(found, exc)) from exc

    fleet_path = path / FLEET_FILENAME
    policy_path = path / POLICY_FILENAME
    content = fleet_content + "\n" + policy_content

    if not fleet_path.exists() and not policy_path.exists():
        path.mkdir(parents=True, exist_ok=True)
        fleet_path.write_text(fleet_content, encoding="utf-8")
        policy_path.write_text(policy_content, encoding="utf-8")
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
        # A setup that will not parse is still someone's files, and still
        # refuses to be overwritten without force.
        reason = str(exc).split(".")[0]
        deltas = (
            Delta(str(path), f"does not parse ({reason})", "a freshly generated setup"),
        )
    else:
        deltas = diff(current, normalized)

    if force:
        path.mkdir(parents=True, exist_ok=True)
        fleet_path.write_text(fleet_content, encoding="utf-8")
        policy_path.write_text(policy_content, encoding="utf-8")
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
