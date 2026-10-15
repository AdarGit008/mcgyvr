"""A driver named in the environment runs inside the door itself.

``$MCGYVR_DOOR_DRIVER=package.module:attr`` names a
:class:`mcgyvr.serving.run.Driver` that ``python -m mcgyvr.serving.run``
imports before any gate runs, and runs between its own gates exactly as the
library seam's ``driver=`` argument does. Nothing outside the package has to
be a door by the seal's rule to add checks: the driver runs in the door's
own process, so what it starts is under the door.

* unset, the run is the door's alone, as it always was;
* set, ``before``, ``after`` and ``last`` run around the door's gates in the
  door's order, on ``serve``, ``read`` and ``link``;
* a value that is malformed, cannot be imported or is not a ``Driver`` is
  refused in one line before gate 1, never run without;
* a driver adds refusals and names of its own, and nothing else: a gate that
  refused stays refused, and a check that changes a name the door set ends
  the run;
* the variable is not handed to a gate; ``RUN_DRIVER`` names the driver, and
  a serve run's header files it.

The door's gates are stand-ins (``tests/fakedoor.py``) except in the last
test, which runs the real door over the stub machine of ``tests/usermode.py``.
"""

from __future__ import annotations

import json
import secrets
import sys
from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests import fakedoor as fd
from tests import usermode

#: What every stand-in gate shows of its environment.
SHOWN = ("RUN_DRIVER", run.DRIVER_ENV, "RUN_DRIVER_SAW")


def _module(tmp_path: Path, body: str) -> str:
    """A module of ``body`` on sys.path under a name of its own; its name."""
    name = f"drivenby_{secrets.token_hex(4)}"
    where = tmp_path / "drivers"
    where.mkdir(exist_ok=True)
    (where / f"{name}.py").write_text(body, encoding="utf-8")
    if str(where) not in sys.path:
        sys.path.insert(0, str(where))
    return name


def _recording(log: Path, *, refuse: str = "", tamper: str = "", last: int = 0) -> str:
    """A driver module's text: each check logs itself, and ``refuse`` names the
    check that says no; ``tamper`` names the check that sets RUN_HOST."""
    return f"""\
from mcgyvr.serving.run import Driver

LOG = {str(log)!r}


def _note(line):
    with open(LOG, "a", encoding="utf-8") as out:
        out.write(line + "\\n")


def _check(where, script, env):
    _note(f"{{where}}:{{script}}")
    if {tamper!r} == f"{{where}}:{{script}}":
        env["RUN_HOST"] = "another-rig.invalid"
    env["RUN_DRIVER_SAW"] = script
    return 1 if {refuse!r} == f"{{where}}:{{script}}" else 0


def _last(env):
    _note("last")
    return {last}


DRIVER = Driver(
    before=lambda script, env: _check("before", script, env),
    after=lambda script, env: _check("after", script, env),
    last=_last,
    private=frozenset({{"RUN_DRIVER_SAW"}}),
)
NOT_A_DRIVER = 3
"""


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fd.clean_door_env(monkeypatch)
    monkeypatch.delenv(run.DRIVER_ENV, raising=False)
    monkeypatch.setattr(sys, "path", list(sys.path))
    order = tmp_path / "order.log"
    fd.fake_door(tmp_path, monkeypatch, order, show=SHOWN)
    return order


def _drive(monkeypatch: pytest.MonkeyPatch, spec: str) -> None:
    monkeypatch.setenv(run.DRIVER_ENV, spec)


def _tags(log: Path) -> list[str]:
    return [line.split()[0] for line in fd.log_lines(log)]


def _serve(tmp_path: Path) -> list[str]:
    return fd.serve_argv(fd.compose_file(tmp_path / "compose.yaml"))


def _door_only() -> list[str]:
    return [
        *(f"door:{entry.script}" for entry in (*run.SERVE_SEQUENCE, *run.ALWAYS)),
        f"door:{run.LEASE_RELEASE.script}",
    ]


def test_unset_the_run_is_the_doors_alone(log: Path, tmp_path: Path) -> None:
    assert run.main(_serve(tmp_path)) == 0

    assert _tags(log) == _door_only()
    for line in fd.log_lines(log):
        assert f"RUN_DRIVER=- {run.DRIVER_ENV}=-" in line, line


def test_a_named_drivers_checks_run_around_the_doors_gates_in_order(
    log: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = f"{_module(tmp_path, _recording(log))}:DRIVER"
    _drive(monkeypatch, spec)

    assert run.main(_serve(tmp_path)) == 0

    expected: list[str] = []
    for entry in run.SERVE_SEQUENCE:
        expected += [f"before:{entry.script}", f"door:{entry.script}"]
        expected += [f"after:{entry.script}"]
    expected += [f"door:{entry.script}" for entry in run.ALWAYS]
    expected += ["last", f"door:{run.LEASE_RELEASE.script}"]
    assert _tags(log) == expected
    gates = [line for line in fd.log_lines(log) if line.startswith("door:")]
    for line in gates:
        # The driver is named to every gate, and the variable is handed to none.
        assert f"RUN_DRIVER={spec} {run.DRIVER_ENV}=-" in line, line
    release = next(line for line in gates if "lease-release" in line)
    assert "RUN_DRIVER_SAW=-" in release, release


def test_a_named_driver_runs_on_a_read_and_a_link_as_the_seam_runs_it(
    log: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _drive(monkeypatch, f"{_module(tmp_path, _recording(log))}:DRIVER")

    assert run.main(fd.read_argv()) == 0
    expected: list[str] = []
    for entry in run.READ_SEQUENCE:
        expected += [f"before:{entry.script}", f"door:{entry.script}"]
        expected += [f"after:{entry.script}"]
    assert _tags(log) == expected

    log.unlink()
    assert run.main(fd.link_argv()) == 0
    (timer,) = run.LINK_SEQUENCE
    assert _tags(log) == [f"before:{timer.script}", f"door:{timer.script}"]


BAD_MODULE = "raise RuntimeError('this module will not load')\n"


@pytest.mark.parametrize(
    ("value", "says"),
    [
        ("", "package.module:attr"),
        ("no_attr_given", "package.module:attr"),
        ("two:colons:here", "package.module:attr"),
        ("path/to/file.py:DRIVER", "package.module:attr"),
        ("mcgyvr_no_such_module_xyz:DRIVER", "cannot be imported"),
        ("{bad}:DRIVER", "cannot be imported"),
        ("{good}:NO_SUCH_NAME", "has no NO_SUCH_NAME"),
        ("{good}:NOT_A_DRIVER", "not a mcgyvr.serving.run.Driver"),
    ],
)
def test_a_value_that_names_no_driver_is_refused_in_one_line_before_gate_1(
    value: str,
    says: str,
    log: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    good = _module(tmp_path, _recording(log))
    bad = _module(tmp_path, BAD_MODULE)
    _drive(monkeypatch, value.format(good=good, bad=bad))

    for argv in (_serve(tmp_path), fd.read_argv(), fd.link_argv()):
        assert run.main(argv) == 2
        assert fd.log_lines(log) == [], "a gate ran without the driver it was named"
        err = capsys.readouterr().err.strip().splitlines()
        assert len(err) == 1, err
        assert run.DRIVER_ENV in err[0] and says in err[0], err


def test_a_driver_that_claims_a_door_name_as_its_own_is_refused_before_gate_1(
    log: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    body = (
        "from mcgyvr.serving.run import Driver\n"
        "DRIVER = Driver(private=frozenset({'RUN_HOST', 'RUN_MINE'}))\n"
    )
    _drive(monkeypatch, f"{_module(tmp_path, body)}:DRIVER")

    assert run.main(_serve(tmp_path)) == 2
    assert fd.log_lines(log) == []
    assert "RUN_HOST" in capsys.readouterr().err


def test_a_driver_cannot_make_a_refused_gate_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fd.clean_door_env(monkeypatch)
    monkeypatch.setattr(sys, "path", list(sys.path))
    log = tmp_path / "order.log"
    rig = run.SERVE_SEQUENCE[1].script
    fd.fake_door(tmp_path, monkeypatch, log, show=SHOWN, statuses={rig: 2})
    _drive(monkeypatch, f"{_module(tmp_path, _recording(log))}:DRIVER")

    assert run.main(_serve(tmp_path)) == 2

    logged = _tags(log)
    assert f"door:{rig}" in logged
    assert f"after:{rig}" not in logged, "a check ran after a refused gate"
    assert f"door:{run.SERVE_SEQUENCE[2].script}" not in logged, logged
    assert "last" not in logged


@pytest.mark.parametrize("where", ["before", "after"])
def test_a_check_that_changes_a_name_the_door_set_ends_the_run(
    where: str,
    log: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    daemon = run.SERVE_SEQUENCE[2].script
    driver = _recording(log, tamper=f"{where}:{daemon}")
    _drive(monkeypatch, f"{_module(tmp_path, driver)}:DRIVER")

    assert run.main(_serve(tmp_path)) == 2

    logged = _tags(log)
    assert (f"door:{daemon}" in logged) is (where == "after"), logged
    assert f"door:{run.SERVE_SEQUENCE[3].script}" not in logged, logged
    # The lease gate 2 took is released, and on the door's own host.
    release = fd.log_lines(log)[-1]
    assert release.startswith(f"door:{run.LEASE_RELEASE.script}"), release
    assert "RUN_HOST" in capsys.readouterr().err


def test_a_check_that_raises_is_a_refusal_and_the_lease_is_released(
    log: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    body = (
        "from mcgyvr.serving.run import Driver\n"
        "def _after(script, env):\n"
        "    if script == '03-image.py':\n"
        "        raise ValueError('the driver broke')\n"
        "    return 0\n"
        "DRIVER = Driver(after=_after)\n"
    )
    _drive(monkeypatch, f"{_module(tmp_path, body)}:DRIVER")

    assert run.main(_serve(tmp_path)) == 2

    logged = _tags(log)
    assert f"door:{run.SERVE_SEQUENCE[3].script}" not in logged, logged
    assert logged[-1] == f"door:{run.LEASE_RELEASE.script}", logged
    assert "the driver broke" in capsys.readouterr().err


#: A driver whose check, after gate 3, starts a process that asks whether it
#: is under the door, and files the answer.
UNDER_THE_DOOR = """\
import subprocess
import sys

from mcgyvr.serving.run import Driver

ANSWER = {answer!r}


def _after(script, env):
    if script == "03-image.py":
        done = subprocess.run(
            [sys.executable, "-c",
             "from mcgyvr.serving.gatelib import under_door; print(under_door())"],
            env=env, capture_output=True, text=True, check=False,
        )
        with open(ANSWER, "w", encoding="utf-8") as out:
            out.write(done.stdout.strip())
    return 0


DRIVER = Driver(after=_after)
"""


def test_the_real_door_files_the_driver_it_ran_and_what_it_starts_is_under_it(
    tmp_path: Path,
) -> None:
    usermode.save_rig()
    stubs = usermode.machine(tmp_path)
    answer = tmp_path / "under-door.txt"
    where = tmp_path / "drivers"
    where.mkdir()
    (where / "underdoor_driver.py").write_text(
        UNDER_THE_DOOR.format(answer=str(answer)), encoding="utf-8"
    )
    spec = "underdoor_driver:DRIVER"

    done = usermode.door(
        usermode.serve("up", usermode.compose_file(tmp_path)),
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
        env_extra={
            "MCGYVR_CONFIG": str(usermode.dev_setup(tmp_path)),
            "PYTHONPATH": str(where),
            run.DRIVER_ENV: spec,
        },
    )

    assert done.returncode == 0, done.stdout + done.stderr
    assert answer.read_text(encoding="utf-8") == "True"
    [filed] = usermode.door_logs(usermode.home())
    header = json.loads((filed / f"{filed.name}.run.json").read_text("utf-8"))
    assert header["driver"] == spec


def test_a_run_with_no_driver_files_no_driver(tmp_path: Path) -> None:
    usermode.save_rig()
    stubs = usermode.machine(tmp_path)

    done = usermode.door(
        usermode.serve("up", usermode.compose_file(tmp_path)),
        stubs=stubs,
        run_root=usermode.install_root(tmp_path),
        cwd=tmp_path,
        env_extra={"MCGYVR_CONFIG": str(usermode.dev_setup(tmp_path))},
    )

    assert done.returncode == 0, done.stdout + done.stderr
    [filed] = usermode.door_logs(usermode.home())
    header = json.loads((filed / f"{filed.name}.run.json").read_text("utf-8"))
    assert "driver" not in header
