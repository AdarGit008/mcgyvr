"""A unit that is coming up is watched for as long as the config says.

``mcgyvr serve up`` and ``serve wake`` poll each unit until it lists its models
and does not read as asleep, and then give up and report it down. That limit is
``serving.start_timeout_s``: six minutes unset, the 120 polls three seconds
apart the door always spent, and longer for a load that needs it (a large vLLM
unit read off a slow disk).

Promises:

* Unset, the key reads as 360 seconds; a stated number of seconds is kept, and
  a negative one is refused when the config is read.
* The timeout buys ``ceil(timeout / HEALTH_INTERVAL_S)`` polls, and never fewer
  than one.
* A serve step reads the key from the config gate 1 read, found as gate 1
  found it, and takes the default when gate 1 found none (``RUN_CONFIG=none``);
  a config it cannot read again, or one found at another path than the one
  gate 1 exported, is a refusal, not a default.
* ``serve up`` and ``serve wake`` hand that timeout to every ``wait_for``, and
  a refusal is exit 2 before anything is started or woken.
* ``wait_for`` polls a unit that never answers exactly as many times as its
  timeout buys, sleeping ``HEALTH_INTERVAL_S`` between polls.

The rig is the invented one ``test_a_sleeping_unit_does_not_read_as_serving``
scripts, reached through the same substitution of ``servelib.ssh``; the steps
are driven in-process with the rig calls they make (``up``, ``sleeping``,
``wait_for``) recorded instead of sent.
"""

from __future__ import annotations

import subprocess
import time
import types
from pathlib import Path

import pytest

from mcgyvr.config import CONFIG_PATH_ENV, ConfigSchemaError, parse
from mcgyvr.serving import servelib
from tests._helpers import by_path
from tests.test_a_sleeping_unit_does_not_read_as_serving import (
    HOST,
    NO_ROUTE,
    UNIT,
    Rig,
)

#: One invented unit and its ladder: the least a config states.
CONFIG = """\
units:
  local_coder:
    address: http://rig-a.invalid:8001
    model: invented-coder
    width: 1
ladder:
- local_coder
"""


def _with_serving(body: str) -> str:
    return CONFIG + "serving:\n" + body


def test_unset_the_start_timeout_is_six_minutes() -> None:
    assert parse(CONFIG).get("serving.start_timeout_s") == 360.0
    assert servelib.START_TIMEOUT_S_DEFAULT == 360.0


@pytest.mark.parametrize("stated", ["900", "900.5", "0"])
def test_a_stated_start_timeout_is_kept(stated: str) -> None:
    config = parse(_with_serving(f"  start_timeout_s: {stated}\n"))

    assert config.get("serving.start_timeout_s") == float(stated)


def test_a_negative_start_timeout_is_refused() -> None:
    with pytest.raises(ConfigSchemaError, match="start_timeout_s"):
        parse(_with_serving("  start_timeout_s: -1\n"))


@pytest.mark.parametrize(
    ("timeout_s", "polls"),
    [(360.0, 120), (361.0, 121), (900.0, 300), (3.0, 1), (0.0, 1)],
)
def test_the_timeout_buys_its_polls_and_never_none(
    timeout_s: float, polls: int
) -> None:
    assert servelib.health_polls(timeout_s) == polls


def test_a_step_under_no_config_takes_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUN_CONFIG", "none")
    assert servelib.start_timeout_s("up") == 360.0
    monkeypatch.delenv("RUN_CONFIG")
    assert servelib.start_timeout_s("up") == 360.0


def _under(monkeypatch: pytest.MonkeyPatch, setup: Path) -> None:
    """The environment the door hands a step for a run under ``setup``: the
    config named by ``$MCGYVR_CONFIG``, and gate 1's export of its folder."""
    monkeypatch.setenv(CONFIG_PATH_ENV, str(setup))
    monkeypatch.setenv("RUN_CONFIG", str(setup.resolve().parent))


def test_a_step_reads_the_timeout_from_the_config_gate_one_named(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stated = tmp_path / "setup.yaml"
    stated.write_text(_with_serving("  start_timeout_s: 900\n"), encoding="utf-8")
    unset = tmp_path / "unset.yaml"
    unset.write_text(CONFIG, encoding="utf-8")

    _under(monkeypatch, stated)
    assert servelib.start_timeout_s("up") == 900.0
    _under(monkeypatch, unset)
    assert servelib.start_timeout_s("wake") == 360.0


def test_a_config_the_step_cannot_read_again_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _under(monkeypatch, tmp_path / "gone.yaml")

    assert servelib.start_timeout_s("wake") is None
    assert "serve-wake: REFUSED" in capsys.readouterr().err


def test_a_config_found_at_another_path_than_gate_one_exported_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "now").mkdir()
    setup = tmp_path / "now" / "setup.yaml"
    setup.write_text(_with_serving("  start_timeout_s: 900\n"), encoding="utf-8")
    _under(monkeypatch, setup)
    monkeypatch.setenv("RUN_CONFIG", str(tmp_path / "then"))

    assert servelib.start_timeout_s("up") is None
    assert "serve-up: REFUSED" in capsys.readouterr().err


def test_a_unit_that_never_answers_is_polled_as_often_as_its_timeout_buys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = Rig(models=NO_ROUTE, is_sleeping=NO_ROUTE)
    monkeypatch.setattr(servelib, "ssh", rig)
    # The row's restart count asks the docker daemon, through a subprocess whose
    # wait sleeps in short steps of its own: answered here, nothing reaches this
    # machine's docker and every sleep recorded below is a poll's.
    monkeypatch.setattr(servelib, "restart_count", lambda container: 0)
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", slept.append)

    row = servelib.wait_for(HOST, UNIT, timeout_s=4 * servelib.HEALTH_INTERVAL_S)

    assert row["healthy"] is False
    assert sum(1 for asked in rig.asked if "/v1/models" in asked) == 4
    assert slept == [servelib.HEALTH_INTERVAL_S] * 3


#: The serve steps, as the door runs them.
_STEPS = Path(servelib.__file__).resolve().parent / "gate-scripts"


def _step(mode: str) -> types.ModuleType:
    return by_path(f"serve_{mode}_step", _STEPS / f"serve-{mode}.py")


class Steps:
    """What a serve step asked of the rig: whether it started the stack, and
    the timeout each ``wait_for`` was handed."""

    def __init__(self) -> None:
        self.started = 0
        self.timeouts: list[float] = []

    def up(
        self, compose_file: Path, units: tuple[servelib.Service, ...] = ()
    ) -> subprocess.CompletedProcess[str]:
        self.started += 1
        return subprocess.CompletedProcess([], 0, "", "")

    def wait_for(
        self, host: str, service: servelib.Service, *, timeout_s: float = -1.0
    ) -> dict[str, object]:
        self.timeouts.append(timeout_s)
        return {
            "container": service.container,
            "port": service.port,
            "healthy": True,
            "sleeping": False,
            "seconds": 0,
            "models": ["invented-coder"],
        }


@pytest.fixture
def steps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Steps:
    """Two invented units on one invented host, behind a prologue that passed;
    every rig call the steps make is recorded instead of sent."""
    units = (
        UNIT,
        servelib.Service(name="svc1", container="mcgyvr-box1-b-8081", port=8081),
    )
    compose = tmp_path / "compose.yaml"
    compose.write_text("services: {}\n", encoding="utf-8")
    ctx = servelib.ServeContext(
        host=HOST,
        compose_file=compose,
        out=tmp_path / "serve.json",
        units=units,
        expected=[u.container for u in units],
        only=set(),
    )
    seen = Steps()
    monkeypatch.setattr(servelib, "serve_prologue", lambda mode, **_: ctx)
    monkeypatch.setattr(servelib, "up", seen.up)
    monkeypatch.setattr(servelib, "wait_for", seen.wait_for)
    monkeypatch.setattr(servelib, "sleeping", lambda host, port, key=None: False)
    monkeypatch.setattr(servelib, "write_serve_record", lambda ctx, mode, body: None)
    return seen


@pytest.mark.parametrize("mode", ["up", "wake"])
def test_a_serve_step_hands_the_stated_timeout_to_every_unit_it_watches(
    mode: str, steps: Steps, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    setup = tmp_path / "setup.yaml"
    setup.write_text(_with_serving("  start_timeout_s: 6\n"), encoding="utf-8")
    _under(monkeypatch, setup)

    assert _step(mode).main() == 0
    assert steps.timeouts == [6.0, 6.0]
    assert servelib.health_polls(6.0) == 2


@pytest.mark.parametrize("mode", ["up", "wake"])
def test_a_serve_step_under_a_config_it_cannot_read_again_starts_nothing(
    mode: str,
    steps: Steps,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _under(monkeypatch, tmp_path / "gone.yaml")

    assert _step(mode).main() == 2
    assert f"serve-{mode}: REFUSED" in capsys.readouterr().err
    assert steps.started == 0
    assert steps.timeouts == []
