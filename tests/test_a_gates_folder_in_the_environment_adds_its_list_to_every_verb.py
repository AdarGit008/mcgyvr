"""``$MCGYVR_DOOR_GATES`` adds a caller's gate list to every verb's run.

Owner, 2026-10-08 (design 2b): a caller hands the door its gates from the
environment as well as with ``--gates``: ``MCGYVR_DOOR_GATES=<folder>``, and
a ``serve``, ``read``, ``link`` or ``step`` run loads
``<folder>/<verb>.json``. Owner, on mcgyvr#633: with ``--gates`` given too,
both lists run, the environment's first and then the option's in each phase,
and the door warns on stderr that ``MCGYVR_DOOR_GATES`` is also set; neither
list can be skipped, and a name both lists export is refused. So a door
mcgyvr's own code opens (the waker, the fleet's read and probe, the commands
live admission prints) carries the caller's gates too, with no product code
naming them. A list from the environment is a ``--gates`` list in every way:
placed by phase, held to the same rules, and never in place of a door gate.
A folder with no list for a verb adds none; a value that names no folder is
refused before any gate.

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


def _both(
    verb: str, tmp_path: Path, log: Path, *, env_status: int = 0, flag_status: int = 0
) -> Path:
    """A folder list and a ``--gates`` list for ``verb``, each with one gate in
    every phase the verb has. Returns the ``--gates`` list."""
    phases = {"read": ("before", "after"), "link": ("before",)}.get(
        verb, ("before", "after", "always")
    )
    lists = {}
    for source, status in (("env", env_status), ("flag", flag_status)):
        root = tmp_path / f"{source}-gates"
        for phase in phases:
            cg.executable(
                root / f"{phase}.py",
                cg.gate_text(log, f"{source}:{phase}", status=status),
            )
        where = tmp_path / source / f"{verb}.json"
        where.parent.mkdir(parents=True, exist_ok=True)
        lists[source] = cg.write_list(
            where, str(root), [cg.entry(f"{phase}.py", phase) for phase in phases]
        )
    return lists["flag"]


@pytest.mark.parametrize("verb", VERBS)
def test_with_both_the_environments_list_runs_first_then_the_options_per_phase(
    verb: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    listed = _both(verb, tmp_path, log)
    monkeypatch.setenv(run.GATES_ENV, str(tmp_path / "env"))

    assert run.main(_argv(verb, tmp_path, "--gates", str(listed))) == 0

    callers = [name for name in _order(log) if not name.startswith("door:")]
    phases = [name.split(":")[1] for name in callers[::2]]
    assert callers == [
        name for phase in phases for name in (f"env:{phase}", f"flag:{phase}")
    ]
    assert phases[0] == "before"
    said = capsys.readouterr().err
    assert run.GATES_ENV in said and "also set" in said, said


@pytest.mark.parametrize("refusing", ["env", "flag"])
@pytest.mark.parametrize("verb", VERBS)
def test_with_both_a_refusal_in_either_list_ends_the_run(
    verb: str, refusing: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Neither list can be skipped: the other one admitting changes nothing."""
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    listed = _both(
        verb,
        tmp_path,
        log,
        env_status=2 if refusing == "env" else 0,
        flag_status=2 if refusing == "flag" else 0,
    )
    monkeypatch.setenv(run.GATES_ENV, str(tmp_path / "env"))

    assert run.main(_argv(verb, tmp_path, "--gates", str(listed))) == 2

    order = _order(log)
    assert f"{refusing}:before" in order
    assert "door:06-step.py" not in order
    if refusing == "env":
        assert "flag:before" not in order


@pytest.mark.parametrize("verb", VERBS)
def test_with_both_a_name_both_lists_export_is_refused_before_any_gate(
    verb: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    lists = []
    for source in ("env", "flag"):
        root = tmp_path / f"{source}-gates"
        cg.executable(root / "early.py", cg.gate_text(log, f"{source}:before"))
        where = tmp_path / source / f"{verb}.json"
        where.parent.mkdir(parents=True)
        lists.append(
            cg.write_list(
                where, str(root), [cg.entry("early.py", "before", ["RUN_SHARED_X"])]
            )
        )
    monkeypatch.setenv(run.GATES_ENV, str(tmp_path / "env"))

    assert run.main(_argv(verb, tmp_path, "--gates", str(lists[1]))) == 2

    assert _order(log) == []
    assert "RUN_SHARED_X" in capsys.readouterr().err


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


@pytest.mark.parametrize("verb", VERBS)
def test_the_folders_list_named_again_by_gates_runs_once(
    verb: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One file named both ways, the option by a link to it, is one list."""
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    folder = tmp_path / "folder"
    listed = _before_list(folder / f"{verb}.json", log, "caller:early")
    link = tmp_path / "linked.json"
    link.symlink_to(listed)
    monkeypatch.setenv(run.GATES_ENV, str(folder))

    assert run.main(_argv(verb, tmp_path, "--gates", str(link))) == 0

    assert _order(log).count("caller:early") == 1
