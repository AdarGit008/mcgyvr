"""A blank ``--orchestrator`` is refused, not filed under an empty name.

``--orchestrator ''`` is the flag saying nothing, and nothing is the one answer
:mod:`mcgyvr.session` does not accept: "a run nobody can be traced to is
refused, not filed under a default". It was accepted anyway. ``resolve('')``
built ``Session('')`` because an empty string starts with neither ``claude-``
nor ``pi-``, and from there the two paths diverged into two different wrong
answers. On the deterministic floor nothing ever constructs a
:class:`~mcgyvr.drive.Recording`, so nobody looked at the name: the run
succeeded, exit 0, and left a result file whose ``orchestrator`` is ``""`` —
a row filed under nobody. On the ladder path ``Recording.__post_init__``
caught it, but only after the config and the contract had been read, and it
came out as exit 1 — an error, where the skill documents exit 2 for a run with
no session to file itself under.

Both are the same defect: an id that names nobody is a *usage* error, and it is
one before a file is opened. So it is refused where the missing session already
is — in :func:`~mcgyvr.cli._name_the_writer`, through the subparser's own
``error``, exit 2 — on both paths, and the environment's session does not stand
in for it. A caller who typed the flag asked to name the writer; a blank value
is that caller getting the id wrong, not that caller declining to pass one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import livejournal as lj

FORMAT = """
id: tidy
task_type: format
task: Reformat the module.
target: src/pkg/messy.py
scope:
  allow: ["src/**"]
"""


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A HOME of this test's own, with a session in the environment.

    The session is there on purpose: a blank flag must be refused rather than
    quietly falling back to the session that happens to be exported, which
    would file the run under a writer the caller did not name.
    """
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


def test_a_blank_orchestrator_is_refused_on_the_ladder_path(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exit 2, the usage code the skill documents, and nothing dispatched."""
    sent = lj.scripted(monkeypatch)  # nothing scripted: any dispatch is a failure
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config, "--orchestrator", ""))

    assert code == 2, code
    assert "--orchestrator" in capsys.readouterr().err
    assert sent == [], "a refused run still dispatched"
    assert not journal.exists()


def test_a_blank_orchestrator_is_refused_on_the_deterministic_floor_too(
    tmp_path: Path,
    home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The floor journals nothing, so nothing there would have caught the name.

    The result file is where an empty id surfaced: a deterministic run wrote
    one saying ``"orchestrator": ""`` and exited 0. So the assertion is that no
    result was written at all — the run never started.
    """
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)

    code = lj.main(lj.run_args(contract, repo, config, "--orchestrator", ""))

    out = capsys.readouterr()
    assert code == 2, f"stdout: {out.out}\nstderr: {out.err}"
    assert "--orchestrator" in out.err
    assert "result: " not in out.out, out.out
    assert not journal.exists(), sorted(str(p) for p in journal.rglob("*"))
    assert lj.git(repo, "status", "--porcelain") == "", "a refused run touched the repo"


def test_a_whitespace_only_orchestrator_is_the_same_refusal(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``' '`` names a writer no better than ``''`` does, and files worse."""
    sent = lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config, "--orchestrator", "   "))

    assert code == 2, code
    assert "--orchestrator" in capsys.readouterr().err
    assert sent == []
    assert not journal.exists()


def test_the_refusal_lands_before_the_contract_is_read(
    tmp_path: Path,
    home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Parse time, not run time: a contract that does not exist is never reached.

    A contract that cannot be loaded is exit 1. If the blank id were caught
    anywhere inside ``_run`` this would come back as that instead, which is the
    ladder path's old answer with a different message.
    """
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=tmp_path / "journal")

    code = lj.main(
        lj.run_args(tmp_path / "nowhere.yaml", repo, config, "--orchestrator", "")
    )

    assert code == 2, code
    err = capsys.readouterr().err
    assert "--orchestrator" in err
    assert "nowhere.yaml" not in err, err
