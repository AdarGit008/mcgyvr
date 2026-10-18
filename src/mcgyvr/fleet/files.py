"""The one reader of a setup's `fleet.yaml`, `policy.yaml` and `relief.yaml`.

Three files, three vocabularies. `load_fleet` reads what runs where — the
units, the rigs and the fleets; `load_policy` reads how work moves over those
units — the ladder and the policy settings; `load_relief` reads the units a hub
lends, which `mcgyvr rig rungs sync` writes and nothing else does. Each file
refuses a key that belongs to another, an unknown key, and a word that was
retired, naming in the message what to write instead, because a file that does
not say what it means must not be read under rules it never agreed to.
"""

from __future__ import annotations

from typing import Any

import yaml


class FleetFileError(Exception):
    """A setup file this module will not read: invalid YAML, a key that is not
    text or is duplicated, an unknown, retired or misplaced key, or a value of
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
        "role",
        "launch",
    }
)

#: The keys `policy.yaml` may carry: `ladder` plus how work moves and how much
#: it may do — fanout, attempts, draws, escalations, timeouts, the window
#: fraction, breadth, cleanup, users — the units a job goes to (orchestrator,
#: verifier, jev, manager), what the gate refuses, and how a run is sandboxed,
#: delivered, served and journaled.
_POLICY_KEYS = frozenset(
    {
        "use_case",
        "deployment",
        "ladder",
        "fanout",
        "attempts",
        "draws",
        "rider_slots",
        "max_escalations",
        "max_attempts",
        "task_timeout_s",
        "max_window_fraction",
        "users",
        "breadth",
        "cleanup",
        "gate",
        "orchestrator",
        "verifier",
        "jev",
        "sandbox",
        "delivery",
        "serving",
        "manager",
        "journal",
    }
)

#: The top-level keys `fleet.yaml` may carry; a policy setting, a `relief` block
#: or anything else at that level is refused rather than carried along unseen.
_FLEET_KEYS = frozenset({"units", "rigs", "fleets"})

#: What a `fleets` entry may say: `layout` (rig -> slots) and `next` (the fleets
#: this one may switch to).
_FLEET_BLOCK_KEYS = frozenset({"layout", "next"})

#: The one key `relief.yaml` may carry. Its units are lent through a hub and
#: written whole by `mcgyvr rig rungs sync`, so they are read as units marked
#: `relief` and never join `units` or the ladder.
_RELIEF_FILE_KEYS = frozenset({"relief"})

#: Words a file may no longer use, each mapped to what replaced it, so a refusal
#: can name the term to write instead of only saying the key is unknown.
_RETIRED_WORDS = {
    "sources": "name what serves under `units` — a unit is the one term",
    "source": "a unit is the one term",
    "rung": "a unit is the one term",
    "rungs": "a ladder names `unit names`, not rungs or tiers",
    "tier": "a unit is the one term",
    "tiers": "a ladder names `unit names`, not rungs or tiers",
}


class _StrictLoader(yaml.SafeLoader):
    """A `SafeLoader` that builds every mapping through `_no_duplicate_keys`, so
    a key repeated anywhere in the file is refused instead of last-one-wins."""


def _no_duplicate_keys(
    loader: yaml.SafeLoader, node: yaml.nodes.MappingNode
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            hash(key)
        except TypeError:
            # A list or a mapping cannot be a key: a key is one word.
            mark = key_node.start_mark
            raise FleetFileError(
                f"key {key!r} at line {mark.line + 1} is not a plain name; a "
                "file key is one word, never a list or a mapping."
            ) from None
        if key in mapping:
            mark = key_node.start_mark
            raise FleetFileError(
                f"duplicate key {key!r} at line {mark.line + 1} — YAML would "
                f"silently keep only the last one, so the file does not mean "
                f"what it looks like it means."
            )
        mapping[key] = loader.construct_object(value_node, deep=True)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys
)


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
        return yaml.load(text, Loader=_StrictLoader)
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


def _refuse_retired(key: str, where: str) -> None:
    hint = _RETIRED_WORDS.get(key)
    if hint is None:
        return
    raise FleetFileError(f"{where}: `{key}` is retired — {hint}.")


def _refuse_policy_setting(key: str, where: str) -> None:
    raise FleetFileError(
        f"{where}: `{key}` is a policy setting — it belongs in policy.yaml, "
        f"not in fleet.yaml."
    )


def _refuse_relief(where: str) -> None:
    raise FleetFileError(
        f"{where}: `relief` is written by `mcgyvr rig rungs sync` — it belongs "
        f"in relief.yaml, which nothing else writes."
    )


def _refuse_unit_fact(key: str) -> None:
    raise FleetFileError(
        f"policy.yaml: `{key}` is a fact about a unit, not about how work "
        f"moves — it belongs in fleet.yaml under `units`."
    )


def _unknown_key(key: str, where: str, known: frozenset[str]) -> None:
    _refuse_retired(key, where)
    raise FleetFileError(
        f"{where}: unknown key {key!r}. An ignored key is a file that does "
        f"not do what it says. Valid keys here: {', '.join(sorted(known))}"
    )


def _unit_block(raw: object, where: str) -> dict[str, Any]:
    given = _document(raw, where)
    for key in given:
        if key in _POLICY_KEYS:
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
            _refuse_retired(key, where)
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
    `relief` block, an unknown key (including a retired word, which is named
    with what replaced it) or a value that is not a block of text keys raises
    `FleetFileError`.
    """
    given = _document(_yaml(text), "fleet.yaml")
    data: dict[str, Any] = {}
    for key, value in given.items():
        if key in _POLICY_KEYS:
            _refuse_policy_setting(key, "fleet.yaml")
        elif key in _RELIEF_FILE_KEYS:
            _refuse_relief("fleet.yaml")
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
    be in `_POLICY_KEYS`. A fact about a unit, a `relief` block, an unknown key
    or a retired word raises `FleetFileError` naming the file it belongs in.
    """
    given = _document(_yaml(text), "policy.yaml")
    data: dict[str, Any] = {}
    for key, value in given.items():
        if key in _UNIT_KEYS:
            _refuse_unit_fact(key)
        elif key in _RELIEF_FILE_KEYS:
            _refuse_relief("policy.yaml")
        elif key == "ladder":
            data[key] = _ladder(value, "policy.yaml: ladder")
        elif key in _POLICY_KEYS:
            data[key] = value
        else:
            _unknown_key(key, "policy.yaml", _POLICY_KEYS)
    return data


def load_relief(text: str) -> dict[str, Any]:
    """Parse `relief.yaml`: the units a hub lends, under the one key `relief`.

    The `relief` entry and each unit's block are checked only as blocks of text
    keys and kept as given, since their fields are the schema's. Any other key
    raises `FleetFileError`; nothing here joins `units` or the ladder.
    """
    given = _document(_yaml(text), "relief.yaml")
    data: dict[str, Any] = {}
    for key, value in given.items():
        if key not in _RELIEF_FILE_KEYS:
            _unknown_key(key, "relief.yaml", _RELIEF_FILE_KEYS)
        entries = _document(value, "relief.yaml: relief")
        data[key] = {
            name: _document(block, f"relief.yaml: relief.{name}")
            for name, block in entries.items()
        }
    return data
