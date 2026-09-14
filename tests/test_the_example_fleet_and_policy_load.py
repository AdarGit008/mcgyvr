"""The shipped fleet/policy examples load, so copying one copies a valid setup.

``examples/fleet.yaml`` and ``examples/policy.yaml`` are the templates an
operator copies into a setup directory and edits. A template that does not
load through :mod:`mcgyvr.fleet.files` is a shape nobody checked, and the one
thing a first run must not do is hand a stranger a file that refuses to parse
— so both are read through the real loader here, exactly as ``mcgyvr init``
reads the file it wrote. The contract examples hold the same contract in
``tests/test_an_unconfigured_machine_says_where_setup_lives.py``: examples are
validated, never merely shipped.
"""

from __future__ import annotations

from pathlib import Path

from mcgyvr.fleet.files import load_fleet, load_policy

REPO = Path(__file__).resolve().parent.parent


def test_the_example_fleet_loads() -> None:
    """``examples/fleet.yaml`` is a valid fleet file with the three blocks."""
    text = (REPO / "examples" / "fleet.yaml").read_text(encoding="utf-8")
    fleet = load_fleet(text)
    assert set(fleet) == {"profile", "units", "rigs", "fleets"}
    assert fleet["profile"] in {"live", "dev"}
    assert fleet["units"], "the example names no units"
    assert fleet["fleets"], "the example names no fleets"


def test_the_example_policy_loads() -> None:
    """``examples/policy.yaml`` names a ladder over the example's units."""
    text = (REPO / "examples" / "policy.yaml").read_text(encoding="utf-8")
    policy = load_policy(text)
    assert policy["ladder"], "the example policy names no ladder"
    for name in policy["ladder"]:
        assert isinstance(name, str) and name
