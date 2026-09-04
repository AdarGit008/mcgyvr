"""A deterministic run is a run, and the corpus holds it.

``_run`` built a :class:`~mcgyvr.drive.Recording` only for a contract that was
not deterministic, and :func:`~mcgyvr.cli._floor` journalled nothing, so every
``format``, ``import_sort`` and ``lint_fix`` run left the corpus a loose
``results/*.json`` that ``tools/live/index.py`` does not read. The cheap tier
is the tier most work goes through, and it was the one tier no question could
be asked about.

The question it was hiding is the one the ladder exists to answer. "How often
does the floor finish this task type on its own" is the whole economic case for
a deterministic tier, and it cannot be computed from a table that contains only
the runs the floor did *not* handle. Neither can "what does escalation cost" —
the denominator was missing.

So the floor writes a row, on the same terms as a dispatch: written before the
gate, keyed the same way, corrected with its verdict and then with how the work
landed. It is not a dispatch and does not pretend to be one — no prompt, no
reply, no endpoint, no tokens, and ``tier`` says ``deterministic`` beside a
``rung`` that is a program's name rather than a model's. What makes it worth
having is that it is in the same table as the dispatches, so the two can be
counted against each other in one query.
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
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


@pytest.fixture
def ours(tmp_path: Path) -> Path:
    return tmp_path / "corpus"


def floor_row(ours: Path) -> dict[str, object]:
    found = lj.rows(ours)
    assert len(found) == 1, found
    return found[0]


def test_the_floor_writes_a_row_the_corpus_can_be_asked_about(
    tmp_path: Path,
    home: Path,
    ours: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The identity a query needs: whose run, what kind of work, which tier."""
    lj.scripted(monkeypatch)  # nothing scripted: the floor must dispatch nothing
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=ours)
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)

    lj.main(lj.run_args(contract, repo, config))

    row = floor_row(ours)
    assert row["orchestrator"] == "claude-s1"
    assert row["task_type"] == "format"
    assert row["tier"] == "deterministic"
    assert "tidy" in str(row["attempt_id"])


def test_the_floor_row_names_the_program_that_did_the_work(
    tmp_path: Path,
    home: Path,
    ours: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``rung`` is a program here, and ``tier`` is what keeps that unambiguous.

    A ladder rung and a tool cannot collide in a query that reads ``tier``
    first, which is why the column is worth its width.
    """
    lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=ours)
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)

    lj.main(lj.run_args(contract, repo, config))

    assert floor_row(ours)["rung"] == "ruff"


def test_the_floor_row_claims_no_dispatch_it_did_not_make(
    tmp_path: Path,
    home: Path,
    ours: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Absent, not null and not zero: there was no model and no conversation.

    A row carrying ``input_tokens: 0`` would be counted by anything averaging
    them, and a run that dispatched nothing must not drag a mean toward zero.
    """
    lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=ours)
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)

    lj.main(lj.run_args(contract, repo, config))

    row = floor_row(ours)
    for absent in (
        "prompt_sha256",
        "reply_sha256",
        "endpoint",
        "model",
        "input_tokens",
        "output_tokens",
        "bundle_sha256",
    ):
        assert absent not in row, absent
    assert lj.blobs(ours) == set(), "a run that sent nothing stored a blob"


def test_the_floor_row_carries_how_the_work_landed(
    tmp_path: Path,
    home: Path,
    ours: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Written before the gate, corrected after it — the dispatch's own shape.

    Without ``--commit`` an accepted change is left in the target, and the
    folded outcome is the word for that, so the corpus can tell an accepted
    change that shipped from one still sitting in a working tree.
    """
    lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=ours)
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)

    lj.main(lj.run_args(contract, repo, config))

    assert floor_row(ours)["outcome"] == "not_committed"


def test_a_floor_run_that_could_not_run_says_so_on_its_row(
    tmp_path: Path,
    home: Path,
    ours: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ "The floor could not" is an answer, and the corpus has to hold it.

    A missing program is the commonest thing that stops a floor run, and it is
    the case the ratio most needs: a tier that finishes nothing on this machine
    is a different fact from a tier that was never asked. An uncorrected row
    reads as a run that died before anything judged it, so the verdict is
    written the way a climb's raised attempt's is — ``error``, with the reason.
    """
    import mcgyvr.drive as drive
    from mcgyvr.drive import ToolOutcome

    lj.scripted(monkeypatch)
    # Patched on `drive` and not on `cli`: `_floor` imports the name inside the
    # function, so the module it is looked up on is the one that defines it.
    monkeypatch.setattr(
        drive,
        "run_tool_step",
        lambda step, sandbox: ToolOutcome(
            step=step, environment_issue="ruff is not on PATH"
        ),
    )
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=ours)
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)

    assert lj.main(lj.run_args(contract, repo, config)) == 1

    row = floor_row(ours)
    assert row["outcome"] == "error"
    assert "ruff is not on PATH" in str(row["detail"])
    # The class that carries the stop is part of the corpus's vocabulary, so it
    # is named for a reader of the journal and not for the module it lives in.
    assert not str(row["error"]).startswith("_"), row["error"]


def test_a_floor_run_is_copied_to_the_callers_directory_too(
    tmp_path: Path,
    home: Path,
    ours: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two changes meet: the floor journals, and ``--record`` copies it."""
    lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=ours)
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    theirs = tmp_path / "theirs"

    lj.main(lj.run_args(contract, repo, config, "--record", str(theirs)))

    mine = [row["attempt_id"] for row in lj.rows(ours)]
    assert len(mine) == 1, mine
    assert [row["attempt_id"] for row in lj.rows(theirs)] == mine
    assert len(lj.results(theirs)) == 1, "the copy got no result file"
