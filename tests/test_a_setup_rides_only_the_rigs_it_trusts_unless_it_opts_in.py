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

A ride the hub refuses as outside the scope it names (``403 out_of_scope``)
is a full rung, not the rung's error: one note says which rung, under which
scope, and how to opt in; the climb moves on with no attempt spent; and the
rung is not asked again in the process, since every refusal spends the
rider's hub budget. The rig's refresher says whose rigs ride once, as a sync
does, and under ``own`` the sync says no relief rung serves the setup.

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


@pytest.fixture(autouse=True)
def nothing_refused_yet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with no rung held out as out of scope: the runner
    keeps them for its process."""
    from mcgyvr import runner

    monkeypatch.setattr(runner, "_OUT_OF_SCOPE_RUNGS", set())


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
    from mcgyvr.ladder_map import unit_map

    monkeypatch.setenv("MCGYVR_HUB_API_KEY", "mhu_" + "k" * 40)
    setup = f"{FLEET}ladder: [local]\nfanout: idle\n"
    for policy, sent in (("", "crew"), ("ride_scope: own\n", "own")):
        pool = unit_map(parse(setup + policy, relief_text=_relief("anyone")))
        (ride,) = pool.relief
        headers = runner.request_headers(pool.bind(ride.name))
        assert headers[hubwire.SCOPE_HEADER] == sent


# --- a private setup ----------------------------------------------------------


def test_a_private_setup_rides_no_relief_rung_it_keeps() -> None:
    from mcgyvr.ladder_map import unit_map

    config = parse(
        f"{FLEET}ladder: [local]\nfanout: idle\nprivate: true\n",
        relief_text=_relief("anyone"),
    )

    assert config.private is True
    assert config.relief == {}
    assert unit_map(config).relief == ()


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


def test_under_own_the_sync_says_no_relief_rung_serves_the_setup(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    (setup / "policy.yaml").write_text(POLICY + "ride_scope: own\n", encoding="utf-8")
    hub.answer(hub.listing(FIRST))

    assert cli() == Exit.OK

    out = capsys.readouterr().out
    assert "ride scope: own: " in out and "no relief rung serves it" in out


def test_the_rigs_refresher_says_whose_rigs_ride_once_as_the_sync_does(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.rig import rungs

    hub.answer(hub.listing(FIRST))
    assert cli() == Exit.OK
    (line,) = [
        each
        for each in capsys.readouterr().out.splitlines()
        if each.startswith("ride scope: ")
    ]
    said: list[str] = []
    refresher = rungs.refresher_for(hub.address, folder=setup)
    assert refresher is not None
    refresher._say = said.append  # what it tells the rig's log
    refresher._start = lambda work: work()  # on this thread

    refresher.tick()
    refresher._due = None  # due again at once
    refresher.tick()

    assert said == [line]
    assert [r["scope"] for r in _kept(setup).values()] == ["crew"]


# --- a ride the hub refuses as outside the setup's scope -------------------------

OUT_OF_SCOPE = (403, "out_of_scope")


def _refusing_hub_setup(
    hub: str, other: str, fast: str = "http://fast.invalid/v1"
) -> str:
    return f"""
units:
  local_fast:
    address: {fast}
    model: {FAST_MODEL}
    width: 1
    window: 32768
    output_tokens: 256
  api_big:
    address: {other}
    model: {OTHER_MODEL}
    api_key_env: HUB_KEY
    width: 1
    window: 32768
ladder: [local_fast, {RIDE}, api_big]
max_escalations: 3
relief:
  {RIDE}:
    address: {hub}
    model: hitchhike@{FIRST}
    api_key_env: HUB_KEY
    width: 1
    position: within
"""


FAST_MODEL = "qwen2.5-coder-3b"
OTHER_MODEL = "vendor-large"


@pytest.fixture
def hub_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_KEY", "mhu_" + "1" * 16)


def _notes(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return [line for line in capsys.readouterr().err.splitlines() if line.strip()]


@pytest.mark.usefixtures("hub_key")
def test_a_relief_rung_refused_as_out_of_scope_is_full_asked_once_and_said(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.capacity import Capacity, SlotUnavailableError
    from mcgyvr.ladder_map import unit_map
    from mcgyvr.runner import ReliefUnavailableError, Request, RunnerError, dispatch
    from tests.rungs import answering_unplaced, error

    assert hubwire.OUT_OF_SCOPE == OUT_OF_SCOPE
    seen: list[str] = []
    outcomes: list[BaseException] = []
    with answering_unplaced(*error(*OUT_OF_SCOPE), seen) as address:
        config = parse(_refusing_hub_setup(address, "http://other.invalid/v1"))
        capacity = Capacity.of(config, root=tmp_path / "slots")
        for _ in range(2):
            try:
                dispatch(
                    unit_map(config),
                    RIDE,
                    Request(prompt="hello", max_output_tokens=8),
                    capacity=capacity,
                )
            except Exception as exc:
                outcomes.append(exc)

    assert len(outcomes) == 2
    for outcome in outcomes:
        assert isinstance(outcome, ReliefUnavailableError)
        assert isinstance(outcome, SlotUnavailableError)
        # Not a runner error, so the cooldown does not learn the rung as failing.
        assert not isinstance(outcome, RunnerError)
    assert seen == [f"hitchhike@{FIRST}"], "the hub was asked once, not again"
    assert capacity.load(RIDE) == 0, "the slot it held is given back"
    (said,) = _notes(capsys)
    assert said.startswith("note: ") and repr(RIDE) in said
    assert "ride_scope (crew)" in said
    assert "mcgyvr rig rungs sync --ride-scope anyone" in said
    assert "hello" not in said


@pytest.mark.usefixtures("hub_key")
def test_a_unit_refused_as_out_of_scope_is_still_its_error(tmp_path: Path) -> None:
    from mcgyvr.capacity import Capacity
    from mcgyvr.ladder_map import unit_map
    from mcgyvr.runner import BackendError, Request, dispatch
    from tests.rungs import answering_unplaced, error

    seen: list[str] = []
    with answering_unplaced(*error(*OUT_OF_SCOPE), seen) as address:
        config = parse(_refusing_hub_setup("http://hub.invalid/v1", address))
        capacity = Capacity.of(config, root=tmp_path / "slots")
        with pytest.raises(BackendError) as raised:
            dispatch(
                unit_map(config),
                "api_big",
                Request(prompt="hello", max_output_tokens=8),
                capacity=capacity,
            )

    assert (raised.value.status, raised.value.code) == OUT_OF_SCOPE


@pytest.mark.usefixtures("hub_key")
def test_a_ladder_step_on_a_refused_relief_rung_climbs_to_the_next(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The reviewer's repro (#834): a ladder step bound to a stranger's relief
    rung, no `ride_scope` stated, is passed over and the climb reaches
    `api_big`. The step's dispatch is the real one, against a hub refusing it;
    a full rung declines, as the driver turns one (drive/attempt.py)."""
    from mcgyvr.capacity import Capacity, SlotUnavailableError
    from mcgyvr.escalate import Delivered, Judgement, escalate
    from mcgyvr.ladder_map import unit_map
    from mcgyvr.route import Try, Verdict
    from mcgyvr.runner import Request, dispatch
    from tests.relieftakes import Script, contract
    from tests.rungs import answering_unplaced, error

    asked_hub: list[str] = []
    with answering_unplaced(*error(*OUT_OF_SCOPE), asked_hub) as hub:
        config = parse(_refusing_hub_setup(hub, "http://api.invalid/v1"))
        assert config.units[RIDE].scope == hubwire.SCOPE_CREW
        pool = unit_map(config)
        capacity = Capacity.of(config, root=tmp_path / "slots")

        class Riding(Script):
            def __call__(self, this: Try) -> Judgement:
                if this.rung.name != RIDE:
                    return super().__call__(this)
                self.tried.append(RIDE)
                request = Request(prompt="hello", max_output_tokens=8)
                try:
                    dispatch(pool, RIDE, request, capacity=capacity)
                except SlotUnavailableError as busy:
                    return Judgement(verdict=Verdict.DECLINED, detail=str(busy))
                raise AssertionError("the hub refused this ride")

        script = Riding(local_fast=Verdict.FAILED, api_big=Verdict.PASSED)
        outcome = escalate(config, pool, contract(), script, capacity=capacity)

    assert isinstance(outcome, Delivered), outcome
    assert outcome.rung == "api_big"
    assert script.tried == ["local_fast", RIDE, "api_big"]
    assert [(a.rung, a.verdict) for a in outcome.history] == [
        ("local_fast", Verdict.FAILED),
        (RIDE, Verdict.DECLINED),
        ("api_big", Verdict.PASSED),
    ]
    assert asked_hub == [f"hitchhike@{FIRST}"]
    said = [line for line in _notes(capsys) if "out_of_scope" in line]
    assert len(said) == 1 and "--ride-scope anyone" in said[0]
