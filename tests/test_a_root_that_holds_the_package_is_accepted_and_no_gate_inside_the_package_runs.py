"""A root that holds the package is accepted; a gate inside the package is not.

A caller's project may hold the installed package, in a virtual environment
or a checkout inside it, and its gates live beside it. So a list's root may
hold the package's folder, and may sit as high as the file system's top.
What the list may not do is run a file inside the package's folder, the
door's own scripts among them: such a gate is refused before any gate runs,
whether the list names it directly or through a link.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests import callergates as cg


def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A project folder whose virtual environment holds the package."""
    project = tmp_path / "top" / "project"
    package = project / ".venv" / "site" / "mcgyvr"
    (package / "serving").mkdir(parents=True)
    cg.executable(package / "serving" / "door-own.py", "#!/usr/bin/env python3\n")
    monkeypatch.setattr(run, "PACKAGE", package)
    return project, package


@pytest.mark.parametrize("height", ["project", "top", "above everything"])
def test_a_root_that_holds_the_package_runs_its_gates(
    height: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    project, _ = _project(tmp_path, monkeypatch)
    root = {
        "project": project,
        "top": project.parent,
        "above everything": tmp_path,
    }[height]
    cg.executable(project / "gates" / "mine.py", cg.gate_text(log, "caller:mine"))
    listed = cg.write_list(
        tmp_path / "gates.json",
        str(root),
        [cg.entry(str(project / "gates" / "mine.py"), "before")],
    )

    assert run.main(cg.read_argv("--gates", str(listed))) == 0

    assert "caller:mine" in [line.split()[0] for line in cg.log_lines(log)]


@pytest.mark.parametrize("how", ["named", "linked"])
def test_a_gate_inside_the_package_is_refused_before_any_gate(
    how: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cg.clean_door_env(monkeypatch)
    log = tmp_path / "order.log"
    cg.fake_door(tmp_path, monkeypatch, log)
    project, package = _project(tmp_path, monkeypatch)
    inside = package / "serving" / "door-own.py"
    if how == "named":
        path = str(inside)
    else:
        (project / "gates").mkdir()
        os.symlink(inside, project / "gates" / "link.py")
        path = "gates/link.py"
    listed = cg.write_list(
        tmp_path / "gates.json", str(project), [cg.entry(path, "before")]
    )

    assert run.main(cg.read_argv("--gates", str(listed))) == 2

    assert cg.log_lines(log) == []
    said = capsys.readouterr().err
    assert "gates[0]" in said and str(listed) in said, said
