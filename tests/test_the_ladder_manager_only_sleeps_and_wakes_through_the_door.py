"""The ladder manager sleeps and wakes through the door a person's ``serve`` uses.

The promises:

* **One door, a fresh waker.** :class:`~mcgyvr.wake.CardSwitches` wakes a card
  by the same ``serve up`` a refused dispatch runs, and wakes it again when the
  manager asks again later: the manager lives for hours and may wake a card it
  has since slept, so it never reuses a waker's one-wake-per-run memory.
* **Sleep drains first, and a busy card is not slept.** A sleep takes every
  slot of the card before the door's ``down``; a dispatch still running makes
  it ``False`` and runs no door.
* **The switch gates the manager, not the person.** With
  ``serving.enable_sleep_wake`` off neither verb spawns anything.
* **A card goes whole.** ``room_for`` is always empty and ``card_of`` names
  every rung the card serves.
* **``mcgyvr manage`` on a ladder with nothing to manage does nothing** — no
  door, no decision, no file — and on one with a sleeping unit and a quiet
  queue asks Jev nothing and spawns nothing.
* **A cooled unit is not an unreachable one.** :class:`~mcgyvr.pressure.RungCooling`
  learns from the manager's own failures and never reads a sleeping unit as
  down, because asleep is the state the manager wakes.

Everything here is a fake: the door is substituted at ``mcgyvr.wake.spawn_door``
and the probes at ``mcgyvr.pressure``; no network is reached.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import Config, parse
from tests import livejournal as lj
from tests.test_a_sleeping_rung_is_woken_rather_than_declined import door_log

FAST = "local_fast"
BIG_A = "local_big_a"
BIG_B = "local_big_b"
API = "api_big"

FAST_HOST = "fast-box.example"
BIG_HOST = "big-box.example"


def ladder_text(
    compose_dir: Path | None,
    *,
    sleep_wake: bool = True,
    timeout_s: float | None = None,
    api: bool = False,
) -> str:
    """A fast rung, and two rungs sharing one big card."""
    timeout = "" if timeout_s is None else f"    request_timeout_s: {timeout_s}\n"
    serving = ""
    if compose_dir is not None:
        serving = (
            "serving:\n"
            f"  compose_dir: {compose_dir}\n"
            f"  enable_sleep_wake: {'true' if sleep_wake else 'false'}\n"
        )
    text = (
        "units:\n"
        f"  {FAST}:\n"
        f"    address: http://{FAST_HOST}:8000\n"
        "    model: small-coder\n"
        "    rig: fast-rig\n"
        "    width: 2\n"
        f"  {BIG_A}:\n"
        f"    address: http://{BIG_HOST}:8001\n"
        "    model: large-coder\n"
        "    rig: big-rig-a\n"
        "    width: 2\n" + timeout + f"  {BIG_B}:\n"
        f"    address: http://{BIG_HOST}:8002\n"
        "    model: large-coder-two\n"
        "    rig: big-rig-b\n"
        "    width: 2\n" + timeout
    )
    names = [FAST, BIG_A, BIG_B]
    if api:
        text += (
            f"  {API}:\n"
            "    address: https://api.example.com/v1\n"
            "    model: vendor-large\n"
            "    rig: vendor\n"
            "    width: 4\n"
            "    api_key_env: EXAMPLE_API_KEY\n"
        )
        names.append(API)
    text += "ladder:\n" + "".join(f"- {n}\n" for n in names)
    return text + "profile: dev\n" + serving


def write_spec(tmp_path: Path) -> Path:
    """One launch spec for the big card, as ``emit`` would write it."""
    from mcgyvr.serving import COMPOSE_PREFIX, COMPOSE_SUFFIX

    where = tmp_path / "specs"
    where.mkdir(exist_ok=True)
    (where / f"{COMPOSE_PREFIX}{BIG_HOST}{COMPOSE_SUFFIX}").write_text(
        "services:\n  big:\n    image: example/server:1\n", encoding="utf-8"
    )
    return where


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A HOME and a rendezvous directory nobody else writes to."""
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    (tmp_path / "rendezvous").mkdir(exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "rendezvous"))
    return tmp_path / "home"


def config_on_disk(tmp_path: Path, text: str, name: str = "c.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text + f"journal:\n  dir: {tmp_path / 'j'}\n", encoding="utf-8")
    return path


def switches_for(config: Config) -> Any:
    from mcgyvr.capacity import Capacity
    from mcgyvr.wake import CardSwitches

    return CardSwitches(config, Capacity.of(config))


def verb(argv: list[str]) -> str:
    return argv[argv.index("serve") + 1]


# --- the door ----------------------------------------------------------------


def test_a_wake_runs_the_door_up_for_the_card_and_runs_it_again_when_asked_again(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each wake is a fresh waker, so a card slept in between is woken again."""
    specs = write_spec(tmp_path)
    config = parse(ladder_text(specs))
    spawned = door_log(monkeypatch)
    switches = switches_for(config)

    first = switches.wake(BIG_A)
    second = switches.wake(BIG_A)

    assert first is True and second is True
    assert [verb(argv) for argv in spawned] == ["up", "up"], spawned
    for argv in spawned:
        assert BIG_HOST in argv, argv
        assert str(specs / f"compose.{BIG_HOST}.yml") in argv, argv


def test_a_sleep_drains_the_card_and_then_runs_the_door_down(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs = write_spec(tmp_path)
    config = parse(ladder_text(specs))
    spawned = door_log(monkeypatch)

    slept = switches_for(config).sleep(BIG_A)

    assert slept is True
    assert [verb(argv) for argv in spawned] == ["down"], spawned
    assert BIG_HOST in spawned[0], spawned


def test_a_sleep_with_a_dispatch_still_running_is_not_done_and_runs_no_door(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slot held by another holder is a request in flight: not now."""
    from mcgyvr.capacity import Capacity

    specs = write_spec(tmp_path)
    config = parse(ladder_text(specs, timeout_s=0.2))
    spawned = door_log(monkeypatch)
    holder = Capacity.of(config)

    with holder.hold(BIG_B):
        slept = switches_for(config).sleep(BIG_A)

    assert slept is False
    assert spawned == [], spawned


def test_a_door_that_fails_is_a_sleep_that_did_not_happen(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcgyvr.wake as wake

    specs = write_spec(tmp_path)
    config = parse(ladder_text(specs))
    monkeypatch.setattr(wake, "spawn_door", lambda argv, **_: 1)

    switches = switches_for(config)

    assert switches.sleep(BIG_A) is False
    assert switches.wake(BIG_A) is False


# --- the switch --------------------------------------------------------------


def test_with_the_switch_off_neither_verb_spawns_anything(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs = write_spec(tmp_path)
    config = parse(ladder_text(specs, sleep_wake=False))
    spawned = door_log(monkeypatch)
    switches = switches_for(config)

    assert switches.wake(BIG_A) is False
    assert switches.sleep(BIG_A) is False
    assert spawned == [], spawned


def test_a_rung_whose_card_holds_no_single_launch_spec_is_neither_woken_nor_slept(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs = write_spec(tmp_path)
    config = parse(ladder_text(specs))
    spawned = door_log(monkeypatch)
    switches = switches_for(config)

    assert switches.wake(FAST) is False
    assert switches.sleep(FAST) is False
    assert spawned == [], spawned


# --- a card goes whole -------------------------------------------------------


def test_no_unit_needs_room_made_because_a_card_goes_whole(
    tmp_path: Path, home: Path
) -> None:
    config = parse(ladder_text(write_spec(tmp_path)))
    switches = switches_for(config)

    assert switches.room_for(BIG_A) == ()
    assert switches.room_for(BIG_B) == ()


def test_a_cards_rungs_are_every_rung_the_host_serves(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "0" * 12)
    config = parse(ladder_text(write_spec(tmp_path), api=True))
    switches = switches_for(config)

    assert set(switches.card_of(BIG_A)) == {BIG_A, BIG_B}
    assert set(switches.card_of(BIG_B)) == {BIG_A, BIG_B}
    assert switches.card_of(API) == (API,)


def test_the_drain_waits_as_long_as_the_slowest_unit_on_the_card_may_take(
    tmp_path: Path,
) -> None:
    from mcgyvr.serving import cards
    from mcgyvr.wake import drain_timeout

    specs = write_spec(tmp_path)
    stated = parse(ladder_text(specs, timeout_s=7.5))
    unstated = parse(ladder_text(specs))

    assert drain_timeout(stated, cards(stated)[BIG_A]) == 7.5
    assert drain_timeout(unstated, cards(unstated)[BIG_A]) is None


# --- mcgyvr manage -----------------------------------------------------------


def refuse_everything(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Fail the test if a door is run or Jev is asked; return what was reached."""
    import mcgyvr.decision as decision
    import mcgyvr.wake as wake

    reached: list[str] = []

    def no_door(argv: Any, **_: Any) -> int:
        reached.append(f"door: {argv}")
        raise AssertionError(f"a door was run: {argv}")

    def no_decision(*args: Any, **kwargs: Any) -> Any:
        reached.append("decision")
        raise AssertionError("Jev was asked")

    monkeypatch.setattr(wake, "spawn_door", no_door)
    monkeypatch.setattr(decision, "_post_json", no_decision)
    return reached


def test_manage_on_a_ladder_with_nothing_to_sleep_says_so_and_does_nothing(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No compose directory means no unit can wake: no pool, no file, no door."""
    reached = refuse_everything(monkeypatch)
    config = config_on_disk(tmp_path, ladder_text(None))

    code = lj.main(["manage", "--config", str(config), "--once"])

    assert code == 0
    assert "nothing to manage" in capsys.readouterr().out
    assert reached == []
    assert list((tmp_path / "rendezvous").iterdir()) == [], (
        "the manager wrote under the host-wide rendezvous directory for a "
        "ladder it has nothing to do on"
    )


def test_manage_with_the_switch_off_is_nothing_to_manage_as_well(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reached = refuse_everything(monkeypatch)
    config = config_on_disk(
        tmp_path, ladder_text(write_spec(tmp_path), sleep_wake=False)
    )

    code = lj.main(["manage", "--config", str(config), "--once"])

    assert code == 0
    assert "nothing to manage" in capsys.readouterr().out
    assert reached == []


def test_manage_once_on_a_quiet_ladder_with_a_sleeping_unit_asks_and_wakes_nothing(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The fast rung answers with nothing queued and the big card sleeps.

    Nothing is queued on the dearest awake rung, so a wake is not legal, and
    the big card is already asleep, so a sleep is not either: one legal answer
    is not a question, and a quiet ladder costs no decision.
    """
    import mcgyvr.pressure as pressure

    reached = refuse_everything(monkeypatch)
    config = config_on_disk(tmp_path, ladder_text(write_spec(tmp_path)))

    class Answers:
        def __init__(self, live: bool) -> None:
            self.live = live

    def probe(endpoint: Any, timeout_s: float) -> Any:
        return Answers(endpoint.base_url.startswith(f"http://{FAST_HOST}"))

    monkeypatch.setattr(pressure, "probe_endpoint", probe)
    monkeypatch.setattr(pressure, "unit_in_flight", lambda *args: 0)

    code = lj.main(["manage", "--config", str(config), "--once"])

    out = capsys.readouterr().out
    assert code == 0, out
    assert "nothing to manage" not in out
    assert reached == []


def test_manage_names_the_rungs_it_manages_in_one_header_line(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mcgyvr.pressure as pressure

    refuse_everything(monkeypatch)
    config = config_on_disk(tmp_path, ladder_text(write_spec(tmp_path)))

    class Answers:
        live = False

    monkeypatch.setattr(pressure, "probe_endpoint", lambda *args: Answers())
    monkeypatch.setattr(pressure, "unit_in_flight", lambda *args: 0)

    lj.main(["manage", "--config", str(config), "--once"])

    header = capsys.readouterr().out.splitlines()[0]
    for rung in (FAST, BIG_A, BIG_B):
        assert rung in header, header


def test_manage_is_listed_beside_serve_in_the_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = lj.main(["manage", "--help"])

    assert code == 0
    assert "--once" in capsys.readouterr().out


# --- the cooling a failed switch earns ---------------------------------------


def test_a_unit_that_failed_three_switches_in_a_row_is_cooled_and_a_success_resets_it(
    tmp_path: Path,
) -> None:
    from mcgyvr.pool import source_map
    from mcgyvr.pressure import RungCooling

    config = parse(ladder_text(write_spec(tmp_path)))
    cooling = RungCooling(source_map(config))

    cooling.failed(BIG_A)
    cooling.failed(BIG_A)
    cooling.worked(BIG_A)
    cooling.failed(BIG_A)
    cooling.failed(BIG_A)
    assert cooling.cooled((FAST, BIG_A, BIG_B)) == frozenset()

    cooling.failed(BIG_A)
    assert cooling.cooled((FAST, BIG_A, BIG_B)) == frozenset({BIG_A})


def test_a_sleeping_unit_is_never_read_as_cooling_for_being_asleep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing answers on any rung here, and nothing is cooled for it."""
    import mcgyvr.availability as availability
    from mcgyvr.pool import source_map
    from mcgyvr.pressure import RungCooling

    def nothing_answers(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the cooling read the network")

    monkeypatch.setattr(availability, "probe_endpoint", nothing_answers)
    config = parse(ladder_text(write_spec(tmp_path)))

    assert RungCooling(source_map(config)).cooled((FAST, BIG_A, BIG_B)) == frozenset()


def test_a_rung_the_pool_does_not_know_is_not_cooled(tmp_path: Path) -> None:
    from mcgyvr.pool import source_map
    from mcgyvr.pressure import RungCooling

    config = parse(ladder_text(write_spec(tmp_path)))
    cooling = RungCooling(source_map(config))

    assert cooling.cooled(("no_such_rung",)) == frozenset()


# --- the climb reads the manager's hooks -------------------------------------


def test_a_run_asks_the_ladder_manager_what_it_climbs_with(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every ``mcgyvr run`` takes its config, gauge and presence from one place."""
    import mcgyvr.ladder_manager as ladder_manager

    config = config_on_disk(tmp_path, ladder_text(None))
    seen: list[Any] = []
    real = ladder_manager.for_task

    def recording(config: Config, **kwargs: Any) -> Any:
        seen.append(kwargs)
        return real(config, **kwargs)

    monkeypatch.setattr(ladder_manager, "for_task", recording)
    lj.patch_backend(
        monkeypatch, lambda model, request: lj.completion(lj.GOOD_REPLY, request)
    )
    repo = lj.make_repo(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    lj.main(lj.run_args(contract, repo, config))
    capsys.readouterr()

    assert len(seen) == 1, seen
    assert callable(seen[0]["read_board"])
