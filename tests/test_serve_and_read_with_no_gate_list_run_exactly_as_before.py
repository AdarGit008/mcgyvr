"""Without a gate list, `serve` and `read` run only the door's own gates.

A gate list is something a caller adds. A caller that adds none gets the
door's runs as they are: every gate of the door, in the door's order, each
under the door's run root, and the same exit status for the same gate
outcomes. A door gate that writes a line that is not ``KEY=VALUE`` is
refused quoting the whole line, as before.

One change to these runs is deliberate: a door gate that exports a value
holding a NUL is refused by name, with status 2, and the lease is released.
Before, the door raised ValueError when it started the next process with
that value, and the lease was never released.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests import callergates as cg


def _lines(log: Path) -> list[tuple[str, str]]:
    return [(line.split()[0], line.split()[1]) for line in cg.log_lines(log)]


def test_a_serve_runs_its_sequence_its_always_gates_and_its_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    compose = cg.compose_file(tmp_path / "compose.yaml")

    assert run.main(cg.serve_argv(compose)) == 0

    root = f"root={cg.door_root(tmp_path).resolve()}"
    assert _lines(log) == [
        (f"door:{entry.script}", root)
        for entry in (*run.SERVE_SEQUENCE, *run.ALWAYS, run.LEASE_RELEASE)
    ]


def test_a_serve_whose_step_fails_ends_with_the_steps_status_after_its_teardown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log, statuses={"06-step.py": 1})
    compose = cg.compose_file(tmp_path / "compose.yaml")

    assert run.main(cg.serve_argv(compose)) == 1

    assert [name for name, _ in _lines(log)] == [
        f"door:{entry.script}"
        for entry in (*run.SERVE_SEQUENCE, *run.ALWAYS, run.LEASE_RELEASE)
    ]


def test_a_serve_gate_that_refuses_ends_the_run_at_that_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    refusing = run.SERVE_SEQUENCE[1].script
    cg.fake_door(tmp_path, monkeypatch, log, statuses={refusing: 2})
    compose = cg.compose_file(tmp_path / "compose.yaml")

    assert run.main(cg.serve_argv(compose)) == 2

    assert [name for name, _ in _lines(log)][:2] == [
        f"door:{run.SERVE_SEQUENCE[0].script}",
        f"door:{refusing}",
    ]
    assert f"door:{run.SERVE_SEQUENCE[2].script}" not in [n for n, _ in _lines(log)]


def test_a_read_runs_its_sequence_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)

    assert run.main(cg.read_argv()) == 0

    root = f"root={cg.door_root(tmp_path).resolve()}"
    assert _lines(log) == [
        (f"door:{entry.script}", root) for entry in run.READ_SEQUENCE
    ]


@pytest.mark.parametrize("status", [2, 3])
def test_a_read_ends_with_the_status_its_reading_gate_gave(
    status: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    last = run.READ_SEQUENCE[-1].script
    cg.fake_door(tmp_path, monkeypatch, log, statuses={last: status})

    assert run.main(cg.read_argv()) == status

    assert [name for name, _ in _lines(log)] == [
        f"door:{entry.script}" for entry in run.READ_SEQUENCE
    ]


def _door_gate_writes(gates: Path, script: str, data: bytes) -> None:
    """Make the stand-in for the door's ``script`` write ``data`` on its exports."""
    cg.executable(
        gates / script,
        "#!/usr/bin/env python3\nimport os\n"
        "fd = int(os.environ['RUN_EXPORT_FD'])\n"
        f"os.write(fd, {data!r})\n",
    )


def test_a_door_gates_line_that_is_not_key_value_is_quoted_whole(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    gates = cg.fake_door(tmp_path, monkeypatch, log)
    line = "not a fact " + "z" * 300
    _door_gate_writes(gates, run.SERVE_SEQUENCE[2].script, f"{line}\n".encode())
    compose = cg.compose_file(tmp_path / "compose.yaml")

    assert run.main(cg.serve_argv(compose)) == 2

    said = capsys.readouterr().err
    assert repr(line) in said, said


def test_a_door_gate_exporting_a_nul_is_refused_by_name_and_the_lease_released(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The one deliberate change to a run with no gate list."""
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    gates = cg.fake_door(tmp_path, monkeypatch, log)
    image = run.SERVE_SEQUENCE[2].script
    _door_gate_writes(gates, image, b"RUN_IMAGE_NOTE=a\x00b\n")
    compose = cg.compose_file(tmp_path / "compose.yaml")

    assert run.main(cg.serve_argv(compose)) == 2

    said = capsys.readouterr().err
    assert f"{image} exported RUN_IMAGE_NOTE with a NUL byte" in said, said
    assert [name for name, _ in _lines(log)][-1] == f"door:{run.LEASE_RELEASE.script}"
