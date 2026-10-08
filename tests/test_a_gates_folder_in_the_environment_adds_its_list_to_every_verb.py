"""``$MCGYVR_DOOR_GATES`` adds a caller's gate list to every verb's run.

Owner, 2026-10-08 (design 2b): a caller hands the door its gates from the
environment as well as with ``--gates``: ``MCGYVR_DOOR_GATES=<folder>``, and
a ``serve``, ``read``, ``link`` or ``step`` run given no ``--gates`` loads
``<folder>/<verb>.json``. So a door mcgyvr's own code opens (the waker, the
fleet's read and probe, the commands live admission prints) carries the
caller's gates too, with no product code naming them. A list from the
environment is a ``--gates`` list in every way: placed by phase, held to the
same rules, and never in place of a door gate. A folder with no list for a
verb adds none; a value that names no folder is refused before any gate.

Every machine here is invented and stands behind the door's shims.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from mcgyvr import wake
from mcgyvr.fleet import linkread, read
from mcgyvr.serving import run
from tests import callergates as cg
from tests import onedoor, usermode

VERBS = ("step", "serve", "read", "link")


def _argv(verb: str, tmp_path: Path, *extra: str) -> list[str]:
    if verb == "step":
        return cg.step_argv(tmp_path, *extra)
    if verb == "serve":
        return cg.serve_argv(cg.compose_file(tmp_path / "compose.yaml"), *extra)
    if verb == "read":
        return cg.read_argv(*extra)
    return cg.link_argv(*extra)


def _order(log: Path) -> list[str]:
    return [line.split()[0] for line in cg.log_lines(log)]


def _before_list(where: Path, log: Path, tag: str, *, status: int = 0) -> Path:
    """A list of one ``before`` gate that logs ``tag``, written as ``where``."""
    root = where.parent / f"{where.stem}-gates"
    cg.executable(root / "early.py", cg.gate_text(log, tag, status=status))
    return cg.write_list(where, str(root), [cg.entry("early.py", "before")])


@pytest.mark.parametrize("verb", VERBS)
def test_the_environments_list_runs_where_the_same_list_given_as_gates_runs(
    verb: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    by_flag, by_env = tmp_path / "flag.log", tmp_path / "env.log"

    cg.fake_door(tmp_path, monkeypatch, by_flag)
    listed = _before_list(tmp_path / "flag" / f"{verb}.json", by_flag, "caller:early")
    assert run.main(_argv(verb, tmp_path, "--gates", str(listed))) == 0

    folder = tmp_path / "folder"
    _before_list(folder / f"{verb}.json", by_env, "caller:early")
    (tmp_path / "again").mkdir()
    cg.fake_door(tmp_path / "again", monkeypatch, by_env)
    monkeypatch.setenv(run.GATES_ENV, str(folder))
    assert run.main(_argv(verb, tmp_path)) == 0

    assert "caller:early" in _order(by_env)
    assert _order(by_env) == _order(by_flag)


@pytest.mark.parametrize("verb", VERBS)
def test_a_gates_option_is_the_list_and_the_environments_is_not_read(
    verb: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    folder = tmp_path / "folder"
    _before_list(folder / f"{verb}.json", log, "caller:from-env")
    listed = _before_list(tmp_path / "flag.json", log, "caller:from-flag")
    monkeypatch.setenv(run.GATES_ENV, str(folder))

    assert run.main(_argv(verb, tmp_path, "--gates", str(listed))) == 0

    order = _order(log)
    assert "caller:from-flag" in order
    assert "caller:from-env" not in order


@pytest.mark.parametrize("verb", VERBS)
def test_a_folder_with_no_list_for_the_verb_adds_no_gate_to_it(
    verb: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    folder = tmp_path / "folder"
    other = "read" if verb != "read" else "serve"
    _before_list(folder / f"{other}.json", log, "caller:other-verb")
    monkeypatch.setenv(run.GATES_ENV, str(folder))

    assert run.main(_argv(verb, tmp_path)) == 0

    assert not any(name.startswith("caller:") for name in _order(log))


@pytest.mark.parametrize("value", ["", "relative/folder", "/no/such/folder"])
@pytest.mark.parametrize("verb", VERBS)
def test_a_value_that_names_no_folder_is_refused_before_any_gate(
    verb: str,
    value: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    monkeypatch.setenv(run.GATES_ENV, value)

    assert run.main(_argv(verb, tmp_path)) == 2

    assert _order(log) == []
    assert run.GATES_ENV in capsys.readouterr().err


@pytest.mark.parametrize("verb", VERBS)
def test_a_list_in_the_folder_is_held_to_the_rules_of_any_list(
    verb: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    folder = tmp_path / "folder"
    folder.mkdir()
    root = tmp_path / "caller"
    root.mkdir()
    listed = cg.write_list(
        folder / f"{verb}.json", str(root), [cg.entry("missing.py", "before")]
    )
    monkeypatch.setenv(run.GATES_ENV, str(folder))

    assert run.main(_argv(verb, tmp_path)) == 2

    assert _order(log) == []
    said = capsys.readouterr().err
    assert str(listed) in said and "missing.py" in said, said


@pytest.mark.parametrize("phase", ["after", "always"])
def test_a_link_takes_before_gates_alone(
    phase: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nothing runs after the link's timer: its reading is the last line."""
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    cg.executable(root / "late.py", cg.gate_text(log, "caller:late"))
    listed = cg.write_list(
        tmp_path / "link.json", str(root), [cg.entry("late.py", phase)]
    )

    assert run.main(cg.link_argv("--gates", str(listed))) == 2

    assert _order(log) == []
    assert phase in capsys.readouterr().err


def test_a_link_runs_its_before_gates_before_the_timer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    listed = _before_list(tmp_path / "link.json", log, "caller:early")

    assert run.main(cg.link_argv("--gates", str(listed))) == 0

    assert _order(log) == ["caller:early", f"door:{run.LINK_SEQUENCE[0].script}"]


# --------------------------------------------------------------------------
# mcgyvr's own door calls carry the environment's gates
# --------------------------------------------------------------------------


def _product_calls_the_door(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """The stub machine and an environment as a lab's wrapper sets it: a gates
    folder whose lists, one per verb, each hold one ``before`` gate that logs
    its verb and refuses. Returns the stub folder and the gates' log."""
    cg.clean_door_env(monkeypatch)
    stubs = usermode.machine(tmp_path, pending=())
    log = tmp_path / "gates.log"
    folder = tmp_path / "lists"
    for verb in VERBS:
        _before_list(folder / f"{verb}.json", log, f"caller:{verb}", status=2)
    monkeypatch.setenv(run.GATES_ENV, str(folder))
    monkeypatch.setenv(run.ROOT_ENV, str(usermode.install_root(tmp_path)))
    monkeypatch.setenv("PATH", f"{stubs}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("STUB_RIG_HOME", "/home/user")
    return stubs, log


def test_the_wakers_serve_carries_the_environments_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stubs, log = _product_calls_the_door(tmp_path, monkeypatch)
    argv = wake.door_argv(
        direction="down",
        host=usermode.RIG,
        compose=usermode.compose_file(tmp_path),
        suffix="w1",
    )

    done = subprocess.run(
        argv, capture_output=True, text=True, timeout=300, check=False
    )

    assert done.returncode == 2, done.stdout + done.stderr
    assert _order(log) == ["caller:serve"]
    assert onedoor.ssh_log(stubs) == []


def test_the_fleets_read_carries_the_environments_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The argv the fleet's read spawns (``spawn_read`` runs it as it is; the
    suite stands that function in for every test, so it is run here)."""
    stubs, log = _product_calls_the_door(tmp_path, monkeypatch)
    argv = read.door_read_argv(usermode.RIG, "run-20261008T000000-0a1b2c3d")

    done = subprocess.run(
        argv, capture_output=True, text=True, timeout=300, check=False
    )

    assert done.returncode == 2, done.stdout + done.stderr
    assert _order(log) == ["caller:read"]
    assert onedoor.ssh_log(stubs) == []


def test_the_fleets_probe_link_carries_the_environments_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stubs, log = _product_calls_the_door(tmp_path, monkeypatch)

    ran = linkread.DoorLinks().run(usermode.RIG, ["--peer", "0", "1"])

    assert ran.code == 2, ran.stderr
    assert _order(log) == ["caller:link"]
    assert onedoor.ssh_log(stubs) == []
