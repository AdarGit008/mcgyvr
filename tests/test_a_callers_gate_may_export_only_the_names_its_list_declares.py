"""A caller's gate passes on only the names its list declares, and none of the door's.

A gate passes a fact to the gates after it as ``KEY=VALUE`` on the export
descriptor. A caller's gate may pass a name its list declares for it, and the
gates after it, the door's included, see it. A name the list does not declare
is refused, and so is a list declaring a name the door sets itself or a name
outside the door's ``RUN_`` vocabulary, since either would change what a
door gate reads. A caller's gate sees the list's root as ``RUN_ROOT``; the
door's gates keep the door's.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests import callergates as cg

#: Every name the door sets for its own gates today, read from the door.
DOOR_NAMES = sorted(
    {
        *run.EXPORTED,
        *(name for entry in run.READ_SEQUENCE for name in entry.exports),
        "RUN_EXPORT_FD",
    }
)


def test_a_declared_export_reaches_the_gates_after_it_the_doors_included(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log, show=("RUN_LAB_MARK",))
    root = tmp_path / "caller"
    cg.executable(
        root / "mark.py",
        cg.gate_text(log, "caller:mark", exports={"RUN_LAB_MARK": "seen"}),
    )
    cg.executable(
        root / "look.py", cg.gate_text(log, "caller:look", show=("RUN_LAB_MARK",))
    )
    listed = cg.write_list(
        tmp_path / "gates.json",
        str(root),
        [
            cg.entry("mark.py", "before", ["RUN_LAB_MARK"]),
            cg.entry("look.py", "after"),
        ],
    )

    assert run.main(cg.read_argv("--gates", str(listed))) == 0

    lines = {line.split()[0]: line for line in cg.log_lines(log)}
    assert "RUN_LAB_MARK=seen" in lines["caller:look"]
    assert "RUN_LAB_MARK=seen" in lines[f"door:{run.READ_SEQUENCE[1].script}"]
    assert "RUN_LAB_MARK=-" in lines[f"door:{run.READ_SEQUENCE[0].script}"]


def test_an_export_the_list_does_not_declare_is_refused_and_the_run_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    cg.executable(
        root / "sneak.py",
        cg.gate_text(log, "caller:sneak", exports={"RUN_LAB_UNDECLARED": "x"}),
    )
    listed = cg.write_list(
        tmp_path / "gates.json", str(root), [cg.entry("sneak.py", "before")]
    )

    assert run.main(cg.read_argv("--gates", str(listed))) == 2

    assert [line.split()[0] for line in cg.log_lines(log)] == [
        f"door:{run.READ_SEQUENCE[0].script}",
        "caller:sneak",
    ]
    said = capsys.readouterr().err
    assert "RUN_LAB_UNDECLARED" in said and "sneak.py" in said, said


@pytest.mark.parametrize("name", DOOR_NAMES)
def test_a_list_declaring_a_name_the_door_sets_is_refused_before_any_gate(
    name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    cg.executable(root / "claim.py", cg.gate_text(log, "caller:claim"))
    listed = cg.write_list(
        tmp_path / "gates.json", str(root), [cg.entry("claim.py", "after", [name])]
    )

    assert run.main(cg.read_argv("--gates", str(listed))) == 2

    assert cg.log_lines(log) == []
    said = capsys.readouterr().err
    assert name in said and str(listed) in said, said


@pytest.mark.parametrize(
    "name", ["PATH", "LD_PRELOAD", "PYTHONPATH", "MCGYVR_CONFIG", "DOCKER_HOST"]
)
def test_a_list_declaring_a_name_outside_the_doors_vocabulary_is_refused(
    name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    cg.executable(root / "claim.py", cg.gate_text(log, "caller:claim"))
    listed = cg.write_list(
        tmp_path / "gates.json", str(root), [cg.entry("claim.py", "before", [name])]
    )
    compose = cg.compose_file(tmp_path / "compose.yaml")

    assert run.main(cg.serve_argv(compose, "--gates", str(listed))) == 2

    assert cg.log_lines(log) == []
    said = capsys.readouterr().err
    assert name in said and str(listed) in said, said


def test_a_callers_gate_sees_the_lists_root_and_the_doors_gates_keep_the_doors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    root = tmp_path / "caller"
    cg.executable(root / "early.py", cg.gate_text(log, "caller:early"))
    listed = cg.write_list(
        tmp_path / "gates.json", str(root), [cg.entry("early.py", "before")]
    )
    compose = cg.compose_file(tmp_path / "compose.yaml")

    assert run.main(cg.serve_argv(compose, "--gates", str(listed))) == 0

    roots = {line.split()[0]: line.split()[1] for line in cg.log_lines(log)}
    assert roots.pop("caller:early") == f"root={root.resolve()}"
    door_root = f"root={cg.door_root(tmp_path).resolve()}"
    assert set(roots.values()) == {door_root}, roots
