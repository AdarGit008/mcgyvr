"""A caller's gate is ended at its time bound, and a signal ends an ``always`` one.

Each gate of a list runs for at most its ``timeout_s``, or a stated default.
A gate over its bound is ended with its process group, and that is a
refusal naming the gate and the bound. A gate that exits but leaves a
process holding its export descriptor does not keep the door waiting past
the bound. A signal to the door while a caller's ``always`` gate runs ends
that gate. The lease is released in every case.
"""

from __future__ import annotations

import re
import signal
import time
from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests import callergates as cg

RELEASE = f"door:{run.LEASE_RELEASE.script}"


def _sleeper(root: Path, log: Path, name: str, body: str) -> None:
    cg.executable(
        root / f"{name}.py",
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import os, time",
                f"line = f'caller:{name} pid={{os.getpid()}}\\n'",
                f"open({str(log)!r}, 'a').write(line)",
                body,
                f"open({str(log)!r}, 'a').write('caller:{name}-end\\n')",
                "",
            ]
        ),
    )


def _pid(log: Path, name: str) -> int:
    for line in cg.log_lines(log):
        match = re.match(rf"caller:{name} pid=(\d+)", line)
        if match:
            return int(match.group(1))
    raise AssertionError(f"{name} never started: {cg.log_lines(log)}")


def test_a_gate_over_its_bound_is_ended_as_a_refusal_and_the_lease_released(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    _sleeper(root, log, "slow", "time.sleep(60)")
    gate = cg.entry("slow.py", "after")
    gate["timeout_s"] = 1
    listed = cg.write_list(tmp_path / "gates.json", str(root), [gate])
    compose = cg.compose_file(tmp_path / "compose.yaml")

    started = time.monotonic()
    status = run.main(cg.serve_argv(compose, "--gates", str(listed)))
    took = time.monotonic() - started

    said = capsys.readouterr().err
    assert status == 2, said
    assert took < 30, took
    assert "slow.py" in said and "bound of 1 s" in said, said
    assert "its process group" in said, said
    order = [line.split()[0] for line in cg.log_lines(log)]
    assert "caller:slow-end" not in order
    assert order[-1] == RELEASE, order
    assert not cg.alive(_pid(log, "slow"))


def test_a_gate_leaving_a_process_on_its_exports_waits_no_longer_than_its_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    _sleeper(root, log, "leaver", "os.system('sleep 60 &')")
    gate = cg.entry("leaver.py", "before")
    gate["timeout_s"] = 2
    listed = cg.write_list(tmp_path / "gates.json", str(root), [gate])

    started = time.monotonic()
    status = run.main(cg.read_argv("--gates", str(listed)))
    took = time.monotonic() - started

    said = capsys.readouterr().err
    assert status == 2, said
    assert took < 30, took
    assert "leaver.py" in said and "bound of 2 s" in said, said


@pytest.mark.parametrize("verb", ["serve", "read"])
def test_the_help_says_the_default_bound(
    verb: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        run.main([verb, "--help"])
    said = " ".join(capsys.readouterr().out.split())
    assert f"{run.CALLER_GATE_TIMEOUT_S:g} s" in said, said
    assert "timeout_s" in said, said


def test_a_signal_during_a_callers_always_gate_ends_it_and_the_lease_is_released(
    tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    log = work / "order.log"
    root = work / "caller"
    _sleeper(root, log, "slow", "time.sleep(60)")
    gate = cg.entry("slow.py", "always")
    gate["timeout_s"] = 120
    listed = cg.write_list(work / "gates.json", str(root), [gate])
    compose = cg.compose_file(work / "compose.yaml")
    door = cg.driven_door(work, log, cg.serve_argv(compose, "--gates", str(listed)))
    try:
        deadline = time.monotonic() + 60
        while not any(line.startswith("caller:slow") for line in cg.log_lines(log)):
            assert door.poll() is None, door.communicate()
            assert time.monotonic() < deadline, cg.log_lines(log)
            time.sleep(0.1)
        pid = _pid(log, "slow")
        door.send_signal(signal.SIGTERM)
        _, said = door.communicate(timeout=30)
    finally:
        if door.poll() is None:
            door.kill()
            door.wait()

    order = [line.split()[0] for line in cg.log_lines(log)]
    assert "caller:slow-end" not in order
    assert order[-1] == RELEASE, (order, said)
    assert not cg.alive(pid)
    assert "slow.py" in said, said
