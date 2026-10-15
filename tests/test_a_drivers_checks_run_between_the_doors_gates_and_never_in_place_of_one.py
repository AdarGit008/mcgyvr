"""A driver's checks run between the door's gates, and never in place of one.

The door has three verbs, ``serve``, ``read`` and ``link``, and no flag that
adds a gate. A driver outside the package — code that is itself a door by the
seal's rule — runs checks of its own inside a door run through the door's
library seam (:class:`mcgyvr.serving.run.Driver`, taken by ``run.serve``,
``run.read``, ``run.link`` and ``run.through``):

* ``before`` and ``after`` run around each of the door's entries, in the
  door's order, and see the run's environment;
* a check that refuses ends the run as a door gate's refusal does: exit 2, no
  door entry after it, and the lease released when gate 2 took one;
* ``last`` runs after gates 7 and 8 and before the lease release, and is the
  run's exit when everything before it passed;
* the names a driver adds are left out of the lease release's environment;
* a read runs no ``last``, and a link runs ``before`` alone: nothing follows
  the timer's reading.

The door's gates are stand-ins here (``tests/fakedoor.py``); nothing reaches a
machine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests import fakedoor as fd


def _logged(log: Path) -> list[str]:
    return [line.split()[0] for line in fd.log_lines(log)]


def _recording(log: Path, refuse: str = "", *, last: int = 0) -> run.Driver:
    """A driver that logs each check it is asked, and refuses at ``refuse``."""

    def note(line: str) -> None:
        with log.open("a", encoding="utf-8") as out:
            out.write(line + "\n")

    def before(script: str, env: dict[str, str]) -> int:
        note(f"before:{script}")
        return 1 if refuse == f"before:{script}" else 0

    def after(script: str, env: dict[str, str]) -> int:
        note(f"after:{script}")
        env["RUN_DRIVER_SAW"] = script
        return 1 if refuse == f"after:{script}" else 0

    def finally_(env: dict[str, str]) -> int:
        note("last")
        return last

    return run.Driver(
        before=before,
        after=after,
        last=finally_,
        private=frozenset({"RUN_DRIVER_SAW"}),
    )


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fd.clean_door_env(monkeypatch)
    order = tmp_path / "order.log"
    fd.fake_door(tmp_path, monkeypatch, order, show=("RUN_DRIVER_SAW",))
    return order


def test_a_serve_runs_the_drivers_checks_around_each_of_its_gates(
    log: Path, tmp_path: Path
) -> None:
    compose = fd.compose_file(tmp_path / "compose.yaml")

    assert run.serve(fd.serve_argv(compose)[1:], _recording(log)) == 0

    expected: list[str] = []
    for entry in run.SERVE_SEQUENCE:
        expected += [f"before:{entry.script}", f"door:{entry.script}"]
        expected += [f"after:{entry.script}"]
    expected += [f"door:{entry.script}" for entry in run.ALWAYS]
    expected += ["last", f"door:{run.LEASE_RELEASE.script}"]
    assert _logged(log) == expected


def test_the_lease_is_released_without_the_names_the_driver_added(
    log: Path, tmp_path: Path
) -> None:
    compose = fd.compose_file(tmp_path / "compose.yaml")

    run.serve(fd.serve_argv(compose)[1:], _recording(log))

    lines = fd.log_lines(log)
    release = next(line for line in lines if line.startswith("door:lease-release"))
    assert "RUN_DRIVER_SAW=-" in release, release
    teardown = next(line for line in lines if line.startswith("door:07-teardown"))
    assert "RUN_DRIVER_SAW=06-step.py" in teardown, teardown


@pytest.mark.parametrize("where", ["before", "after"])
def test_a_check_that_refuses_ends_the_run_and_a_taken_lease_is_released(
    where: str, log: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    compose = fd.compose_file(tmp_path / "compose.yaml")
    rig = run.SERVE_SEQUENCE[1].script

    code = run.serve(fd.serve_argv(compose)[1:], _recording(log, f"{where}:{rig}"))

    assert code == 2
    logged = _logged(log)
    assert f"door:{run.SERVE_SEQUENCE[2].script}" not in logged, logged
    took = where == "after"
    assert (f"door:{rig}" in logged) is took, logged
    # Released when gate 2 took it, and nothing to release when it never ran.
    assert (logged[-1] == f"door:{run.LEASE_RELEASE.script}") is took, logged
    assert "last" not in logged, "a run refused before gate 5 has no last phase"
    assert f"REFUSED {where} {rig}" in capsys.readouterr().err


def test_a_last_check_that_refuses_is_the_runs_exit(log: Path, tmp_path: Path) -> None:
    compose = fd.compose_file(tmp_path / "compose.yaml")

    assert run.serve(fd.serve_argv(compose)[1:], _recording(log, last=1)) == 1
    assert _logged(log)[-2:] == ["last", f"door:{run.LEASE_RELEASE.script}"]


def test_a_read_runs_the_checks_around_its_gates_and_no_last(log: Path) -> None:
    assert run.read(fd.read_argv()[1:], _recording(log)) == 0

    expected: list[str] = []
    for entry in run.READ_SEQUENCE:
        expected += [f"before:{entry.script}", f"door:{entry.script}"]
        expected += [f"after:{entry.script}"]
    assert _logged(log) == expected


def test_a_link_runs_before_alone_and_nothing_after_the_timer(log: Path) -> None:
    assert run.link(fd.link_argv()[1:], _recording(log)) == 0

    (timer,) = run.LINK_SEQUENCE
    assert _logged(log) == [f"before:{timer.script}", f"door:{timer.script}"]


def test_the_door_takes_no_gate_list_and_has_no_step_verb() -> None:
    for verb in ("serve", "read", "link"):
        with pytest.raises(SystemExit):
            run.main([verb, "--host", fd.HOST, "--gates", "x.json"])
    with pytest.raises(SystemExit):
        run.main(["step", "--host", fd.HOST])
    assert not hasattr(run, "GATES_ENV")
    assert not hasattr(run, "load_gate_list")
