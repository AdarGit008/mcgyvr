"""A flag given a blank path is refused, not read as "the caller named none".

``--orchestrator ''`` is refused at parse time, because an id that names nobody
is a usage error before a file is opened. Every other flag on ``run`` that takes
a path was left with the defect that refusal was written to close, one flag
over: an empty string is falsy, so ``Path(args.result) if args.result else ...``
and ``Path(args.config) if args.config else None`` read it as *absent* and
resolved the default the caller never chose. ``--record`` is worse than that,
because it tests ``is not None`` instead: ``Path('')`` is ``Path('.')``, so
``--record ''`` journals into the current directory — the repository the
2026-09-03 ruling exists to keep clean — and prints a ``result:`` line relative
to a working directory the caller may not still be in.

What puts a blank there is not a person typing two quotes. It is
``--record "$JOURNAL_DIR"`` with ``JOURNAL_DIR`` unset, which is the shape every
wrapper script has, and the failure it produces is silent in all three cases:
exit 0, a run that looks finished, and its record somewhere nobody asked for.

So a blank is refused where the blank orchestrator is, through the subparser's
own ``error`` — exit 2, the usage code the skill documents — and for every flag
that takes a path, on every command that takes one, because "the same hole one
flag over" is exactly what this is.
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
    quietly falling back to whatever the environment would have resolved, which
    is the whole of the defect.
    """
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


@pytest.mark.parametrize("flag", ["--record", "--result", "--config"])
def test_a_blank_path_flag_on_run_is_refused(
    flag: str,
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exit 2 and the flag's own name, before a contract or a repo is read."""
    sent = lj.scripted(monkeypatch)  # nothing scripted: any dispatch is a failure
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config, flag, ""))

    assert code == 2, code
    assert flag in capsys.readouterr().err
    assert sent == [], "a refused run still dispatched"
    assert not journal.exists()


def test_a_blank_record_does_not_journal_into_the_current_directory(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The measured failure: ``Path('') == Path('.')``, and the cwd is a repo.

    Run from inside the repository, which is where a wrapper script runs, and
    assert on the directory rather than on the exit code: the refusal is only
    worth having because of what it stops landing here.
    """
    lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=tmp_path / "journal")
    contract = lj.make_contract(tmp_path / "impl.yaml", FORMAT)
    monkeypatch.chdir(repo)

    code = lj.main(lj.run_args(contract, repo, config, "--record", ""))

    assert code == 2, code
    assert not (repo / "results").exists(), "the result landed in the repository"
    assert list(repo.glob("*.jsonl")) == [], "the journal landed in the repository"
    assert not (repo / "blobs").exists(), "the blobs landed in the repository"


def test_a_blank_orchestrator_is_still_refused_by_its_own_message(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The id keeps its own sentence: it is not a path, and §9 is why.

    Both refusals are usage errors at the same seam, and one message for both
    would have to drop the reason either one gives.
    """
    lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=tmp_path / "journal")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config, "--orchestrator", ""))

    assert code == 2, code
    assert "§9" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "named"),
    [
        (["config", ""], "path"),
        (["pool", ""], "path"),
        (["catalog", "--against", ""], "--against"),
        (["emit", "--config", ""], "--config"),
    ],
)
def test_a_blank_config_path_is_refused_on_every_command_that_takes_one(
    argv: list[str],
    named: str,
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Not only ``run``. The same empty string, resolved the same silent way.

    Each of these reads the config through ``load(Path(x) if x else None)``, so a
    blank asked the loader to locate one — and then the loader's advice, which
    turns on whether anybody named a path, was answered for a caller who had.
    """
    code = lj.main(argv)

    assert code == 2, code
    assert named in capsys.readouterr().err
