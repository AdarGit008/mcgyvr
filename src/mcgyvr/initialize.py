"""Write a setup — fleet.yaml and policy.yaml — from what this machine runs.

`initialize` detects the machine (cards, local model servers, whether a Docker
daemon answers), asks `propose` for one rung per model a running server lists,
and turns that into the two config files the loader validates. Every value it
writes is measured, the schema's default, or stated on the command line; no
estimate is matched to a listed model, which is why `NO_ESTIMATE_NOTICE` and
`LISTED_ORDER_NOTICE` say so inside the written file.

The rendering half (`render_fleet`, `render_policy`) writes the YAML text by
hand, commenting every leaf from the same `Field` schema the loader validates
against, so a comment cannot drift from what is enforced. The result is parsed
back with `parse_config` before anything is written: a setup the loader would
refuse raises `InitError` carrying the loader's objection and the ways out.

An existing setup is never replaced silently. Without `force`, `initialize`
reports the `Delta` between the file on disk and the one it would write and
leaves both files alone.
"""

from __future__ import annotations

import re
import textwrap
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from mcgyvr import hostos
from mcgyvr.compose import Recommendation, endpoint_for_backend, recommend
from mcgyvr.config import (
    API_OUTPUT_TOKENS,
    BREADTH_FIELDS,
    CLEANUP_FIELDS,
    DELIVERY_FIELDS,
    FLEET_FILENAME,
    GATE_FIELDS,
    JEV_FIELDS,
    JOURNAL_FIELDS,
    LAUNCHER_NATIVE,
    LOCAL_ONLY,
    MCGYVR_CODE,
    ORCHESTRATOR_FIELDS,
    POLICY_FILENAME,
    SANDBOX_FIELDS,
    SCHEMA,
    VERIFIER_UNIT_FIELDS,
    Config,
    ConfigError,
    Field,
    default_launcher,
    local_orchestrator,
)
from mcgyvr.config import load as load_config
from mcgyvr.config import parse as parse_config
from mcgyvr.decision import DecisionError
from mcgyvr.detect import (
    DEFAULT_PROBE_TARGETS,
    PORT_CONVENTIONS,
    Detection,
    detect,
    is_local_host,
    targets_for,
)
from mcgyvr.propose import API, AvailableSource, Proposal, binding_name, propose
from mcgyvr.runner import RunnerError

if TYPE_CHECKING:
    from mcgyvr.local_pool import Endpoint

COMMENT_WIDTH = 78

#: Said in a setup that binds listed models: init knows only what a server
#: listed, so there is no estimate behind a unit's size. The notice states that
#: a unit is sized from the shipped table only when its model name equals a row,
#: and that anything declared for the unit in fleet.yaml wins over that row.
NO_ESTIMATE_NOTICE = (
    "No estimate was matched to a unit bound from a server's listing: mcgyvr "
    "cannot yet match an estimate to a model by its weights. Until it can, "
    "`mcgyvr emit` sizes a unit whose model name equals a row of the shipped "
    "table from that row. What you declare for a unit in fleet.yaml, for "
    "example under `launch` or as `room_mib`, wins over that row."
)

#: Said when the ladder has rungs: init orders them by where it found them —
#: `--host` order, then the fixed probe order of `PORT_CONVENTIONS`, then each
#: server's own listing order — and the notice says that this is discovery
#: order, no judgement of cost or quality, and that policy.yaml sets the climb.
LISTED_ORDER_NOTICE = (
    "The ladder is written in the order init found the models: the machines "
    "in the order `--host` named them (this one when none was named), then on "
    "each machine the server programs in mcgyvr's fixed probe order ("
    + ", ".join(kind for kind, _, _ in PORT_CONVENTIONS)
    + "), then each server's own listing order; a unit named with `--api` "
    "comes after them. None of these judges cost or quality. A ladder is "
    "climbed cheapest first, and that order is yours to set in policy.yaml."
)

#: The words `mcgyvr setup --priority` accepts. A priority is handed to the Jev
#: decision as the state it chooses under; it does not order the ladder, which
#: policy.yaml sets.
PRIORITIES = ("throughput", "quality", "cost")

# `_scalar` writes a string bare only when it matches this and is not one of
# the words below, which YAML reads as booleans or null rather than as text.
# Anything else is double-quoted, with backslashes and quotes escaped.
_BARE_SAFE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")
_RESERVED = frozenset({"true", "false", "null", "yes", "no", "on", "off", "~"})


class InitError(Exception):
    """What init refuses: a flag naming a unit it does not write, or a setup the
    loader would not accept. The message says what is wrong and what to do
    instead."""


class ApiSpecError(Exception):
    """`--api` could not be read. The message names the part that is wrong and
    spells what a hosted unit may say."""


#: The `key=value` fields one `--api` unit must state, in the order the error
#: messages and the usage example list them.
API_SPEC_KEYS: tuple[str, ...] = ("model", "address", "api_key_env")

#: The one field `--api` accepts and does not require.
API_SPEC_OPTIONAL_KEYS: tuple[str, ...] = ("output_tokens",)


@dataclass(frozen=True)
class ApiUnit:
    """One hosted unit an `--api` spec asked to bind: the model id the provider
    serves, the base URL it is reached at, and the name of the environment
    variable holding the key — never the key. `output_tokens` is the room its
    replies are given, defaulting to `API_OUTPUT_TOKENS`."""

    model: str
    address: str
    api_key_env: str
    output_tokens: int = API_OUTPUT_TOKENS

    @property
    def name(self) -> str:
        """The unit name this spec is written under in both files:
        `binding_name` of the model id, prefixed `api` because nothing detected
        it."""
        return binding_name(self.model, locality=API)


def parse_api_unit(spec: str) -> ApiUnit:
    """Read one `--api` unit from its comma-separated `key=value` text.

    Every key in `API_SPEC_KEYS` is required exactly once, plus at most one
    `API_SPEC_OPTIONAL_KEYS` key; a repeated key is refused, since binding two
    units takes two `--api` flags. `output_tokens`, when given, must be a whole
    number of at least 1. Each failure is an `ApiSpecError` naming the part of
    the spec that is wrong."""
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
        if key not in API_SPEC_KEYS + API_SPEC_OPTIONAL_KEYS:
            raise ApiSpecError(
                f"--api: {key!r} is not something a hosted unit says. "
                f"Accepted: {', '.join(API_SPEC_KEYS + API_SPEC_OPTIONAL_KEYS)}."
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
    room = stated.get("output_tokens")
    if room is not None and not (room.isdigit() and int(room) >= 1):
        raise ApiSpecError(
            f"--api: output_tokens={room!r} is not a whole number of at least "
            f"1. It is the room the unit's replies are given — the `max_tokens` "
            f"its provider is sent — e.g. `output_tokens=16384`."
        )
    return ApiUnit(
        model=stated["model"],
        address=stated["address"],
        api_key_env=stated["api_key_env"],
        **({"output_tokens": int(room)} if room is not None else {}),
    )


def _api_setup_rejected(api_units: Sequence[ApiUnit], why: ConfigError) -> str:
    """The refusal when the setup composed from `--api` is one the loader will
    not accept: how many hosted units were asked for, which ones, what the
    loader said, and what `--api` must carry — the served model id, its base
    URL with scheme, and the name of the variable holding the key."""
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


def _listing(names: Sequence[str]) -> str:
    """The names as running prose: `a`, `a and b`, `a, b and c`."""
    if len(names) < 2:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _these_cards(detection: Detection) -> str:
    """This machine's cards, for a refusal to explain.

    Only local cards are read, so it names the remote hosts it did not look at;
    then either that this machine has no card the build can see, or each card
    with the memory size detection read."""
    remote = [
        host
        for host in dict.fromkeys(target.host for target in detection.swept)
        if not is_local_host(host)
    ]
    if remote:
        unread = f"the cards of {_listing(remote)} are not read from here"
    else:
        unread = "a rig named with `--host` is not read from here"
    if not detection.gpus:
        return (
            f"This machine, the one running mcgyvr ({unread}), has no GPU "
            f"this build can see."
        )
    cards = "; ".join(f"{gpu.name}, {gpu.size}" for gpu in detection.gpus)
    return f"This machine's GPUs (the machine running mcgyvr; {unread}): {cards}."


def _nothing_to_bind(detection: Detection, why: ConfigError, proposal: Proposal) -> str:
    """The refusal when the composed setup binds nothing and `--api` was not
    asked for.

    It states what was reached and why nothing was bound — no server answered,
    or none lists a model init can bind — how much of the card could be read,
    what the loader said, and the ways out: bind a unit by hand with the
    `room_mib` it needs, start a backend, load a model, name another rig with
    `--host`, or bind a hosted unit with `--api`."""
    local = [b for b in detection.backends if b.is_local]
    binds = "init binds only a model a running server lists."
    nothing = f"there is nothing to bind: {binds}"
    if detection.backends:
        found = ", ".join(f"{b.name} at {b.base_url}" for b in detection.backends)
        if proposal.rejected:
            situation = (
                f"Reachable model servers: {found} — but none of them lists a "
                f"model init can bind: " + " ".join(r.reason for r in proposal.rejected)
            )
        else:
            situation = (
                f"Reachable model servers: {found} — but none of them lists a model."
            )
        situation += f" So {nothing}"
    elif detection.swept:
        tried = ", ".join(target.base_url for target in detection.swept)
        situation = (
            f"No model server answered on any endpoint tried ({tried}), so {nothing}"
        )
    else:
        situation = f"No model server answered, so {nothing}"

    unsized = [gpu.name for gpu in detection.gpus if gpu.vram_gb is None]
    if len(unsized) == 1:
        cause = f"the memory size of {unsized[0]} was not determined, and {binds}"
    elif unsized:
        cause = (
            f"the memory sizes of {_listing(unsized)} were not determined, and {binds}"
        )
    elif not detection.gpus and local:
        cause = f"there is no GPU this build can see, and {binds}"
    else:
        cause = ""
    by_hand = ""
    if cause:
        text = (
            f"bind a unit by hand: {cause} A unit in fleet.yaml under `units` "
            f"states its `address`, the `model` it serves and `room_mib`, the "
            f"card room it needs in MiB, measured or stated; `ladder` in "
            f"policy.yaml names it, or"
        )
        lines = textwrap.wrap(text, width=70)
        by_hand = "  - " + "\n    ".join(lines) + "\n"
    start = (
        ""
        if local
        else (
            "  - start a local backend (llama-server, vLLM, LM Studio, "
            "TGI) and re-run, or\n"
        )
    )
    load = (
        "  - load a model into a server named above and re-run, or\n"
        if detection.backends
        else ""
    )
    return (
        f"Refusing to write a config that cannot load.\n\n"
        f"{situation} A config with no unit or no "
        f"ladder dispatches nowhere.\n\n"
        f"{_these_cards(detection)}\n\n"
        f"The loader would reject it with: {why}\n\n"
        f"Fix one of these:\n"
        f"{by_hand}{start}{load}"
        f"  - name the rig that serves your models, if it is not this one\n"
        f"    (`mcgyvr setup --host <name>`), or\n"
        f"  - bind a hosted API unit, which needs no GPU and no backend:\n\n"
        f"      mcgyvr setup --api model=claude-opus-5,"
        f"address=https://api.anthropic.com,api_key_env=ANTHROPIC_API_KEY\n\n"
        f"    That writes the same two files any other init writes. "
        f"`api_key_env`\n"
        f"    names the environment variable holding your key; the key itself "
        f"is\n"
        f"    never written to either file.\n\n"
        f"`mcgyvr capabilities` lists the shipped estimates.\n"
    )


@dataclass(frozen=True)
class Delta:
    """One key that differs between the setup on disk and the one proposed: the
    dotted path, the value there now and the value init would write. `str` gives
    it as one line, and a side that has no such key shows as `(unset)`."""

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


def _render_leaf(spec: Field, value: Any, indent: int, note: str = "") -> list[str]:
    pad = " " * indent
    lines = _comment(spec.doc, indent)
    if note:
        # The schema's own comment first, then the reason this key is worth
        # noting on this machine, so a note adds to a field rather than replace
        # what it says.
        lines.extend(_comment(note, indent))
    if value is None or value == [] or (spec.kind == "mapping" and not value):
        # An unset key is written as a commented-out line carrying the schema's
        # bind hint, so nothing pretends to be set and the hint sits beside it.
        hint = spec.bind_hint or "unset"
        lines.append(f"{pad}# {spec.name}:  # {hint}")
        return lines
    if spec.kind == "mapping":
        # A free-form mapping (a unit's `launch`) is written whole as YAML, its
        # keys sorted and nested one step under the key.
        dumped = yaml.safe_dump(dict(value), sort_keys=True, width=200)
        lines.append(f"{pad}{spec.name}:")
        lines.extend(
            f"{pad}  {line}" if line else ""
            for line in dumped.rstrip("\n").splitlines()
        )
        return lines
    if spec.kind == "str_list":
        lines.append(f"{pad}{spec.name}:")
        lines.extend(f"{pad}  - {_scalar(item)}" for item in value)
        return lines
    lines.append(f"{pad}{spec.name}: {_scalar(value)}")
    return lines


def _render_fields(
    fields: Sequence[Field],
    data: Mapping[str, Any],
    indent: int,
    notes: Mapping[str, str] | None = None,
    prefix: str = "",
) -> list[str]:
    lines: list[str] = []
    for spec in fields:
        value = data.get(spec.name)
        if spec.kind == "block":
            lines.extend(_comment(spec.doc, indent))
            lines.append(f"{' ' * indent}{spec.name}:")
            lines.extend(
                _render_fields(
                    spec.block, value or {}, indent + 2, notes, f"{prefix}{spec.name}."
                )
            )
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
            note = (notes or {}).get(f"{prefix}{spec.name}", "")
            lines.extend(_render_leaf(spec, value, indent, note))
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


FLEET_FIELDS: tuple[Field, ...] = tuple(f for f in SCHEMA if f.name == "units")
#: The schema split across the two files: fleet.yaml is the `units` block, and
#: policy.yaml is every other field except `relief`, which the loader derives.
POLICY_FIELDS: tuple[Field, ...] = tuple(
    f for f in SCHEMA if f.name not in ("units", "relief")
)


def _header(title: str, decisions: Sequence[str] = ()) -> list[str]:
    lines = [
        f"# mcgyvr {title} — one of the two files that define a setup.",
        "#",
        "# Generated by `mcgyvr setup`, and safe to edit by hand: re-running",
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
    """The whole fleet.yaml: the shared header carrying what init decided, then
    the `units` block of the schema, commented from it."""
    lines = _header(FLEET_FILENAME, decisions)
    lines.extend(_render_fields(FLEET_FIELDS, data, 0))
    return "\n".join(lines).rstrip("\n") + "\n"


#: The extra comment `render_policy` puts on `sandbox.mode` when no daemon answered.
NO_DAEMON_MODE_NOTE = (
    "No Docker daemon answered when init ran, so this is `tempdir`: the "
    "explicitly weaker mode, in which a contract's acceptance commands run on "
    "this machine rather than in a container. Once Docker runs here, set "
    "`mode: docker` to run each task in its own container."
)


def render_policy(
    data: Mapping[str, Any], notes: Mapping[str, str] | None = None
) -> str:
    """The whole policy.yaml: the shared header without decisions, then every
    schema field that is not `units` or `relief`. `notes` adds comment text under
    a dotted key such as `sandbox.mode`."""
    lines = _header(POLICY_FILENAME)
    lines.extend(_render_fields(POLICY_FIELDS, data, 0, notes))
    return "\n".join(lines).rstrip("\n") + "\n"


def _policy_notes(detection: Detection, data: Mapping[str, Any]) -> dict[str, str]:
    """Extra comment text per dotted field, for what the schema cannot say on its
    own: when no Docker daemon answered, `sandbox.mode` gets the note saying
    what that leaves you with."""
    sandbox = data.get("sandbox") or {}
    notes: dict[str, str] = {}
    if not detection.docker and sandbox.get("mode") == "tempdir":
        notes["sandbox.mode"] = NO_DAEMON_MODE_NOTE
    return notes


def render(data: Mapping[str, Any], decisions: Sequence[str] = ()) -> str:
    """Both files as one string, fleet.yaml first, separated by a blank line."""
    return render_fleet(data, decisions) + "\n" + render_policy(data)


def _defaults(fields: Sequence[Field], *names: str) -> dict[str, Any]:
    """The schema's `default` for each named field, as a fresh dict."""
    by_name = {field.name: field for field in fields}
    return {name: by_name[name].default for name in names}


def _deployment_default(use_case: str) -> str:
    """The deployment written when none was asked for: `hybrid`, printed without
    consulting the use case. `local-only` is written only when `--deployment`
    names it."""
    return "hybrid"


def _rig_name(backend: Any, fallback: str) -> str:
    """The `rig` a bound unit is written with: the fallback when no backend
    answered for the rung, `localhost` for a local backend, its host otherwise."""
    if backend is None:
        return fallback
    return "localhost" if backend.is_local else backend.host


def build(
    detection: Detection,
    proposal: Proposal,
    *,
    api_units: Sequence[ApiUnit] = (),
    use_case: str = MCGYVR_CODE,
    deployment: str | None = None,
) -> dict[str, Any]:
    """Turn a detection and a proposal into the data both files render from.

    One unit per proposed rung — its address, the model the source listed, and
    `width: 1` — plus the served window and the `vllm` engine where the backend
    gave them. Then one unit per `--api` spec, whose key is named by variable.
    The ladder is the rung names in proposal order followed by the hosted units;
    `fanout` is `none`, review keeps the schema's `enabled`, the orchestrator,
    verifier and Jev blocks stay unbound, and the sandbox mode follows whether a
    Docker daemon answered. `deployment` falls back to `_deployment_default`."""
    backends = {backend.name: backend for backend in detection.backends}
    units: dict[str, Any] = {}
    for rung in proposal.rungs:
        backend = backends.get(rung.source)
        unit: dict[str, Any] = {
            "address": backend.base_url if backend is not None else "",
            "model": rung.model,
            "width": 1,
        }
        if backend is not None and backend.window is not None:
            # The window is the context length the backend reported serving, and
            # it is written only when the server stated one: a guessed ceiling is
            # worse than none. A `code` contract's cap is held to this unit's
            # ceiling, so an absent window narrows what can be dispatched here.
            unit["window"] = backend.window
        if backend is not None and backend.kind == "vllm":
            unit["engine"] = "vllm"
        if backend is not None and (
            default_launcher(
                local=is_local_host(backend.host),
                engine=unit.get("engine"),
                system=hostos.os_name(),
            )
            == LAUNCHER_NATIVE
        ):
            # A llama.cpp unit on this macOS or Windows machine runs as the
            # pinned native build; a container there reaches no GPU.
            unit["launcher"] = LAUNCHER_NATIVE
        unit["rig"] = _rig_name(backend, rung.source)
        units[rung.name] = unit
    for api in api_units:
        # A hosted unit is written exactly as `--api` stated it — the address,
        # the served model and the variable naming the key — because nothing was
        # detected for it.
        units[api.name] = {
            "address": api.address,
            "model": api.model,
            "api_key_env": api.api_key_env,
            "width": 1,
            # The reply room is a declared number, not a measured one, so a
            # `code` contract dispatched here is held to it.
            "output_tokens": api.output_tokens,
        }
    ordered_api_units = tuple(api_units)
    return {
        # Installation-wide numbers keep the schema's defaults, so the file says
        # what the loader would assume anyway instead of inventing a value.
        **_defaults(SCHEMA, "max_escalations", "task_timeout_s", "users"),
        # The use case and deployment are what was asked for — `--use-case` and
        # `--deployment` — and they govern what the rest of the file may say.
        "use_case": use_case,
        "deployment": (
            deployment if deployment is not None else _deployment_default(use_case)
        ),
        "units": units,
        # The ladder lists units in the order init found them: the proposal's
        # rungs, then the units `--api` stated. Nothing here judges cost or
        # quality; `LISTED_ORDER_NOTICE` says so in the header, and the order to
        # climb in is set in policy.yaml.
        "ladder": [rung.name for rung in proposal.rungs]
        + [api.name for api in ordered_api_units],
        "fanout": "none",
        # The switches of the stages a batch is ordered by keep the schema's
        # defaults, written out so the one file shows every switch.
        **_defaults(SCHEMA, "infer_dependencies", "same_file"),
        # No orchestrator unit is bound: `orchestrator.type` keeps the schema's
        # default, and a unit is named only when a person names one.
        "orchestrator": {
            **_defaults(ORCHESTRATOR_FIELDS, "type"),
            "unit": None,
            "model": None,
        },
        # Review is on by default and no unit is named, so each rung's work is
        # reviewed by the next dearer local rung serving another model.
        "verifier": {
            **_defaults(VERIFIER_UNIT_FIELDS, "enabled"),
            "unit": None,
            "model": None,
        },
        # The Jev block stays empty unless `--jev` names the unit every typed
        # decision should ask.
        "jev": {**_defaults(JEV_FIELDS, "enabled"), "unit": None, "model": None},
        "sandbox": {
            "mode": "docker" if detection.docker else "tempdir",
            # `mode` follows the machine — `docker` when the daemon answered,
            # `tempdir` when it did not, and `_policy_notes` then says what that
            # mode means. `network` and `allow_fallback` keep their
            # defaults, no image is named and no setup command runs, so the image
            # is whatever the detected stack needs.
            **_defaults(SANDBOX_FIELDS, "allow_fallback", "network"),
            "image": None,
            "setup": [],
        },
        # Delivery keeps the schema's default, `commit: false`, and names no
        # branch, so accepted work stays in the workspace on the branch you have
        # checked out until `run --commit` asks for a commit.
        "delivery": {**_defaults(DELIVERY_FIELDS, "commit"), "branch": None},
        # Breadth keeps the schema's `draws`, so a unit is asked once, and no
        # temperature is stated; cleanup keeps its default too. Init measures none
        # of these, so it invents none of them — a person sets them by hand.
        "breadth": _defaults(BREADTH_FIELDS, "draws"),
        "cleanup": _defaults(CLEANUP_FIELDS, "enabled"),
        # The gate keeps the schema's `enabled` and `param_mutation`, `refuse`
        # included, so init states no gate policy nobody stated.
        "gate": _defaults(GATE_FIELDS, "enabled", "param_mutation"),
        # The journal is written where the schema's default `dir` puts it, under
        # this user's state directory rather than inside any repository.
        "journal": _defaults(JOURNAL_FIELDS, "dir"),
    }


def _opt_ins(data: dict[str, Any], *, jev: str | None) -> dict[str, Any]:
    """Apply `--jev` to the built data.

    The flag must name a unit this init writes, or `InitError` lists the ones it
    does. `--jev` binds the Jev block to that unit."""
    if jev is None:
        return data
    if jev not in data["units"]:
        raise InitError(
            f"--jev {jev!r} names no unit this init writes. The units are: "
            f"{', '.join(sorted(data['units']))}."
        )
    data["jev"] = {**data.get("jev", {}), "unit": jev, "model": None}
    return data


def _opt_in_decisions(*, jev: str | None) -> tuple[str, ...]:
    said: tuple[str, ...] = ()
    if jev is not None:
        said += (
            f"Jev unit {jev!r} dedicated: every typed decision asks it, and it is "
            "never slept or woken.",
        )
    return said


def unit_names(detection: Detection) -> tuple[str, ...]:
    """The unit names a proposal over this detection would bind, so a caller can
    offer them as choices before anything is written."""
    return tuple(rung.name for rung in propose(sources=_sources_for(detection)).rungs)


def _sources_for(detection: Detection) -> list[AvailableSource]:
    """The detection's backends as `propose` sees them: one available source per
    backend, carrying the model ids it listed and the host it runs on."""
    return [
        AvailableSource(
            name=backend.name,
            backend=backend.kind,
            models_present=tuple(backend.models),
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
    backends = {backend.name: backend for backend in detection.backends}
    remote = False
    for rung in proposal.rungs:
        backend = backends.get(rung.source)
        remote = remote or (backend is not None and not backend.is_local)
    scope = (
        " — this machine's card, which is not what the remote rungs below run on"
        if remote
        else ""
    )
    # Each card is stated with the size detection read and how it read it, and
    # the scope says that a remote rung runs on a card other than this one.
    for gpu in detection.gpus:
        decisions.append(f"GPU {gpu.name} with {gpu.size}, via {gpu.how}{scope}.")
    for backend in detection.backends:
        where = "here" if backend.is_local else f"on {backend.host}"
        decisions.append(
            f"Backend '{backend.name}' {where} at {backend.base_url} speaking "
            f"{backend.api}; {len(backend.models)} model(s) listed."
        )
    for rung in proposal.rungs:
        backend = backends.get(rung.source)
        address = backend.base_url if backend is not None else rung.source
        decisions.append(
            f"{rung.name} -> {rung.model} at {address}: bound because "
            f"{rung.source} lists it; no estimate was matched to it."
        )
    if proposal.rungs:
        decisions.append(NO_ESTIMATE_NOTICE)
        decisions.append(LISTED_ORDER_NOTICE)
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
    """What the written setup cannot do, said plainly.

    Detection and proposal notes come through as they are; a rung whose served
    window could not be read gets the note saying a code dispatch to it refuses;
    the hosted case gets the note about spend, review and the unbound
    orchestrator, and the local case the note about which rung reviews which; and
    with no Docker daemon the tempdir note is added."""
    limits = list(detection.notes) + list(proposal.notes)
    backends = {backend.name: backend for backend in detection.backends}
    for rung in proposal.rungs:
        backend = backends.get(rung.source)
        if backend is None or backend.window is None:
            limits.append(
                f"units.{rung.name}.window: the context length {rung.source} "
                f"serves could not be read, so none is written. A `code` "
                f"reply is sent its unit's maximum, so a code "
                f"dispatch to {rung.name} refuses until "
                f"`units.{rung.name}.window` or `units.{rung.name}.output_tokens` "
                f"is set."
            )
    if api_units:
        # Each hosted unit is named with the variable its key comes from, so a
        # person can find the variable without reading the ladder.
        named = ", ".join(f"{u.name} (${u.api_key_env})" for u in api_units)
        limits.append(
            f"Hosted units are bound and every dispatch to one spends money: "
            f"{named}. Each needs its variable exported — `mcgyvr local_pool` skips "
            f"a rung whose variable is unset and says so. Review is on and "
            f"picks the next dearer local rung with another model; a hosted "
            f"unit never reviews on its own, and reviews — spending money on "
            f"every review — only when `verifier.unit` names it, or stands in "
            f"for a hosted named one above it on the ladder whose own model "
            f"wrote the work. Work with no "
            f"such local rung above it is accepted and labelled unverified. "
            f"`orchestrator` is still unbound."
        )
    else:
        limits.append(
            "No API provider is configured. This is a supported install: the "
            "deterministic gate is the acceptance bar, and each rung's work is "
            "reviewed by the next dearer local rung serving another model; work with "
            "no such rung above it is accepted and labelled unverified. Bind "
            "`orchestrator` once you have a key."
        )
    if not detection.docker:
        limits.append(
            "sandbox.mode is `tempdir`, the explicitly weaker mode. A "
            "contract's acceptance commands run without a shell, but each runs "
            "whatever program it names, on the host, with only the host's "
            "process, network and resource isolation, so install Docker "
            "before running contracts you did not write."
        )
    return tuple(limits)


def _distinct_api_units(api_units: Sequence[ApiUnit]) -> tuple[ApiUnit, ...]:
    """The `--api` units with one unit per name, or `InitError` naming both specs
    that minted the same name — a ladder lists a unit once."""
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
    """Every leaf of a nested mapping or list as `dotted.path` -> value.

    Mapping keys and list indices both extend the prefix, so two data trees can
    be compared key by key; a leaf is whatever is neither a mapping nor a list."""
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
    """The keys whose value differs between the loaded setup and the proposed
    data, sorted by dotted path and read through `_flatten`. A key on one side
    only counts, with the missing side reported as unset."""
    have = _flatten(current.data)
    want = _flatten(proposed)
    keys = sorted(set(have) | set(want))
    return tuple(
        Delta(key, have.get(key), want.get(key))
        for key in keys
        if have.get(key) != want.get(key)
    )


def _decision_from(
    found: Detection, proposal: Proposal
) -> tuple[Endpoint | None, str | None]:
    """The endpoint and model to decide on when `--priority` was given without
    naming them: the first detected backend as an endpoint, and the first
    proposed rung's model, or the backend's first listed model when nothing was
    proposed. Either half is None when there is nothing to take it from."""
    backend = found.backends[0] if found.backends else None
    endpoint = endpoint_for_backend(backend) if backend is not None else None
    if proposal.rungs:
        model = proposal.rungs[0].model
    elif backend is not None and backend.models:
        model = backend.models[0]
    else:
        model = None
    return endpoint, model


def _composition_note(
    priority: str, recommendation: Recommendation, data: Mapping[str, Any]
) -> str:
    """The decision line for a setup the Jev layer composed: the priority, the
    candidate it selected, how many were assembled from the measured machine and
    the declared schema, the ladder written, and the reminder that only
    composition was chosen — every number is measured or the schema's."""
    ladder = ", ".join(str(name) for name in data.get("ladder", ()))
    return (
        f"Priority {priority!r}: the Jev layer selected the "
        f"{recommendation.selected.name!r} setup from "
        f"{len(recommendation.candidates)} candidate(s) assembled from the "
        f"measured machine and the declared schema. The ladder is: {ladder}. "
        f"Only composition was chosen — every number in these files is "
        f"measured or the schema's, never the model's."
    )


def _compose_unavailable_note(priority: str) -> str:
    """The note written instead of a composition when a priority was asked for but
    no endpoint and model could be named to decide on."""
    return (
        f"A priority {priority!r} was asked for, but no backend answered "
        f"to run the Jev decision on, so init wrote the deterministic ladder "
        f"instead. Re-run with a backend up — or `mcgyvr setup --host <name>` "
        f"for a rig — to have the ladder composed."
    )


def _compose_failed_note(priority: str, why: Exception) -> str:
    """The note written instead of a composition when the Jev decision could not
    be read, naming what the decision or the runner raised."""
    return (
        f"A priority {priority!r} was asked for, but the Jev decision "
        f"could not be read ({why}), so init wrote the deterministic ladder "
        f"instead. Every number in the file is still measured or the schema's."
    )


def initialize(
    path: Path,
    *,
    force: bool = False,
    detection: Detection | None = None,
    hosts: Sequence[str] = (),
    api_units: Sequence[ApiUnit] = (),
    priority: str | None = None,
    decision_endpoint: Endpoint | None = None,
    decision_model: str | None = None,
    use_case: str = MCGYVR_CODE,
    deployment: str | None = None,
    jev: str | None = None,
    compose_dir: Path | None = None,
) -> InitResult:
    """Write fleet.yaml and policy.yaml into `path`, or report what would change.

    A `detection` is used when given; otherwise the named `hosts` are probed, or
    `DEFAULT_PROBE_TARGETS`. `propose` binds one rung per listed model and `build`
    turns that plus the `--api` units into the data both files render from. A
    `priority` with something to bind has the Jev layer pick among candidate
    compositions instead, and the note saying what it picked — or why it could
    not — leads the decisions; `--jev` is applied afterwards, so it wins over the
    composed data.

    The rendered files are parsed back through `parse_config` before anything is
    written, so a setup the loader would reject raises `InitError` with the
    loader's objection and the ways out. With neither file present both are
    written and `created` is True. Otherwise the deltas against the loaded setup
    are reported and nothing is replaced unless `force`, which is what `written`
    says."""
    found = (
        detection
        if detection is not None
        else detect(targets_for(hosts) if hosts else DEFAULT_PROBE_TARGETS)
    )
    asked = _distinct_api_units(api_units)
    proposal = propose(sources=_sources_for(found))
    data: dict[str, Any] = dict(
        build(
            found,
            proposal,
            api_units=asked,
            use_case=use_case,
            deployment=deployment,
        )
    )
    composition: tuple[str, ...] = ()
    compose_limits: tuple[str, ...] = ()

    if priority is not None and (proposal.rungs or asked):
        endpoint, model = decision_endpoint, decision_model
        if endpoint is None or model is None:
            derived_endpoint, derived_model = _decision_from(found, proposal)
            endpoint = endpoint if endpoint is not None else derived_endpoint
            model = model if model is not None else derived_model
        if endpoint is not None and model is not None:
            try:
                recommendation = recommend(
                    endpoint,
                    model,
                    found,
                    proposal,
                    priority,
                    api_units=asked,
                    use_case=use_case,
                    deployment=deployment,
                )
            except (DecisionError, RunnerError) as exc:
                compose_limits = (_compose_failed_note(priority, exc),)
            else:
                data = dict(recommendation.selected.data)
                composition = (_composition_note(priority, recommendation, data),)
        else:
            compose_limits = (_compose_unavailable_note(priority),)

    # Applied after composition, so `--jev` wins over the composed data.
    data = _opt_ins(data, jev=jev)
    if compose_dir is not None:
        data["serving"] = {
            **dict(data.get("serving") or {}),
            "enable_sleep_wake": True,
            "compose_dir": str(compose_dir),
        }

    chosen_deployment = (
        deployment if deployment is not None else _deployment_default(use_case)
    )
    decisions = (
        _decisions(found, proposal, asked)
        + composition
        + (f"Use case {use_case!r} under deployment {chosen_deployment!r}.",)
        + _opt_in_decisions(jev=jev)
    )
    # A local-only install with one seat provisions the resident orchestrator on
    # the card the ladder serves from. That is worth saying, so it is recorded as
    # a decision — nothing here refuses it.
    if local_orchestrator(
        use_case=use_case,
        local_only=chosen_deployment == LOCAL_ONLY,
        users=int(data.get("users", 1)),
    ).flag_single_user:
        decisions += (
            "Local-only on a single-user install: the resident orchestrator "
            "consumes the card the ladder would otherwise use — flagged, not "
            "refused.",
        )
    limits = _limits(found, proposal, asked) + compose_limits
    fleet_content = render_fleet(data, decisions)
    policy_content = render_policy(data, _policy_notes(found, data))

    # The rendered files are parsed back with the loader's own parser, so a setup
    # that would not load is caught here rather than by the next command to read
    # both files.
    try:
        normalized: Mapping[str, Any] = parse_config(
            fleet_content, policy_content, path=path
        ).data
    except ConfigError as exc:
        # The composed setup does not load, so init refuses rather than writes a
        # file the loader would reject: the refusal says what the loader objected
        # to and, for `--api`, what a hosted spec must carry.
        if asked:
            raise InitError(_api_setup_rejected(asked, exc)) from exc
        raise InitError(_nothing_to_bind(found, exc, proposal)) from exc

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
        # A setup already on disk that does not parse is no baseline to diff
        # against: it is reported as one change, with the loader's first sentence
        # as the reason, and only `--force` replaces it.
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
