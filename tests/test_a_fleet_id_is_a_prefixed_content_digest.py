"""A fleet identity is a prefixed digest of what it covers, and nothing else.

RED. ``mcgyvr.fleet`` does not exist on this branch. The intent is
``records/plans/fleet-identity.md``, rule ID-1.

Five identities share one primitive, the shape ``Config.digest()`` already has
(``src/mcgyvr/config.py:1092``: ``cfg-`` plus the sha256 of a canonical tree): a
prefix that says which kind of thing is named, then a digest of the fields that
define it. Content-addressed, so two processes computing the same inputs agree
without talking, and any change to an input is a new name — which is the
property every approval and every observation record is keyed through.
"""

from __future__ import annotations

import importlib
import re
from typing import Any

import pytest

from tests.red_port.conftest import required

#: model spec, unit, rig, rig shape, fleet shape.
PREFIXES = ("msp-", "unt-", "rig-", "rsh-", "fsh-")
IDENTITY = re.compile(r"^(msp|unt|rig|rsh|fsh)-[0-9a-f]{64}$")


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


def test_a_prefix_outside_the_five_kinds_is_refused() -> None:
    """``cfg-`` is the config's; a sixth kind is a design change, not a typo."""
    digest = _digest()
    with pytest.raises(ValueError):
        digest("cfg-", {"host": "srv1"})
