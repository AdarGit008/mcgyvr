"""Every engine's host memory figure is either shipped or read on the machine.

The host memory a server holds beyond the experts it keeps there is a figure
of its engine. For every engine a unit may name, mcgyvr either ships an
estimate of that figure (which the user's own value replaces), or names the
engine as one whose figure is read on the user's machine, for which nothing is
shipped. Never both, so no estimate stands in for a figure that is to be read;
never neither, so no engine's figure is left to nobody.

The engines are the ones that carry a ``runtime_resident_gb`` figure: the
shipped key plus the engines read on the machine, both from
:mod:`mcgyvr.derived`. A media engine (diffusers) prices its host memory as the
spec's stated ``ram_gb``, so it carries no such figure and is not in this set.
The shipped figures come from the shipped file.
"""

from __future__ import annotations

import json

import pytest

from mcgyvr import derived
from mcgyvr.serving import KNOWN_ENGINES

#: The engines that carry a ``runtime_resident_gb`` figure: the one shipped,
#: plus the ones read on the machine.
ENGINES = (derived.RUNTIME_RESIDENT_KEY, *derived.RUNTIME_RESIDENT_READ)


def shipped() -> set[str]:
    """The engines the shipped file states a host memory figure for."""
    document = json.loads(derived.shipped_path().read_text(encoding="utf-8"))
    return set(document["numbers"][derived.RUNTIME_RESIDENT]["values"])


def read_on_the_machine() -> tuple[str, ...]:
    """The engines whose host memory figure the module names as read on the machine."""
    named: tuple[str, ...] = tuple(getattr(derived, "RUNTIME_RESIDENT_READ", ()))
    return named


@pytest.mark.parametrize("engine", ENGINES)
def test_an_engines_figure_is_shipped_or_read_never_both_never_neither(
    engine: str,
) -> None:
    is_shipped = engine in shipped()
    is_read = engine in read_on_the_machine()
    assert is_shipped or is_read, (
        f"{engine}: its host memory figure is neither shipped nor read on the machine"
    )
    assert not (is_shipped and is_read), (
        f"{engine}: its host memory figure is shipped and also named as read on "
        "the machine"
    )


def test_only_engines_a_unit_may_name_are_read_on_the_machine() -> None:
    named = read_on_the_machine()
    assert len(named) == len(set(named)), named
    assert set(named) <= set(derived.KEY_SPACES["engine"]), named


def test_every_engine_a_unit_may_name_is_known_to_serving() -> None:
    """The config's engine choices are exactly the engines serving prices, so
    every engine a unit may name is accounted for: each is either a
    runtime_resident_gb carrier (ENGINES) or a media engine priced by ram_gb."""
    assert set(derived.KEY_SPACES["engine"]) == set(KNOWN_ENGINES), (
        "the config names engines serving does not price, or serving prices "
        "engines the config cannot name"
    )
    assert set(ENGINES) <= set(KNOWN_ENGINES)
