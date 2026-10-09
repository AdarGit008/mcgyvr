"""The hub's published schemas as the rig agent's tests hold them, and a check of them.

The hub publishes the contracts the agent speaks as JSON Schemas (draft
2020-12), written from its own models: its agent protocol, and the REST API a
rider's agent uses beside it. The agent does not copy them into its code: it
states the few limits it needs (:mod:`mcgyvr.rig.protocol`,
:mod:`mcgyvr.rig.udpwire`, :mod:`mcgyvr.rig.rungs`), and these tests hold
those limits, and every message the agent writes, to a pinned copy of each
hub file (:data:`PINS`):

* :data:`PROTOCOL`, the hub's ``schemas/protocol.schema.json``, pinned as
  ``tests/fixtures/hub_protocol_v1.schema.json``;
* :data:`RIDER`, the hub's ``schemas/rider.schema.json``, pinned as
  ``tests/fixtures/hub_rider_v1.schema.json``.

A pinned copy is the hub's file with its ``$id`` left out (an address that
names no machine of ours, and that no ``$ref`` in the file uses), written back
the way the hub writes it. Two digests pin each. ``hub_sha256`` is the hub's
file as the hub publishes it; ``pinned_sha256`` is the copy here. An edit to a
copy that did not come from the hub fails on the second.

The first is checked against a hub when one is named (:func:`hub_file`):
``MCGYVR_HUB_REPO``, a hub checkout, names every file at once (its
``schemas/`` folder; the real-hub test,
``tests/test_a_real_hub_runs_a_unit_per_card_of_a_real_agent.py``, reads the
same variable and runs that checkout's hub), and each file's own variable
(``MCGYVR_HUB_SCHEMA``, ``MCGYVR_HUB_RIDER_SCHEMA``) names that file alone,
before it. A hub that moved a schema then fails here instead of on the wire.
Naming ``MCGYVR_HUB_REPO`` runs that real-hub test too, which fails on a
checkout without its built ``.venv`` (``uv sync`` in it): a run that checks
the schemas alone names each file by its own variable instead.

A hub's own CI can run the agent's contract tests against a schema it is
about to publish, before it is pinned here: ``MCGYVR_HUB_SCHEMA_UNDER_TEST``
names a directory holding the hub's schema files (its ``schemas/`` folder, or
any directory containing ``protocol.schema.json`` and
``rider.schema.json``). :func:`load` then reads ``<dir>/<pinned.hub_name>``
instead of the pinned copy and skips the ``pinned_sha256`` check, so a
candidate that moved a value the agent reads fails the contract assertion
that reads it rather than the digest tripwire. The drift check above is
separate and unchanged: ``MCGYVR_HUB_SCHEMA`` and ``MCGYVR_HUB_REPO`` still
name the published file the copy was pinned from, and still fail when it
moved from ``hub_sha256``.

To move to a new hub's schemas::

    uv run --no-sync python -m tests.rig_schema /path/to/hub-checkout

rewrites every copy and the digests below (:func:`main`); naming one file of a
hub's ``schemas/`` folder instead moves that file alone.

:func:`validate` is a validator for the keywords these schemas use, and only
those: a keyword it does not know fails the check rather than being skipped,
so a hub schema that starts saying something new cannot pass unread.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"
#: The variable naming a hub checkout, whose ``schemas/`` folder holds every
#: file pinned here.
HUB_REPO_ENV = "MCGYVR_HUB_REPO"
#: The variable naming a directory of candidate hub schema files, read by
#: :func:`load` in place of the pinned copies without the pinned-copy digest
#: check.
UNDER_TEST_ENV = "MCGYVR_HUB_SCHEMA_UNDER_TEST"


@dataclass(frozen=True, kw_only=True)
class Pinned:
    """One of the hub's schema files and the copy pinned from it."""

    #: The file's name in the hub's ``schemas/`` folder.
    hub_name: str
    #: The pinned copy.
    fixture: Path
    #: The hub's file, byte for byte, that the copy was pinned from.
    hub_sha256: str
    #: :attr:`fixture`, byte for byte.
    pinned_sha256: str
    #: The variable naming the hub's file alone, for the drift check.
    env: str


PROTOCOL = Pinned(
    hub_name="protocol.schema.json",
    fixture=FIXTURES / "hub_protocol_v1.schema.json",
    hub_sha256="150dc990e6ef49aaa0b42a6e1dfa8f681a8dfa4f1bfce37567b3978fd252d6de",
    pinned_sha256="99c2dc1388a8560f13c98555251bbe231b6451c1e55580f66b96f4ec2047de8a",
    env="MCGYVR_HUB_SCHEMA",
)
RIDER = Pinned(
    hub_name="rider.schema.json",
    fixture=FIXTURES / "hub_rider_v1.schema.json",
    hub_sha256="a87cfed1a4f1ce2274d0af8eb21bc5b787521d7f231f5ad63efea361e73f0b33",
    pinned_sha256="6d86dae4e9a1eb112b5f0995553d36f00b3e5d7a6b0f797a24032325ae0c6ad9",
    env="MCGYVR_HUB_RIDER_SCHEMA",
)
#: Every hub schema pinned here.
PINS = (PROTOCOL, RIDER)

#: Keywords that say nothing about whether an instance is valid.
_ANNOTATIONS = frozenset(
    {"$schema", "$id", "title", "description", "default", "discriminator"}
)


class SchemaError(AssertionError):
    """An instance the schema refuses, and where."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pin(hub_file: bytes) -> bytes:
    """The hub's schema file as the pinned copy holds it."""
    schema = json.loads(hub_file)
    schema.pop("$id", None)
    return (json.dumps(schema, indent=2, sort_keys=True) + "\n").encode()


def load(pinned: Pinned = PROTOCOL) -> dict[str, Any]:
    """The schema the contract tests read: the candidate named by
    ``MCGYVR_HUB_SCHEMA_UNDER_TEST`` when it is set, else the pinned copy
    after checking it is the copy its digest names."""
    under_test = os.environ.get(UNDER_TEST_ENV)
    if under_test:
        data = (Path(under_test) / pinned.hub_name).read_bytes()
    else:
        data = pinned.fixture.read_bytes()
        if sha256(data) != pinned.pinned_sha256:
            raise SchemaError(
                f"{pinned.fixture.name} is not the pinned copy "
                f"(sha256 {sha256(data)}); "
                "re-pin it from the hub with `python -m tests.rig_schema`"
            )
    schema: dict[str, Any] = json.loads(data)
    return schema


def hub_file(pinned: Pinned, environ: Mapping[str, str] = os.environ) -> Path | None:
    """The hub's file ``pinned`` was pinned from, as the environment names
    it: the file's own variable, else the named hub checkout's ``schemas/``
    folder; ``None`` when neither is set."""
    named = environ.get(pinned.env)
    if named:
        return Path(named)
    repo = environ.get(HUB_REPO_ENV)
    if repo:
        return Path(repo) / "schemas" / pinned.hub_name
    return None


def validate(instance: Any, schema: dict[str, Any], ref: str) -> None:
    """Raise :class:`SchemaError` unless ``instance`` is valid against ``ref``."""
    _check(instance, _resolve(schema, ref), schema, ref)


def _resolve(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise SchemaError(f"only local references are followed, not {ref!r}")
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part]
    if not isinstance(node, dict):
        raise SchemaError(f"{ref} is not a schema")
    return node


def _type_ok(instance: Any, name: str) -> bool:
    if name == "object":
        return isinstance(instance, dict)
    if name == "array":
        return isinstance(instance, list)
    if name == "string":
        return isinstance(instance, str)
    if name == "integer":
        return type(instance) is int
    if name == "number":
        return type(instance) in (int, float)
    if name == "boolean":
        return type(instance) is bool
    if name == "null":
        return instance is None
    raise SchemaError(f"unknown type {name!r}")


def _pattern_ok(pattern: str, text: str) -> bool:
    # ECMA-262 `$` (no multiline) is the end of input; Python's `$` also
    # matches before a final newline, so an anchored pattern is held to `\Z`.
    if pattern.endswith("$") and not pattern.endswith("\\$"):
        pattern = pattern[:-1] + r"\Z"
    return re.search(pattern, text) is not None


def _check(instance: Any, node: dict[str, Any], root: dict[str, Any], at: str) -> None:
    def fail(why: str) -> None:
        raise SchemaError(f"{at}: {why}")

    for key, value in node.items():
        if key in _ANNOTATIONS or key.startswith("x-") or key == "$defs":
            continue
        if key == "$ref":
            _check(instance, _resolve(root, value), root, at)
        elif key in ("anyOf", "oneOf"):
            passed = 0
            for branch in value:
                try:
                    _check(instance, branch, root, at)
                except SchemaError:
                    continue
                passed += 1
            if passed == 0 or (key == "oneOf" and passed != 1):
                fail(f"{key}: {passed} of {len(value)} branches hold")
        elif key == "type":
            if not _type_ok(instance, value):
                fail(f"not of type {value}")
        elif key == "const":
            if instance != value or type(instance) is not type(value):
                fail(f"is not {value!r}")
        elif key == "enum":
            if instance not in value:
                fail(f"is not one of {value!r}")
        elif key == "required":
            if isinstance(instance, dict):
                missing = [name for name in value if name not in instance]
                if missing:
                    fail(f"missing {missing}")
        elif key == "properties":
            if isinstance(instance, dict):
                for name, sub in value.items():
                    if name in instance:
                        _check(instance[name], sub, root, f"{at}.{name}")
        elif key == "additionalProperties":
            if value is False:
                if isinstance(instance, dict):
                    unknown = sorted(set(instance) - set(node.get("properties", {})))
                    if unknown:
                        fail(f"{unknown} are not among its properties")
            elif value is not True:
                fail("additionalProperties other than true or false is not read here")
        elif key == "items":
            if isinstance(instance, list):
                for i, item in enumerate(instance):
                    _check(item, value, root, f"{at}[{i}]")
        elif key == "maxItems":
            if isinstance(instance, list) and len(instance) > value:
                fail(f"more than {value} items")
        elif key == "minItems":
            if isinstance(instance, list) and len(instance) < value:
                fail(f"fewer than {value} items")
        elif key == "maxLength":
            if isinstance(instance, str) and len(instance) > value:
                fail(f"longer than {value}")
        elif key == "minLength":
            if isinstance(instance, str) and len(instance) < value:
                fail(f"shorter than {value}")
        elif key == "pattern":
            if isinstance(instance, str) and not _pattern_ok(value, instance):
                fail(f"does not match {value}")
        elif key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
            if type(instance) in (int, float):
                ok = {
                    "minimum": instance >= value,
                    "maximum": instance <= value,
                    "exclusiveMinimum": instance > value,
                    "exclusiveMaximum": instance < value,
                }[key]
                if not ok:
                    fail(f"{key} {value}")
        else:
            fail(f"keyword {key!r} is not read by this validator")


def _sources(argv: list[str]) -> list[tuple[Pinned, Path]]:
    """Each pin and the hub file the arguments name for it: a hub checkout
    (or its ``schemas/`` folder) names every one, a file the pin of its name."""
    found: list[tuple[Pinned, Path]] = []
    for arg in argv:
        path = Path(arg)
        if path.is_dir():
            folder = path / "schemas" if (path / "schemas").is_dir() else path
            found.extend((pinned, folder / pinned.hub_name) for pinned in PINS)
            continue
        by_name = [pinned for pinned in PINS if pinned.hub_name == path.name]
        if not by_name:
            names = ", ".join(pinned.hub_name for pinned in PINS)
            raise SystemExit(f"{arg}: not a hub schema pinned here ({names})")
        found.append((by_name[0], path))
    return found


def main(argv: list[str]) -> int:
    """Re-pin from the hub files ``argv`` names: write each copy, and the two
    digests of each into this file in place of the old ones. Every file is
    read and every digest found before anything is written, so a re-pin that
    fails leaves the copies and the digests as they were."""
    if not argv:
        print(
            "usage: python -m tests.rig_schema HUB_CHECKOUT | HUB_SCHEMA_FILE ...",
            file=sys.stderr,
        )
        return 2
    here = Path(__file__)
    source = here.read_text(encoding="utf-8")
    copies: list[tuple[Pinned, bytes, bytes]] = []
    for pinned, path in _sources(argv):
        hub_bytes = path.read_bytes()
        copies.append((pinned, hub_bytes, pin(hub_bytes)))
    for pinned, hub_bytes, copy in copies:
        for old, new in (
            (pinned.hub_sha256, sha256(hub_bytes)),
            (pinned.pinned_sha256, sha256(copy)),
        ):
            if source.count(f'"{old}"') != 1:
                raise SystemExit(f"{here.name}: digest {old} is not written once")
            source = source.replace(f'"{old}"', f'"{new}"')
    for pinned, hub_bytes, copy in copies:
        pinned.fixture.write_bytes(copy)
        print(f"{pinned.fixture.name}: hub {sha256(hub_bytes)} pinned {sha256(copy)}")
    here.write_text(source, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
