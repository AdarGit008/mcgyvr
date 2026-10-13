"""A ``rename_symbol`` run says what it ran and which files and lines it renamed.

e2e run 2, R3: the echoed command was a bare ``$ `` — ``rename_symbol`` has no
argv, and joining nothing printed a prompt that named no command — and the
rename's own report ("5 occurrence(s) in 2 file(s)" and the files) reached
neither stdout, nor the result file's notes, nor the journal. The user saw an
acceptance and no account of what was touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import livejournal as lj
from tests.renamecommits import _run


def test_the_run_names_the_operation_and_reports_every_renamed_file(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, journal, code = _run(tmp_path, monkeypatch)

    out = capsys.readouterr().out
    assert code == 0, out
    lines = out.splitlines()
    assert "  $ " not in lines and "  $" not in lines, "a bare prompt was echoed"
    assert "  (in-process) rename_symbol fetch_page -> fetch_document" in lines
    assert any(
        "renamed fetch_page -> fetch_document:" in line
        and "occurrence(s) in 2 file(s)" in line
        for line in lines
    ), out
    assert any(line.strip().startswith("src/pkg/use.py") for line in lines), out
    assert any(line.strip().startswith("src/pkg/web.py") for line in lines), out

    result = json.loads(lj.result_path(out).read_text())
    (note,) = [n for n in result["notes"] if "rename_symbol" in n]
    assert "src/pkg/use.py" in note and "src/pkg/web.py" in note

    raw = [
        json.loads(line)
        for path in sorted(journal.glob("*.jsonl"))
        for line in path.read_text().splitlines()
    ]
    verdicts = [r for r in raw if r.get("outcome") == "passed"]
    assert verdicts, raw
    assert "src/pkg/use.py" in verdicts[0]["detail"]
    assert "src/pkg/web.py" in verdicts[0]["detail"]


def test_a_program_step_is_still_echoed_as_its_command_line() -> None:
    from mcgyvr.cli import _ran
    from mcgyvr.contract import loads
    from mcgyvr.deterministic import tool_steps

    (step,) = tool_steps(
        loads(
            "id: tidy\ntask_type: code\noperation: format\n"
            "task: Reformat.\ntarget: src/pkg/messy.py\n"
            'scope:\n  allow: ["src/**"]\n'
        )
    )

    assert _ran(step) == "$ ruff format -- src/pkg/messy.py"
