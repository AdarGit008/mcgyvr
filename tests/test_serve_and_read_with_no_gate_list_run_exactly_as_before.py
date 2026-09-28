"""Without a gate list, `serve` and `read` run only the door's own gates.

A gate list is something a caller adds. A caller that adds none gets the
door's runs as they are: every gate of the door, in the door's order, each
under the door's run root, and the same exit status for the same gate
outcomes.
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
