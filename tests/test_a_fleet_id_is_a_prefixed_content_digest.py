"""A fleet identity is a prefixed digest of what it covers, and nothing else.

RED. ``mcgyvr.fleet.ids`` does not exist on this branch. The intent is
``records/plans/fleet-identity.md`` §1.

Three kinds are content-addressed and share one primitive, the shape
``Config.digest()`` already has (``src/mcgyvr/config.py:1092``: a prefix plus
the sha256 of a canonical tree): ``unt-`` a unit, ``rig-`` a rig and ``cmb-`` a
combination. Content-addressed, so two processes computing the same inputs
agree without talking, and any change to an input is a new name.

A fleet is not one of them. ``flt-05`` is a name, pinned in its lock file to
the sha256 of its layout (§1, §4). The model spec, rig shape and fleet shape of
the five-id design are gone (owner, 2026-09-10 and 2026-09-11), and so is the
config digest as an approval key; their prefixes are refused, so a record
written under the old design cannot pass for a current one.
"""

from __future__ import annotations

import importlib
import re
from typing import Any

import pytest

from tests.red_port.conftest import required

#: unit, rig, combination.
PREFIXES = ("unt-", "rig-", "cmb-")
IDENTITY = re.compile(r"^(unt|rig|cmb)-[0-9a-f]{64}$")


def _digest() -> Any:
    return required(
        "name a fleet identity as its kind's prefix plus a sha256 of its "
        "canonical fields",
        lambda: importlib.import_module("mcgyvr.fleet.ids").digest,
    )


def test_every_identity_kind_carries_its_own_prefix() -> None:
    digest = _digest()
    for prefix in PREFIXES:
        named = digest(prefix, {"host": "srv2"})
        assert named.startswith(prefix), f"{prefix} identity reads {named!r}"
        assert IDENTITY.match(named), f"not prefix + sha256: {named!r}"


def test_key_order_does_not_change_an_identity() -> None:
    """Canonical, not textual: a dict built in another order is the same thing."""
    digest = _digest()
    one = digest("rig-", {"host": "srv1", "hw": {"gpu": "GTX 1660", "vram": 6144}})
    two = digest("rig-", {"hw": {"vram": 6144, "gpu": "GTX 1660"}, "host": "srv1"})
    assert one == two


def test_any_changed_or_added_field_is_a_new_identity() -> None:
    digest = _digest()
    base = digest("rig-", {"host": "srv1", "driver": "580.173.02"})
    assert digest("rig-", {"host": "srv1", "driver": "580.173.03"}) != base
    assert digest("rig-", {"host": "srv1", "driver": "580.173.02", "x": 1}) != base


def test_a_retired_or_unknown_prefix_is_refused() -> None:
    """``msp-``, ``rsh-`` and ``fsh-`` named the dropped design; ``cfg-`` is the
    config's digest, which no longer keys an approval."""
    digest = _digest()
    for prefix in ("msp-", "rsh-", "fsh-", "cfg-", "flt-"):
        with pytest.raises(ValueError, match=prefix):
            digest(prefix, {"host": "srv1"})
