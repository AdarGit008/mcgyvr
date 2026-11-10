"""Who may use a rig is one vocabulary: ``own``, ``crew`` or ``anyone``.

A unit's ``scope``, the setup's ``ride_scope`` and each rig on a hub name an
audience from ``hubwire.SCOPE_VALUES``. How a rig takes part is its mode,
``lend`` or ``hitchhike`` (``hubwire.MODES``), never an audience value. The
pool a rig is in is ``hubwire.rig_pool`` of the two: the three audience pools
carry the audience's own name, a hitchhike rig is in the hitchhike pool, and
under ``own`` a rig lends to nobody whatever its mode. A hitchhike rig is never
a crew's alone.

The old words are refused with the one to write, never read as an alias: the
hub's sharing modes ``solo``, ``crew``, ``pool`` and ``hitchhike`` each name an
audience and a mode (``hubwire.RETIRED_SHARING_MODES``), and ``solo``, ``pool``
and ``general`` written where an audience goes are refused naming ``own`` or
``anyone``, by the config and by ``mcgyvr rig rungs sync --ride-scope``.
"""

from __future__ import annotations

import pytest

from mcgyvr import docgen, hubwire
from mcgyvr.cli.dispatcher import main
from mcgyvr.config import ConfigSchemaError, parse
from tests.rigsyncs import FIRST

HUB = "https://hub.example.org/v1"
KEY_ENV = "MCGYVR_HUB_API_KEY"
RIDE = f"hitchhike-{FIRST}"


@pytest.fixture(autouse=True)
def _keyed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY_ENV, "mhu_" + "k" * 40)


# --- the wire ---------------------------------------------------------------------


def test_the_three_audience_pools_carry_the_audiences_name() -> None:
    assert (hubwire.POOL_OWN, hubwire.POOL_CREW, hubwire.POOL_ANYONE) == (
        hubwire.SCOPE_VALUES
    )
    assert set(hubwire.SCOPE_VALUES) < set(hubwire.POOLS)
    assert set(hubwire.MODES).isdisjoint(hubwire.SCOPE_VALUES)
    assert dict(hubwire.SCOPE_POOLS) == {s: s for s in hubwire.SCOPE_VALUES}
    assert tuple(hubwire.POOL_NAMES) == hubwire.POOLS


@pytest.mark.parametrize(
    ("audience", "mode", "pool"),
    [
        ("own", "lend", "own"),
        ("crew", "lend", "crew"),
        ("anyone", "lend", "anyone"),
        ("own", "hitchhike", "own"),
        ("anyone", "hitchhike", "hitchhike"),
    ],
)
def test_a_rigs_audience_and_mode_name_its_pool(
    audience: str, mode: str, pool: str
) -> None:
    assert hubwire.rig_pool(audience, mode) == pool


def test_a_hitchhike_rig_is_never_a_crews_alone() -> None:
    with pytest.raises(ValueError, match="takes audience own or anyone, not 'crew'"):
        hubwire.rig_pool("crew", "hitchhike")


@pytest.mark.parametrize(
    ("audience", "mode"), [("anyone", "pool"), ("general", "lend")]
)
def test_a_pair_of_no_known_words_names_no_pool(audience: str, mode: str) -> None:
    with pytest.raises(ValueError):
        hubwire.rig_pool(audience, mode)


@pytest.mark.parametrize(
    ("old", "pool"),
    [("solo", "own"), ("crew", "crew"), ("pool", "anyone"), ("hitchhike", "hitchhike")],
)
def test_each_old_sharing_mode_is_the_pair_that_puts_a_rig_in_its_pool(
    old: str, pool: str
) -> None:
    audience, mode = hubwire.RETIRED_SHARING_MODES[old]

    assert hubwire.rig_pool(audience, mode) == pool


@pytest.mark.parametrize(
    ("old", "new"), [("solo", "own"), ("pool", "anyone"), ("general", "anyone")]
)
def test_an_old_audience_word_is_refused_naming_the_new_one(old: str, new: str) -> None:
    said = hubwire.retired_audience(old)

    assert said is not None
    assert f"`{old}` is no longer an audience: write `{new}`" in said


@pytest.mark.parametrize("value", [*hubwire.SCOPE_VALUES, "everyone"])
def test_a_current_or_unknown_word_is_no_retired_audience(value: str) -> None:
    assert hubwire.retired_audience(value) is None


# --- the config -------------------------------------------------------------------


def _fleet(scope: str) -> str:
    return f"""\
units:
  local:
    address: http://box.invalid:8080
    model: coder-7b
  pool_coder:
    address: {HUB}
    model: coder-32b
    api_key_env: {KEY_ENV}
    scope: {scope}
ladder: [local]
"""


def _relief(scope: str) -> str:
    return f"""\
relief:
  {RIDE}:
    address: {HUB}
    model: hitchhike@{FIRST}
    api_key_env: {KEY_ENV}
    width: 2
    position: below_floor
    scope: {scope}
"""


@pytest.mark.parametrize(
    ("old", "new"), [("solo", "own"), ("pool", "anyone"), ("general", "anyone")]
)
def test_a_units_scope_in_an_old_word_is_refused_naming_the_new_one(
    old: str, new: str
) -> None:
    with pytest.raises(ConfigSchemaError, match=f"write `{new}`") as refused:
        parse(_fleet(old))

    assert "units.pool_coder.scope" in str(refused.value)


def test_a_ride_scope_in_an_old_word_is_refused_naming_the_new_one() -> None:
    with pytest.raises(ConfigSchemaError, match="ride_scope: `general` is no longer"):
        parse(_fleet("own") + "ride_scope: general\n")


def test_a_relief_rungs_scope_in_an_old_word_is_refused_naming_the_new_one() -> None:
    with pytest.raises(ConfigSchemaError, match="`solo` is no longer an audience"):
        parse(_fleet("own"), relief_text=_relief("solo"))


def test_any_other_wrong_scope_is_refused_as_before() -> None:
    with pytest.raises(ConfigSchemaError, match=r"is not a valid value\. Valid: own"):
        parse(_fleet("everyone"))


# --- the rig verb -----------------------------------------------------------------


def test_the_ride_scope_flag_refuses_an_old_word_naming_the_new_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as refused:
        main(["rig", "rungs", "sync", "--ride-scope", "general"])

    assert refused.value.code == 2
    assert (
        "`general` is no longer an audience: write `anyone`" in capsys.readouterr().err
    )


# --- the docs ---------------------------------------------------------------------


def test_the_setup_text_maps_each_audience_and_mode_to_its_pool() -> None:
    text = docgen.render_setup()

    for mode in hubwire.MODES:
        for audience in hubwire.MODE_AUDIENCES[mode]:
            name = hubwire.POOL_NAMES[hubwire.rig_pool(audience, mode)]
            assert f"| `{audience}` | `{mode}` | {name} |" in text
    assert "`pool` is `anyone` + `lend`" in text
    assert "approved you as a host" in text
