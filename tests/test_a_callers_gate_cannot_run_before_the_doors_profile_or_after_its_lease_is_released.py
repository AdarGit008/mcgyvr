"""A caller's gates run inside the door's run, never around it.

Whatever order a gate list names its gates in, the door runs its own gates
all, in its own order, and places each caller gate by its phase.

On ``serve``: ``before`` after the door's profile gate and before the first
gate that reaches the machine, ``after`` after the door's identity and daemon
gates and before the step, ``always`` after the door's teardown gates and
before the lease is released. No caller gate runs before the profile or after
the release, and a refusal in one ``always`` gate does not stop the others or
the release.

On ``read``, which has no step, no teardown and no lease: ``before`` after the
read's profile gate and before anything is sent to the machine, ``after``
once the reading gate has read the machine and filed what it read. An
``after`` gate on a read cannot stop that filing; it runs only when the
reading gate admitted. No caller gate runs before the read's profile.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests import callergates as cg


def _three_phase_list(tmp_path: Path, log: Path, *, always_status: int = 0) -> Path:
    """One gate per phase, listed in the reverse of the order they run in."""
    root = tmp_path / "caller"
    for name in ("early", "late", "last", "final"):
        cg.executable(
            root / f"{name}.py",
            cg.gate_text(
                log, f"caller:{name}", status=always_status if name == "last" else 0
            ),
        )
    return cg.write_list(
        tmp_path / "gates.json",
        str(root),
        [
            cg.entry("last.py", "always"),
            cg.entry("final.py", "always"),
            cg.entry("late.py", "after"),
            cg.entry("early.py", "before"),
        ],
    )


def _order(log: Path) -> list[str]:
    return [line.split()[0] for line in cg.log_lines(log)]


def _door(entries: tuple[run.Entry, ...]) -> list[str]:
    return [f"door:{entry.script}" for entry in entries]


def test_a_serve_runs_every_door_gate_in_its_order_with_the_callers_inside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    listed = _three_phase_list(tmp_path, log)
    compose = cg.compose_file(tmp_path / "compose.yaml")

    assert run.main(cg.serve_argv(compose, "--gates", str(listed))) == 0

    order = _order(log)
    door_only = [name for name in order if name.startswith("door:")]
    assert door_only == _door((*run.SERVE_SEQUENCE, *run.ALWAYS, run.LEASE_RELEASE))
    assert order[0] == f"door:{run.SERVE_SEQUENCE[0].script}"
    assert order[-1] == f"door:{run.LEASE_RELEASE.script}"
    assert order[1] == "caller:early"
    assert order.index("door:03-image.py") < order.index("caller:late")
    assert order.index("door:02-rig.py") < order.index("caller:late")
    assert order.index("caller:late") < order.index("door:06-step.py")
    last_door_always = f"door:{run.ALWAYS[-1].script}"
    assert order[order.index(last_door_always) + 1 :] == [
        "caller:last",
        "caller:final",
        f"door:{run.LEASE_RELEASE.script}",
    ]


def test_a_read_runs_its_gates_in_order_with_before_and_after_inside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    for name in ("early", "late"):
        cg.executable(root / f"{name}.py", cg.gate_text(log, f"caller:{name}"))
    listed = cg.write_list(
        tmp_path / "gates.json",
        str(root),
        [cg.entry("late.py", "after"), cg.entry("early.py", "before")],
    )

    assert run.main(cg.read_argv("--gates", str(listed))) == 0

    profile, reading = _door(run.READ_SEQUENCE)
    assert _order(log) == [profile, "caller:early", reading, "caller:late"]


@pytest.mark.parametrize("status", [1, 2])
def test_a_read_whose_reading_gate_did_not_admit_runs_no_after_gate(
    status: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ``after`` gate on a read follows a reading that admitted, and no other."""
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    reading = run.READ_SEQUENCE[-1].script
    cg.fake_door(tmp_path, monkeypatch, log, statuses={reading: status})
    root = tmp_path / "caller"
    cg.executable(root / "late.py", cg.gate_text(log, "caller:late"))
    listed = cg.write_list(
        tmp_path / "gates.json", str(root), [cg.entry("late.py", "after")]
    )

    assert run.main(cg.read_argv("--gates", str(listed))) == status

    assert "caller:late" not in _order(log)


def test_a_read_refuses_a_list_with_an_always_gate_by_name_before_any_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A read has no lease and no teardown for an ``always`` gate to follow."""
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    listed = _three_phase_list(tmp_path, log)

    assert run.main(cg.read_argv("--gates", str(listed))) == 2

    assert _order(log) == []
    said = capsys.readouterr().err
    assert str(listed) in said and "last.py" in said and "always" in said, said


def test_a_step_that_fails_still_has_the_callers_always_gates_before_the_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log, statuses={"06-step.py": 1})
    listed = _three_phase_list(tmp_path, log)
    compose = cg.compose_file(tmp_path / "compose.yaml")

    assert run.main(cg.serve_argv(compose, "--gates", str(listed))) == 1

    assert _order(log)[-3:] == [
        "caller:last",
        "caller:final",
        f"door:{run.LEASE_RELEASE.script}",
    ]


def test_an_always_gate_that_refuses_stops_neither_the_next_nor_the_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    listed = _three_phase_list(tmp_path, log, always_status=3)
    compose = cg.compose_file(tmp_path / "compose.yaml")

    assert run.main(cg.serve_argv(compose, "--gates", str(listed))) != 0

    assert _order(log)[-3:] == [
        "caller:last",
        "caller:final",
        f"door:{run.LEASE_RELEASE.script}",
    ]


@pytest.mark.parametrize("verb", ["serve", "read"])
def test_a_before_gate_that_refuses_runs_no_door_gate_after_the_profile(
    verb: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    cg.executable(root / "no.py", cg.gate_text(log, "caller:no", status=2))
    cg.executable(root / "late.py", cg.gate_text(log, "caller:late"))
    cg.executable(root / "last.py", cg.gate_text(log, "caller:last"))
    listed = cg.write_list(
        tmp_path / "gates.json",
        str(root),
        [
            cg.entry("no.py", "before"),
            cg.entry("late.py", "after"),
            *([cg.entry("last.py", "always")] if verb == "serve" else []),
        ],
    )
    if verb == "serve":
        argv = cg.serve_argv(
            cg.compose_file(tmp_path / "c.yaml"), "--gates", str(listed)
        )
        profile = run.SERVE_SEQUENCE[0].script
    else:
        argv = cg.read_argv("--gates", str(listed))
        profile = run.READ_SEQUENCE[0].script

    assert run.main(argv) == 2
    assert _order(log) == [f"door:{profile}", "caller:no"]
