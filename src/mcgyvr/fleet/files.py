"""The one reader of a setup's files: fleet, policy, hitchhike and crew.

Four files, four vocabularies. `load_fleet` reads what runs where — the
units, the rigs and the fleets; `load_policy` reads how work moves over those
units — the ladder and the policy settings; `load_hitchhike` reads the units a hub
lends, which `mcgyvr rig rungs sync` writes and nothing else does; `load_crew`
reads the units your crews lend through a hub, which `mcgyvr rig crew sync`
writes and nothing else does. Each file
refuses a key that belongs to another and an unknown key, naming in the message
what to write instead, because a file that does not say what it means must not
be read under rules it never agreed to.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeGuard

import yaml

from mcgyvr.renamed import warn_renamed
from mcgyvr.strict_yaml import strict_loader


class FleetFileError(Exception):
    """A setup file this module will not read: invalid YAML, a key that is not
    text or is duplicated, an unknown or misplaced key, or a value of
    the wrong shape where a block, a list or a name was expected."""


#: The keys a unit block may carry in `fleet.yaml`: one process at one address,
#: with every fact about what it is and what it can physically do. The loader
#: accepts exactly these and refuses anything else, so a consumer that reads a
#: named field off a loaded unit can never see a key the parser ignored.
#: `unit_id` is the lock's identity field — authored here, read by the lock.
_UNIT_KEYS = frozenset(
    {
        "rig",
        "unit_id",
        "address",
        "engine",
        "image",
        "api_key_env",
        "model",
        "width",
        "window",
        "output_tokens",
        "request_timeout_s",
        "room_mib",
        "kv_cache_memory_bytes",
        "attention_backend",
        "container",
        "hf_cache",
        "sampling",
        "sleep",
        "launcher",
        "expose",
        "launch",
        "scope",
    }
)

#: The keys `policy.yaml` may carry: `ladder` plus how work moves and how much
#: it may do — fanout, triage, dependents, attempts, draws, escalations,
#: re-decompositions, re-proposals, refine bounds, retry notes, timeouts, the
#: window fraction,
#: breadth, cleanup, users — the units a job goes to (proposer, verifier,
#: jev), what the gate refuses, and how a run is sandboxed, delivered, served
#: and journaled.
_POLICY_KEYS = frozenset(
    {
        "use_case",
        "deployment",
        "ladder",
        "fanout",
        "ride_scope",
        "private",
        "triage",
        "dependents",
        "infer_dependencies",
        "same_file",
        "attempts",
        "draws",
        "rider_slots",
        "max_escalations",
        "max_attempts",
        "max_redecompositions",
        "max_reproposals",
        "max_splits_per_file",
        "max_refine_fanout",
        "retry_notes",
        "task_timeout_s",
        "max_window_fraction",
        "users",
        "breadth",
        "cleanup",
        "gate",
        "proposer",
        "verifier",
        "jev",
        "sandbox",
        "delivery",
        "serving",
        "journal",
    }
)

#: Policy keys an earlier build read and this one does not, dotted from the
#: top of `policy.yaml`, each with what became of it. Every `policy.yaml` that
#: `mcgyvr setup` wrote before the ladder manager and chat/agent sessions were
#: removed carries the first two. They are refused rather than read — an
#: ignored key is a file that does not do what it says — but all at once, so a
#: setup from before is mended in one pass, and `mcgyvr setup` on its folder
#: names the lines to delete (`retired_policy_lines`).
RETIRED_POLICY_KEYS: dict[str, str] = {
    "manager": (
        "the ladder manager and `mcgyvr manage` were removed; a run wakes a "
        "sleeping unit itself when `serving.enable_sleep_wake` is on"
    ),
    "sandbox.sessions": (
        "chat and agent sessions were removed, and with them the sandbox a "
        "session was staged in"
    ),
    "orchestrator.tools": (
        "it named the harness tools `type: mcorch` kept, and mcorch was removed"
    ),
}

#: Keys renamed outright: the old name is refused, naming the new one, rather
#: than read (`proposer` has no `type`, the one value of which nothing read).
#: Not retired keys: `mcgyvr setup` would offer to delete the user's binding.
RENAMED_POLICY_KEYS: dict[str, str] = {"orchestrator": "proposer"}
RENAMED_UNIT_KEYS: dict[str, str] = {"role": "sleep"}

#: Names read under their old spelling for one release, with a warning
#: (`mcgyvr.renamed`): a policy key, and the values of `proposer.authoring`.
OLD_POLICY_KEYS: dict[str, str] = {"max_replans": "max_redecompositions"}
OLD_AUTHORING: dict[str, str] = {"classifier": "fill", "prose": "draft"}


def _refuse_renamed(key: str, new: str, where: str) -> None:
    dropped = " and drop its `type` line" if key == "orchestrator" else ""
    raise FleetFileError(
        f"{where}: `{key}` is now `{new}`: rename it{dropped}. The old name is "
        f"not read."
    )


def _read_renamed(given: dict[str, Any]) -> dict[str, Any]:
    """`given` with each `OLD_POLICY_KEYS` key and `OLD_AUTHORING` value read
    under its new name, each with a warning; both names at once is refused."""
    out: dict[str, Any] = {}
    for key, value in given.items():
        new = OLD_POLICY_KEYS.get(key)
        if new is not None:
            if new in given:
                raise FleetFileError(
                    f"policy.yaml: carries both `{new}` and `{key}`, its old "
                    f"name: keep `{new}`"
                )
            warn_renamed("policy.yaml", key, new)
            key = new
        out[key] = value
    block = out.get("proposer")
    authoring = block.get("authoring") if isinstance(block, Mapping) else None
    # A value that is not text (a list, a mapping) is left to the schema to
    # refuse: it cannot be an old name, and testing it as a key would raise.
    if (
        isinstance(block, Mapping)
        and isinstance(authoring, str)
        and (authoring in OLD_AUTHORING)
    ):
        old = authoring
        warn_renamed("policy.yaml: proposer.authoring", old, OLD_AUTHORING[old])
        out["proposer"] = {**block, "authoring": OLD_AUTHORING[old]}
    return out


#: The top-level keys `fleet.yaml` may carry; a policy setting, a `hitchhike` block
#: or anything else at that level is refused rather than carried along unseen.
_FLEET_KEYS = frozenset({"units", "rigs", "fleets"})

#: What a `fleets` entry may say: `layout` (rig -> slots) and `next` (the fleets
#: this one may switch to).
_FLEET_BLOCK_KEYS = frozenset({"layout", "next"})

#: The one key `hitchhike.yaml` may carry. Its units are lent through a hub and
#: written whole by `mcgyvr rig rungs sync`, so they are read as units marked
#: `hitchhike` and never join `units` or the ladder.
_HITCHHIKE_FILE_KEYS = frozenset({"hitchhike"})

#: The key `hitchhike.yaml` carried when it was `relief.yaml`. Read there as
#: `hitchhike` for one release, so a setup synced before the rename still
#: loads until its next sync rewrites the file; refused anywhere else, naming
#: the new key.
OLD_HITCHHIKE_KEY = "relief"

#: The one other key `hitchhike.yaml` carries: the NAME of the variable holding
#: the rider's personal hub key, as `mcgyvr rig rungs sync` was told it
#: (`--key-env`), so the rig agent's refresh and `mcgyvr rig status` read the
#: key from the same variable. It is the name, never the key.
KEY_ENV_FIELD = "api_key_env"

#: The one key `crew.yaml` may carry, and the keys each of its units may: what
#: `mcgyvr rig crew sync` writes. Its units join `units` as they are.
_CREW_FILE_KEYS = frozenset({"crew"})
_CREW_UNIT_KEYS = frozenset({"address", "model", "api_key_env", "width", "scope"})

#: The loader every setup file is read with: a key repeated anywhere in the
#: file, or one that is a list or a mapping, is refused instead of
#: last-one-wins, quoted through a bounded repr.
_LOADER = strict_loader(FleetFileError)


def _typename(value: object) -> str:
    if value is None:
        return "nothing"
    return {
        bool: "a true/false value",
        int: "a number",
        float: "a number",
        str: "text",
        list: "a list",
        dict: "a block of keys",
    }.get(type(value), type(value).__name__)


def _yaml(text: str) -> Any:
    try:
        return yaml.load(text, Loader=_LOADER)
    except yaml.YAMLError as exc:
        raise FleetFileError(f"not valid YAML: {exc}") from exc


def _document(raw: object, name: str) -> dict[str, Any]:
    if raw is None:
        raise FleetFileError(f"{name}: is empty.")
    if not isinstance(raw, dict):
        raise FleetFileError(
            f"{name}: expected a block of keys, found {_typename(raw)}"
        )
    for key in raw:
        if not isinstance(key, str):
            raise FleetFileError(
                f"{name}: key {key!r} is not text — keys must be names"
            )
    return dict(raw)


def _refuse_policy_setting(key: str, where: str) -> None:
    raise FleetFileError(
        f"{where}: `{key}` is a policy setting — it belongs in policy.yaml, "
        f"not in fleet.yaml."
    )


def _refuse_hitchhike(key: str, where: str) -> None:
    renamed = (
        f" (`{OLD_HITCHHIKE_KEY}` is now `hitchhike`)"
        if key == OLD_HITCHHIKE_KEY
        else ""
    )
    raise FleetFileError(
        f"{where}: `{key}` is written by `mcgyvr rig rungs sync`{renamed} — it "
        f"belongs in hitchhike.yaml, which nothing else writes."
    )


def _refuse_unit_fact(key: str) -> None:
    raise FleetFileError(
        f"policy.yaml: `{key}` is a fact about a unit, not about how work "
        f"moves — it belongs in fleet.yaml under `units`."
    )


def _unknown_key(key: str, where: str, known: frozenset[str]) -> None:
    raise FleetFileError(
        f"{where}: unknown key {key!r}. An ignored key is a file that does "
        f"not do what it says. Valid keys here: {', '.join(sorted(known))}"
    )


def retired_policy_keys(policy: Mapping[str, Any]) -> tuple[str, ...]:
    """The keys of `RETIRED_POLICY_KEYS` that `policy` carries, in its order."""
    found: list[str] = []
    for dotted in RETIRED_POLICY_KEYS:
        head, _, rest = dotted.partition(".")
        if head not in policy:
            continue
        block = policy[head]
        if not rest or (isinstance(block, Mapping) and rest in block):
            found.append(dotted)
    return tuple(found)


def _refuse_retired(policy: Mapping[str, Any]) -> None:
    found = retired_policy_keys(policy)
    if not found:
        return
    named = "\n".join(f"  - `{key}`: {RETIRED_POLICY_KEYS[key]}" for key in found)
    raise FleetFileError(
        f"policy.yaml: carries {len(found)} key(s) this version of mcgyvr no "
        f"longer reads. An ignored key is a file that does not do what it "
        f"says, so delete each one, with its block and the comment above "
        f"it:\n{named}\n`mcgyvr setup` on this setup's folder names the exact "
        f"lines, and deletes them when you say yes."
    )


@dataclass(frozen=True)
class RetiredLines:
    """Where one retired key sits in a policy file, comment and block included.

    `first` and `last` are 1-based line numbers, both inclusive; `text` is
    those lines as written.
    """

    key: str
    first: int
    last: int
    text: tuple[str, ...]


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _key_line(lines: list[str], key: str, indent: int, start: int, end: int) -> int:
    """The index of `key:` at exactly `indent` within `lines[start:end]`, or -1."""
    pattern = re.compile(rf"^ {{{indent}}}{re.escape(key)}:(\s|$)")
    for index in range(start, end):
        if pattern.match(lines[index]):
            return index
    return -1


def _block_end(lines: list[str], index: int) -> int:
    """One past the last line of the key at `index`: its value and its block.

    The block is every following line indented deeper than the key, blank lines
    between them included; trailing blank lines are not part of it.
    """
    depth = _indent(lines[index])
    end = index + 1
    for after in range(index + 1, len(lines)):
        if not lines[after].strip():
            continue
        if _indent(lines[after]) <= depth:
            break
        end = after + 1
    return end


def retired_policy_lines(text: str) -> tuple[RetiredLines, ...]:
    """The lines of `text` each retired key it carries is written on.

    A key's lines are its doc comment — the comment lines directly above it at
    its own indent — the key itself, and its block. A key written where no line
    shows it (inside a flow mapping, say) is not listed: the refusal still names
    it.
    """
    lines = text.splitlines()
    spans: list[RetiredLines] = []
    for dotted in RETIRED_POLICY_KEYS:
        parts = dotted.split(".")
        index, end = -1, len(lines)
        start, indent = 0, 0
        for depth, part in enumerate(parts):
            index = _key_line(lines, part, indent, start, end)
            if index < 0:
                break
            if depth + 1 < len(parts):
                start, end = index + 1, _block_end(lines, index)
                nested = next(
                    (
                        _indent(line)
                        for line in lines[start:end]
                        if line.strip() and not line.lstrip().startswith("#")
                    ),
                    None,
                )
                if nested is None:
                    index = -1
                    break
                indent = nested
        if index < 0:
            continue
        first = index
        depth = _indent(lines[index])
        while (
            first > 0
            and lines[first - 1].strip().startswith("#")
            and _indent(lines[first - 1]) == depth
        ):
            first -= 1
        last = _block_end(lines, index)
        spans.append(RetiredLines(dotted, first + 1, last, tuple(lines[first:last])))
    return tuple(spans)


def without_retired_lines(text: str) -> str:
    """`text` with every retired key's lines deleted, and no gap left behind.

    A blank line that only separated a deleted block from the next is deleted
    with it, so a file read as blocks a blank line apart still reads that way.
    """
    lines = text.splitlines(keepends=True)
    drop: set[int] = set()
    for span in retired_policy_lines(text):
        first, last = span.first - 1, span.last
        if first > 0 and not lines[first - 1].strip():
            while last < len(lines) and not lines[last].strip():
                last += 1
            # Keep as many blank lines after the deleted lines' neighbour as
            # stood before them, so the spacing either side is unchanged.
            before = 0
            while first - before - 1 >= 0 and not lines[first - before - 1].strip():
                before += 1
            last = min(last, span.last + max(before, 0))
        drop.update(range(first, last))
    return "".join(line for index, line in enumerate(lines) if index not in drop)


def _unit_block(raw: object, where: str) -> dict[str, Any]:
    given = _document(raw, where)
    for key in given:
        if key in RENAMED_UNIT_KEYS:
            _refuse_renamed(key, RENAMED_UNIT_KEYS[key], where)
        elif key in _POLICY_KEYS:
            _refuse_policy_setting(key, where)
        elif key not in _UNIT_KEYS:
            _unknown_key(key, where, _UNIT_KEYS)
    return given


def _units(raw: object) -> dict[str, Any]:
    given = _document(raw, "fleet.yaml: units")
    return {
        name: _unit_block(block, f"fleet.yaml: units.{name}")
        for name, block in given.items()
    }


def _fleet_block(raw: object, where: str) -> dict[str, Any]:
    given = _document(raw, where)
    for key in given:
        if key in _POLICY_KEYS:
            _refuse_policy_setting(key, where)
        elif key not in _FLEET_BLOCK_KEYS:
            _unknown_key(key, where, _FLEET_BLOCK_KEYS)
    return given


def _fleets(raw: object) -> dict[str, Any]:
    given = _document(raw, "fleet.yaml: fleets")
    return {
        name: _fleet_block(block, f"fleet.yaml: fleets.{name}")
        for name, block in given.items()
    }


def _rigs(raw: object) -> dict[str, Any]:
    # A rig is checked only as a block of text keys: which fields one carries
    # is the lock's business (`rig_id` above all), so they are not listed here.
    return _document(raw, "fleet.yaml: rigs")


def _ladder(raw: object, where: str) -> list[str]:
    if isinstance(raw, list):
        names: list[str] = []
        for index, item in enumerate(raw):
            if not isinstance(item, str) or not item.strip():
                raise FleetFileError(
                    f"{where}.{index}: expected a unit name, found {_typename(item)}"
                )
            names.append(item.strip())
        return names
    if isinstance(raw, dict):
        for key in raw:
            raise FleetFileError(
                f"{where}: unknown key {key!r}. The ladder is an ordered list "
                f"of unit names."
            )
        raise FleetFileError(
            f"{where}: is empty. The ladder is an ordered list of unit names."
        )
    raise FleetFileError(
        f"{where}: expected an ordered list of unit names, found {_typename(raw)}"
    )


def load_fleet(text: str) -> dict[str, Any]:
    """Parse `fleet.yaml` into `units`, `rigs` and `fleets`, refusing the rest.

    Each unit block is held to `_UNIT_KEYS` and each fleet entry to
    `_FLEET_BLOCK_KEYS`; `rigs` is checked only as a block. A policy setting, a
    `hitchhike` block, an unknown key or a value that is not a block of text keys
    raises `FleetFileError`.
    """
    given = _document(_yaml(text), "fleet.yaml")
    data: dict[str, Any] = {}
    for key, value in given.items():
        if key in _POLICY_KEYS:
            _refuse_policy_setting(key, "fleet.yaml")
        elif key in _HITCHHIKE_FILE_KEYS or key == OLD_HITCHHIKE_KEY:
            _refuse_hitchhike(key, "fleet.yaml")
        elif key == "units":
            data[key] = _units(value)
        elif key == "fleets":
            data[key] = _fleets(value)
        elif key == "rigs":
            data[key] = _rigs(value)
        else:
            _unknown_key(key, "fleet.yaml", _FLEET_KEYS)
    return data


def load_policy(text: str) -> dict[str, Any]:
    """Parse how work moves over the units: `policy.yaml`.

    `ladder` is normalised to a list of stripped unit names, cheap first; a
    ladder written as an empty block is refused. Every other top-level key must
    be in `_POLICY_KEYS`. The retired keys it carries are refused first, all in
    one error. A fact about a unit, a `hitchhike` block or an unknown key raises
    `FleetFileError` naming the file it belongs in.
    """
    given = _read_renamed(_document(_yaml(text), "policy.yaml"))
    _refuse_retired(given)
    data: dict[str, Any] = {}
    for key, value in given.items():
        if key in RENAMED_POLICY_KEYS:
            _refuse_renamed(key, RENAMED_POLICY_KEYS[key], "policy.yaml")
        elif key in _UNIT_KEYS:
            _refuse_unit_fact(key)
        elif key in _HITCHHIKE_FILE_KEYS or key == OLD_HITCHHIKE_KEY:
            _refuse_hitchhike(key, "policy.yaml")
        elif key == "ladder":
            data[key] = _ladder(value, "policy.yaml: ladder")
        elif key in _POLICY_KEYS:
            data[key] = value
        else:
            _unknown_key(key, "policy.yaml", _POLICY_KEYS)
    return data


def load_hitchhike(text: str) -> dict[str, Any]:
    """Parse `hitchhike.yaml`: the units a hub lends, under the one key
    `hitchhike` (`OLD_HITCHHIKE_KEY` in a file synced before the rename, read
    the same for one release).

    The `hitchhike` entry and each unit's block are checked only as blocks of text
    keys and kept as given, since their fields are the schema's. The
    `KEY_ENV_FIELD` beside it must be a variable's name and is left out: it is
    the sync's, read by `recorded_key_env`, not the setup's. Any other key raises
    `FleetFileError`; nothing here joins `units` or the ladder.
    """
    return _rides_block(_document(_yaml(text), "hitchhike.yaml"))


def _rides_block(given: Mapping[str, Any]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, value in given.items():
        if key == KEY_ENV_FIELD:
            _key_env(value, f"hitchhike.yaml: {key}")
            continue
        if key == OLD_HITCHHIKE_KEY:
            if "hitchhike" in given:
                raise FleetFileError(
                    f"hitchhike.yaml: carries both `hitchhike` and "
                    f"`{OLD_HITCHHIKE_KEY}`, its old name: keep `hitchhike`"
                )
            key = "hitchhike"
        elif key not in _HITCHHIKE_FILE_KEYS:
            _unknown_key(key, "hitchhike.yaml", _HITCHHIKE_FILE_KEYS | {KEY_ENV_FIELD})
        entries = _document(value, "hitchhike.yaml: hitchhike")
        data[key] = {
            name: _document(block, f"hitchhike.yaml: hitchhike.{name}")
            for name, block in entries.items()
        }
    return data


def recorded_key_env(text: str) -> str | None:
    """The variable name `hitchhike.yaml` text records the personal hub key in.

    That is its top-level `KEY_ENV_FIELD`; in a file written before it was
    recorded there, the `api_key_env` every hitchhike rung names when they all
    name one. `None` where it records none: no rung, or rungs naming several.
    A name that is not a variable's raises `FleetFileError`, as a file that
    does not load does.
    """
    given = _document(_yaml(text), "hitchhike.yaml")
    rungs = _rides_block(given).get("hitchhike", {})
    if KEY_ENV_FIELD in given:
        return str(given[KEY_ENV_FIELD])
    return _carried_key_env(rungs, "hitchhike.yaml: hitchhike")


def crew_key_env(text: str) -> str | None:
    """The variable name `crew.yaml` text reads the personal hub key from: the
    `api_key_env` every crew unit names when they all name one, as
    `mcgyvr rig crew sync` was told it. `None` where they name none or several.
    A name that is not a variable's raises `FleetFileError`, as a file that
    does not load does."""
    return _carried_key_env(load_crew(text).get("crew", {}), "crew.yaml: crew")


def _carried_key_env(units: Mapping[str, Any], where: str) -> str | None:
    """The one `KEY_ENV_FIELD` the blocks in `units` name, each checked as a
    variable's name; `None` where they name none or several."""
    named = {
        _key_env(block[KEY_ENV_FIELD], f"{where}.{name}.{KEY_ENV_FIELD}")
        for name, block in units.items()
        if KEY_ENV_FIELD in block
    }
    return named.pop() if len(named) == 1 else None


def is_variable_name(raw: object) -> TypeGuard[str]:
    """Whether `raw` is an environment variable's name: `[A-Za-z_][A-Za-z0-9_]*`,
    the shape `--key-env` takes and `hitchhike.yaml` records."""
    return isinstance(raw, str) and raw.isascii() and raw.isidentifier()


def _key_env(raw: object, where: str) -> str:
    """`raw` as a variable's name, else `FleetFileError` at `where`."""
    if not is_variable_name(raw):
        raise FleetFileError(
            f"{where}: is not a variable's name. It takes the NAME of the "
            "variable holding your personal hub key, never the key"
        )
    return raw


def load_crew(text: str) -> dict[str, Any]:
    """Parse `crew.yaml`: the units your crews lend, under the one key `crew`.

    Each unit's block may carry only `_CREW_UNIT_KEYS` and is kept as given,
    since its fields are the schema's `units` fields. Any other key raises
    `FleetFileError`.
    """
    given = _document(_yaml(text), "crew.yaml")
    data: dict[str, Any] = {}
    for key, value in given.items():
        if key not in _CREW_FILE_KEYS:
            _unknown_key(key, "crew.yaml", _CREW_FILE_KEYS)
        entries = _document(value, "crew.yaml: crew")
        units: dict[str, Any] = {}
        for name, block in entries.items():
            where = f"crew.yaml: crew.{name}"
            units[name] = _document(block, where)
            for field in units[name]:
                if field not in _CREW_UNIT_KEYS:
                    _unknown_key(field, where, _CREW_UNIT_KEYS)
        data[key] = units
    return data
