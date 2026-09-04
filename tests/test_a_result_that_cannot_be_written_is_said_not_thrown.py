"""A result file that cannot be written is reported in words, never as a traceback.

``mcgyvr run`` printed ``result: <path>`` from an unguarded ``write``. A
journal directory on a read-only mount, or ``--result`` naming a directory,
raised ``OSError`` out of ``main`` after the accepted change had already been
placed in the working tree: exit 1, a traceback, no ``result:`` line — which
the skill reads as "the run never started" — and a ``.part`` file left
behind. Now the failure is one ``error:`` line on stderr that names the
path, the reason, and what the run came to, so the caller is told the change
is in the tree even though the file that would have said so is not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.result import RunResult, write
from tests import livejournal as lj


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


def test_write_leaves_no_part_file_when_the_replace_fails(tmp_path: Path) -> None:
    taken = tmp_path / "results" / "impl-1.json"
    taken.mkdir(parents=True)
    report = RunResult(contract="impl", task_type="t", target="x", orchestrator="o")

    with pytest.raises(OSError):
        write(taken, report)

    assert sorted(p.name for p in taken.parent.iterdir()) == ["impl-1.json"]


def test_a_result_path_that_is_a_directory_is_an_error_line_not_a_traceback(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")
    blocked = tmp_path / "a-directory"
    blocked.mkdir()

    code = lj.main(lj.run_args(contract, repo, config, "--result", str(blocked)))

    out, err = capsys.readouterr()
    assert code == 1
    assert "result: " not in out
    assert "Traceback" not in err
    (line,) = [line for line in err.splitlines() if line.startswith("error: ")]
    assert str(blocked) in line
    assert "accepted" in line, line
    assert "src/pkg/messy.py" in line, line
    assert (repo / "src/pkg/messy.py").read_text() == "VALUE = 1\n"
    assert not list(tmp_path.glob("**/.*.part")), "no staging file left behind"
