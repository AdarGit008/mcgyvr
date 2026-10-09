"""A caller's gate in phase ``before`` runs before anything is sent to the machine.

The door's first gate settles the profile and reads no machine; the next one
reaches it. A caller that must refuse a run before the machine is touched
names its gate ``before`` in its gate list, and the door runs it between the
two. A ``before`` gate that refuses ends the run with nothing sent to the
machine, on ``serve`` and on ``read``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests import callergates as cg


def _stopping_list(tmp_path: Path) -> tuple[Path, Path]:
    """A list whose one ``before`` gate writes a marker and refuses."""
    root = tmp_path / "caller"
    marker = tmp_path / "marker.log"
    cg.executable(
        root / "stop.py",
        cg.gate_text(marker, "caller:stop", show=("RUN_PROFILE",), status=2),
    )
    listed = cg.write_list(
        tmp_path / "gates.json", str(root), [cg.entry("stop.py", "before")]
    )
    return listed, marker


def test_a_refusing_before_gate_ends_a_read_with_nothing_sent_to_the_machine(
    tmp_path: Path,
) -> None:
    """The real read gates, a machine that logs every call: the log stays empty."""
    stubs, calls = cg.stub_machine(tmp_path)
    listed, marker = _stopping_list(tmp_path)
    done = cg.door_process(
        cg.read_argv("--gates", str(listed)),
        stubs=stubs,
        run_root=cg.door_root(tmp_path),
        cwd=tmp_path,
    )

    assert done.returncode == 2, done.stderr
    (line,) = cg.log_lines(marker)
    assert "RUN_PROFILE=-" not in line, (
        f"the before gate ran without the profile the door settles first: {line}"
    )
    assert cg.log_lines(calls) == [], (
        "the machine was reached before the caller's before gate refused: "
        f"{cg.log_lines(calls)}"
    )
    assert "stop.py" in done.stderr


def test_a_refusing_before_gate_ends_a_serve_with_nothing_sent_to_the_machine(
    tmp_path: Path,
) -> None:
    """The same for ``serve``: its profile gate runs, then the caller's gate."""
    stubs, calls = cg.stub_machine(tmp_path)
    listed, marker = _stopping_list(tmp_path)
    run_root = cg.door_root(tmp_path)
    cg.round_stub(run_root)
    done = cg.door_process(
        cg.serve_argv(
            cg.compose_file(tmp_path / "compose.yaml"),
            "--gates",
            str(listed),
        ),
        stubs=stubs,
        run_root=run_root,
        cwd=tmp_path,
    )

    assert done.returncode == 2, done.stderr
    (line,) = cg.log_lines(marker)
    assert "RUN_PROFILE=-" not in line, line
    assert cg.log_lines(calls) == [], cg.log_lines(calls)
    assert "stop.py" in done.stderr


@pytest.mark.parametrize("verb", ["serve", "read"])
def test_an_admitting_before_gate_runs_between_the_profile_and_the_machine(
    verb: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In the order of a whole run: the profile, the caller's gate, the machine."""
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    cg.executable(root / "early.py", cg.gate_text(log, "caller:early"))
    listed = cg.write_list(
        tmp_path / "gates.json", str(root), [cg.entry("early.py", "before")]
    )
    if verb == "serve":
        compose = cg.compose_file(tmp_path / "compose.yaml")
        argv = cg.serve_argv(compose, "--gates", str(listed))
        sequence = run.SERVE_SEQUENCE
    else:
        argv = cg.read_argv("--gates", str(listed))
        sequence = run.READ_SEQUENCE

    assert run.main(argv) == 0
    order = [line.split()[0] for line in cg.log_lines(log)]
    assert order[:3] == [
        f"door:{sequence[0].script}",
        "caller:early",
        f"door:{sequence[1].script}",
    ], order
