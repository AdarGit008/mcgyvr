"""The hub's protocol schema as the rig agent's tests hold it, and a check of it.

The hub publishes its agent protocol as one JSON Schema (draft 2020-12),
written from its own message models. The agent does not copy that schema into
its code: it states the few limits it needs (:mod:`mcgyvr.rig.protocol`), and
these tests hold those limits and every frame the agent writes to a pinned
copy of the hub's file.

The pinned copy is ``tests/fixtures/hub_protocol_v1.schema.json``: the hub's
file with its ``$id`` left out (an address that names no machine of ours, and
that no ``$ref`` in the file uses), written back the way the hub writes it.
Two digests pin it. :data:`HUB_SCHEMA_SHA256` is the hub's file as the hub
publishes it; :data:`PINNED_SHA256` is the copy here. An edit to the copy that
did not come from the hub fails on the second. Pointing ``MCGYVR_HUB_SCHEMA``
at a hub checkout's ``schemas/protocol.schema.json`` checks the first, and
that the copy is that file pinned, so a hub that moved its schema fails here
instead of on the wire.

To move to a new hub schema::

    uv run --no-sync python -m tests.rig_schema /path/to/protocol.schema.json

rewrites the copy and prints both digests to paste below.

:func:`validate` is a validator for the keywords this schema uses, and only
those: a keyword it does not know fails the check rather than being skipped,
so a hub schema that starts saying something new cannot pass unread.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).parent / "fixtures" / "hub_protocol_v1.schema.json"

#: The hub's ``schemas/protocol.schema.json``, byte for byte, that the copy
#: was pinned from.
HUB_SCHEMA_SHA256 = "111b96ea467e0651790eb242888f31bc9ec9befed0c8280946adbf7974f42e9f"
#: :data:`FIXTURE`, byte for byte.
PINNED_SHA256 = "d02ed58fec7f4dcac939f9c01b4296c74996cfaa0a06169aefcb01951610e349"

#: The variable naming a hub checkout's schema file, for the drift check.
HUB_SCHEMA_ENV = "MCGYVR_HUB_SCHEMA"

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


def load() -> dict[str, Any]:
    """The pinned schema, after checking it is the copy the digest names."""
    data = FIXTURE.read_bytes()
    if sha256(data) != PINNED_SHA256:
        raise SchemaError(
            f"{FIXTURE.name} is not the pinned copy (sha256 {sha256(data)}); "
            "re-pin it from the hub with `python -m tests.rig_schema`"
        )
    schema: dict[str, Any] = json.loads(data)
    return schema


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
            if value is not True:
                fail("additionalProperties other than true is not read here")
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


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m tests.rig_schema HUB_SCHEMA_FILE", file=sys.stderr)
        return 2
    hub_file = Path(argv[0]).read_bytes()
    pinned = pin(hub_file)
    FIXTURE.write_bytes(pinned)
    print(f'HUB_SCHEMA_SHA256 = "{sha256(hub_file)}"')
    print(f'PINNED_SHA256 = "{sha256(pinned)}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
