"""The hub's published schemas as the product ships them, and a check of them.

The hub publishes the contracts the agent speaks as JSON Schemas (draft
2020-12): its agent protocol, and the REST API a rider's agent uses beside it.
The product ships both inside its package (:data:`mcgyvr.hubwire.SCHEMAS`),
byte for byte the hub's files, and defines the values both sides share once,
in :mod:`mcgyvr.hubwire`; the hub imports them and renders its schemas equal
to these. The agent does not read the schemas at run time: it states the few
limits it needs (:mod:`mcgyvr.hubwire`, :mod:`mcgyvr.rig.protocol`,
:mod:`mcgyvr.rig.udpwire`), and these tests hold those limits, and every
message the agent writes, to the shipped schema (:data:`SCHEMAS`):

* :data:`PROTOCOL`, ``protocol.schema.json``;
* :data:`RIDER`, ``rider.schema.json``.

A hub checkout is compared with them when one is named (:func:`hub_file`):
``MCGYVR_HUB_REPO``, a hub checkout, names every file at once (its
``schemas/`` folder; the real-hub test,
``tests/test_a_real_hub_runs_a_unit_per_card_of_a_real_agent.py``, reads the
same variable and runs that checkout's hub), and each file's own variable
(``MCGYVR_HUB_SCHEMA``, ``MCGYVR_HUB_RIDER_SCHEMA``) names that file alone,
before it. A hub whose file is not the shipped one byte for byte then fails
here instead of on the wire.
Naming ``MCGYVR_HUB_REPO`` runs that real-hub test too, which fails on a
checkout without its built ``.venv`` (``uv sync`` in it): a run that checks
the schemas alone names each file by its own variable instead.

A hub's CI can run the agent's contract tests against a schema it is about to
publish: ``MCGYVR_HUB_SCHEMA_UNDER_TEST`` names a directory holding the hub's
schema files (its ``schemas/`` folder, or any directory containing
``protocol.schema.json`` and ``rider.schema.json``). :func:`load` then reads
``<dir>/<name>`` instead of the shipped schema, so a candidate that moved a
value the agent reads fails the contract assertion that reads it.

:func:`validate` is a validator for the keywords these schemas use, and only
those: a keyword it does not know fails the check rather than being skipped,
so a hub schema that starts saying something new cannot pass unread.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcgyvr import hubwire

#: The variable naming a hub checkout, whose ``schemas/`` folder holds every
#: file shipped here.
HUB_REPO_ENV = "MCGYVR_HUB_REPO"
#: The variable naming a directory of candidate hub schema files, read by
#: :func:`load` in place of the shipped ones.
UNDER_TEST_ENV = "MCGYVR_HUB_SCHEMA_UNDER_TEST"


@dataclass(frozen=True, kw_only=True)
class Published:
    """One of the hub's schema files, as the product ships it."""

    #: The file's name in the hub's ``schemas/`` folder and in the package.
    hub_name: str
    #: The variable naming the hub's file alone, for the comparison.
    env: str

    def shipped(self) -> bytes:
        """The product's copy, byte for byte."""
        return hubwire.schema_bytes(self.hub_name)


PROTOCOL = Published(hub_name=hubwire.PROTOCOL_SCHEMA, env="MCGYVR_HUB_SCHEMA")
RIDER = Published(hub_name=hubwire.RIDER_SCHEMA, env="MCGYVR_HUB_RIDER_SCHEMA")
#: Every hub schema the product ships.
SCHEMAS = (PROTOCOL, RIDER)

#: Keywords that say nothing about whether an instance is valid.
_ANNOTATIONS = frozenset(
    {"$schema", "$id", "title", "description", "default", "discriminator"}
)


class SchemaError(AssertionError):
    """An instance the schema refuses, and where."""


def load(published: Published = PROTOCOL) -> dict[str, Any]:
    """The schema the contract tests read: the candidate named by
    ``MCGYVR_HUB_SCHEMA_UNDER_TEST`` when it is set, else the shipped one."""
    under_test = os.environ.get(UNDER_TEST_ENV)
    if under_test:
        data = (Path(under_test) / published.hub_name).read_bytes()
    else:
        data = published.shipped()
    schema: dict[str, Any] = json.loads(data)
    return schema


def hub_file(
    published: Published, environ: Mapping[str, str] = os.environ
) -> Path | None:
    """The hub's file ``published`` is compared with, as the environment
    names it: the file's own variable, else the named hub checkout's
    ``schemas/`` folder; ``None`` when neither is set."""
    named = environ.get(published.env)
    if named:
        return Path(named)
    repo = environ.get(HUB_REPO_ENV)
    if repo:
        return Path(repo) / "schemas" / published.hub_name
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
        elif key == "uniqueItems":
            if value is True and isinstance(instance, list):
                seen = [json.dumps(item, sort_keys=True) for item in instance]
                if len(set(seen)) != len(seen):
                    fail("an item twice")
            elif value is not True:
                fail("uniqueItems other than true is not read here")
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
