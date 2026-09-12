"""``fleet.yaml`` is what runs where; ``policy.yaml`` is how work moves between units.

Two files, one vocabulary (``records/plans/fleet-identity.md`` §2):

* ``fleet.yaml`` is locked. It holds the ``units``, the ``rigs`` and the
  ``fleets``. A unit carries every fact about what it is and can physically
  do: its rig, address, engine, model, width, context window, reply size and
  request timeout.
* ``policy.yaml`` is not locked. It holds how work moves: the ``ladder`` (an
  ordered list of unit names), then fanout, attempts, escalations and the rest.
* "source", "rung" and "tier" are gone: a unit is the one term.

The two files are loaded separately and each refuses what belongs in the other,
so a fact about a unit cannot ride in the policy file and a routing decision
cannot ride in the fleet file. Unknown keys are refused, never ignored.
"""

from __future__ import annotations

from typing import Any

import yaml


class FleetFileError(Exception):
    """``fleet.yaml`` or ``policy.yaml`` parsed, but does not satisfy the schema."""


#: What a unit is or can physically do. Locked: these belong in ``fleet.yaml``.
_UNIT_KEYS = frozenset(
    {
        "rig",
        "address",
        "engine",
        "model",
        "width",
        "window",
        "output_tokens",
        "request_timeout_s",
    }
)

#: How work moves between units. Not locked: these belong in ``policy.yaml``.
_POLICY_KEYS = frozenset(
    {
        "ladder",
        "fanout",
        "attempts",
        "max_escalations",
        "max_attempts",
        "task_timeout_s",
        "max_window_fraction",
        "breadth",
        "cleanup",
        "orchestrator",
        "verifier",
        "sandbox",
        "delivery",
        "journal",
    }
)

#: The three blocks ``fleet.yaml`` holds.
_FLEET_KEYS = frozenset({"units", "rigs", "fleets"})

#: What a fleet block holds: its layout as room slots, and the fleets it moves to.
_FLEET_BLOCK_KEYS = frozenset({"layout", "next"})

#: Words the vocabulary retired. One term — "unit" — replaced several.
_RETIRED_WORDS = {
    "sources": "name what serves under `units` — a unit is the one term",
    "source": "a unit is the one term",
    "rung": "a unit is the one term",
    "rungs": "a ladder names `unit names`, not rungs or tiers",
    "tier": "a unit is the one term",
    "tiers": "a ladder names `unit names`, not rungs or tiers",
}


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate keys instead of taking the last one."""


def _no_duplicate_keys(
    loader: yaml.SafeLoader, node: yaml.nodes.MappingNode
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            hash(key)
        except TypeError:
            # `[dev]: x` — a list as a key. YAML allows it; a file does not.
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
    # P1 pins only `units`; the fields of a rig block are owned by P2 (the
    # rig identities). What is checked here is that the block is a mapping.
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
    """Parse a ``fleet.yaml`` document: units, rigs and fleets."""
    given = _document(_yaml(text), "fleet.yaml")
    data: dict[str, Any] = {}
    for key, value in given.items():
        if key in _POLICY_KEYS:
            _refuse_policy_setting(key, "fleet.yaml")
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
    """Parse a ``policy.yaml`` document: how work moves between units."""
    given = _document(_yaml(text), "policy.yaml")
    data: dict[str, Any] = {}
    for key, value in given.items():
        if key in _UNIT_KEYS:
            _refuse_unit_fact(key)
        elif key == "ladder":
            data[key] = _ladder(value, "policy.yaml: ladder")
        elif key in _POLICY_KEYS:
            data[key] = value
        else:
            _unknown_key(key, "policy.yaml", _POLICY_KEYS)
    return data
