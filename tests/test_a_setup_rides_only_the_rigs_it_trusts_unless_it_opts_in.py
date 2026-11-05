"""Whose rigs may read what a setup sends when it rides is the setup's choice.

``ride_scope`` (``own``, ``crew`` or ``anyone``, the wire's scopes) bounds every
relief rung's requests: each names the narrower of its own block's scope and
the setup's, so a rung synced as ``anyone`` rides under ``crew`` until the setup
opts in. Unset is ``crew``: your own rigs and your crewmates'. ``anyone`` is
opted in with ``mcgyvr rig rungs sync --ride-scope anyone``, which writes the
policy line and shows the hub's privacy text as it does.

``private: true`` rides no relief rung at all: a sync refuses before the hub is
sent anything, a relief rung already kept is not ridden, and a ladder step or
a role naming one is refused.

Every hub here is a loopback server this test starts.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr import hubwire
from mcgyvr.config import RIDE_SCOPE, ConfigSchemaError, parse
from mcgyvr.exits import Exit
from tests.rigsyncs import (
    FIRST,
    POLICY,
    PRIVACY,
    Hub,
    a_syncing_hub,
    a_syncing_setup,
    cli,
)

RIDE = f"hitchhike-{FIRST}"
FLEET = """\
units:
  local:
    address: http://box.invalid:8080
    model: coder-7b
"""


def _relief(scope: str | None) -> str:
    stated = "" if scope is None else f"    scope: {scope}\n"
    return (
        f"relief:\n  {RIDE}:\n    address: https://hub.invalid/v1\n"
        f"    model: hitchhike@{FIRST}\n    api_key_env: MCGYVR_HUB_API_KEY\n"
        f"    width: 2\n    position: within\n{stated}"
    )


def _ridden(policy: str, scope: str | None) -> str:
    config = parse(f"{FLEET}ladder: [local]\n{policy}", relief_text=_relief(scope))
    return config.relief[RIDE].scope


# --- the wire's scopes, narrowest first ---------------------------------------


def test_the_narrowest_scope_is_the_one_every_other_allows() -> None:
    assert hubwire.SCOPE_VALUES == ("own", "crew", "anyone")
    assert hubwire.narrowest_scope("anyone", "crew") == "crew"
    assert hubwire.narrowest_scope("crew", "own", "anyone") == "own"
    assert hubwire.narrowest_scope("anyone") == "anyone"
    with pytest.raises(ValueError):
        hubwire.narrowest_scope("everyone", "crew")


# --- what a setup rides under ---------------------------------------------------


def test_unset_a_setup_rides_its_own_and_its_crewmates_rigs_only() -> None:
    assert RIDE_SCOPE == hubwire.SCOPE_CREW
    assert parse(f"{FLEET}ladder: [local]\n").ride_scope == hubwire.SCOPE_CREW
    for scope in (None, hubwire.SCOPE_ANYONE, hubwire.SCOPE_CREW):
        assert _ridden("", scope) == hubwire.SCOPE_CREW


@pytest.mark.parametrize("block", [None, *hubwire.SCOPE_VALUES])
@pytest.mark.parametrize("setup", hubwire.SCOPE_VALUES)
def test_a_rung_rides_under_the_narrower_of_its_block_and_the_setup(
    setup: str, block: str | None
) -> None:
    expected = hubwire.narrowest_scope(block or setup, setup)

    assert _ridden(f"ride_scope: {setup}\n", block) == expected


def test_a_ride_scope_the_wire_does_not_name_is_refused() -> None:
    with pytest.raises(ConfigSchemaError, match=r"ride_scope.*Valid"):
        parse(f"{FLEET}ladder: [local]\nride_scope: everyone\n")


def test_every_ride_names_the_setups_ride_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr import runner
    from mcgyvr.local_pool import source_map

    monkeypatch.setenv("MCGYVR_HUB_API_KEY", "mhu_" + "k" * 40)
    setup = f"{FLEET}ladder: [local]\nfanout: idle\n"
    for policy, sent in (("", "crew"), ("ride_scope: own\n", "own")):
        pool = source_map(parse(setup + policy, relief_text=_relief("anyone")))
        (ride,) = pool.relief
        headers = runner.request_headers(pool.bind(ride.name))
        assert headers[hubwire.SCOPE_HEADER] == sent


# --- a private setup ----------------------------------------------------------


def test_a_private_setup_rides_no_relief_rung_it_keeps() -> None:
    from mcgyvr.local_pool import source_map

    config = parse(
        f"{FLEET}ladder: [local]\nfanout: idle\nprivate: true\n",
        relief_text=_relief("anyone"),
    )

    assert config.private is True
    assert config.relief == {}
    assert source_map(config).relief == ()


@pytest.mark.parametrize(
    "binds",
    [f"ladder: [local, {RIDE}]\n", f"ladder: [local]\nverifier: {{unit: {RIDE}}}\n"],
)
def test_a_private_setup_naming_a_relief_rung_is_refused(binds: str) -> None:
    with pytest.raises(ConfigSchemaError, match=rf"private: true.*{RIDE}"):
        parse(f"{FLEET}{binds}private: true\n", relief_text=_relief(None))


# --- the sync -------------------------------------------------------------------


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return a_syncing_setup(tmp_path, monkeypatch)


@pytest.fixture
def hub(setup: Path) -> Iterator[Hub]:
    with a_syncing_hub(setup) as made:
        yield made


def _kept(setup: Path) -> dict[str, Any]:
    text = (setup / "relief.yaml").read_text(encoding="utf-8")
    return dict(yaml.safe_load(text)["relief"])


def _policy(setup: Path) -> str:
    return (setup / "policy.yaml").read_text(encoding="utf-8")


def test_a_sync_writes_the_setups_ride_scope_and_says_whose_rigs_ride(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.answer(hub.listing(FIRST))

    assert cli() == Exit.OK

    assert [r["scope"] for r in _kept(setup).values()] == ["crew"]
    out = capsys.readouterr().out
    assert PRIVACY in out
    assert "ride scope: crew" in out and "--ride-scope anyone" in out
    assert "opted in" not in out
    assert _policy(setup) == POLICY  # nothing asked of the policy


def test_opting_in_to_anyone_writes_the_policy_and_shows_the_privacy_text(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.answer(hub.listing(FIRST))

    assert cli("--ride-scope", "anyone") == Exit.OK

    assert _policy(setup) == POLICY + "ride_scope: anyone\n"  # the rest kept
    assert [r["scope"] for r in _kept(setup).values()] == ["anyone"]
    out = capsys.readouterr().out
    assert "ride scope: crew (unset) -> anyone" in out
    assert out.index("opted in") < out.index(PRIVACY)
    from mcgyvr.config import load

    assert load(setup).relief[RIDE].scope == "anyone"


def test_opting_in_again_rewrites_nothing_and_narrowing_back_is_one_line(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.answer(hub.listing(FIRST))
    assert cli("--ride-scope", "anyone") == Exit.OK
    capsys.readouterr()

    assert cli("--ride-scope", "anyone") == Exit.OK
    assert "opted in" not in capsys.readouterr().out
    assert cli("--ride-scope", "own") == Exit.OK

    assert _policy(setup) == POLICY + "ride_scope: own\n"
    assert [r["scope"] for r in _kept(setup).values()] == ["own"]
    assert "ride scope: anyone -> own" in capsys.readouterr().out


def test_an_opt_in_the_hub_refuses_writes_nothing(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.answer({"error": {"message": "no"}}, status=500)

    assert cli("--ride-scope", "anyone") != Exit.OK

    assert _policy(setup) == POLICY
    assert not (setup / "relief.yaml").exists()


@pytest.mark.parametrize("argv", [(), ("--ride-scope", "anyone")])
def test_a_private_setup_refuses_to_sync_and_sends_the_hub_nothing(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str], argv: tuple[str, ...]
) -> None:
    (setup / "policy.yaml").write_text(POLICY + "private: true\n", encoding="utf-8")
    hub.answer(hub.listing(FIRST))

    assert cli(*argv) == Exit.REFUSED

    assert hub.asked == []
    assert "private" in capsys.readouterr().err
    assert _policy(setup) == POLICY + "private: true\n"
    assert not (setup / "relief.yaml").exists()


def test_the_rigs_refresher_syncs_nothing_for_a_private_setup(
    setup: Path, hub: Hub
) -> None:
    from mcgyvr.rig import rungs

    (setup / "policy.yaml").write_text(POLICY + "private: true\n", encoding="utf-8")
    hub.answer(hub.listing(FIRST))
    said: list[str] = []
    refresher = rungs.refresher_for(hub.address, folder=setup)
    assert refresher is not None
    refresher._say = said.append  # what it tells the rig's log
    refresher._start = lambda work: work()  # on this thread

    refresher.tick()

    assert hub.asked == []
    assert len(said) == 1 and "private" in said[0]


def test_an_opt_in_repairs_a_kept_relief_file_as_a_plain_sync_does(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    (setup / "relief.yaml").write_text("relief: [not, a, map]\n", encoding="utf-8")
    hub.answer(hub.listing(FIRST))

    assert cli("--ride-scope", "anyone") == Exit.OK

    assert _policy(setup) == POLICY + "ride_scope: anyone\n"
    assert [r["scope"] for r in _kept(setup).values()] == ["anyone"]
