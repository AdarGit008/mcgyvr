"""``journal.dir`` holds every run; ``--record`` adds a copy, it does not move one.

The journal exists to be compounded. A question worth asking of it — how often
the floor handles a task type without the ladder, which rung earns its keep,
what a model costs per accepted change — is a question about *every* run there
has been, and it can only be asked where every run is. ``--record DIR`` made
that impossible by construction: it did not add a destination, it replaced one,
so a run made with it was recorded in a directory somebody chose for that run
and in no other. The corpus was then whatever was left over, and the answer to
any question of it was "some of the runs, and there is no way to know which".

Worse, the directory a caller passes is typically inside the repository they
are working in, and repositories are cloned, stale and thrown away. A record
kept there is a record with a half-life.

So the rule is one sentence: **mcgyvr always writes its own record under
``journal.dir``, and nothing a caller passes moves it.** ``--record DIR`` is
theirs — a complete second copy, so ``tools/live/review.py DIR`` reads it
exactly as it reads ours — and ``--result PATH`` likewise puts the file where
they asked while ours keeps its own. We keep our copy; they keep theirs.

Which settles what happens when their copy cannot be written: **not the run.**
Our sink keeps the rule it has always had — unwritable is fatal, because a run
whose record is missing is the failure this module exists to end — but their
copy is a convenience they asked for, and ending a run we recorded correctly
because their directory is full would be the product punishing them for using
a feature. It is said, once, and the result file says it too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import livejournal as lj


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


@pytest.fixture
def ours(tmp_path: Path) -> Path:
    """Where the corpus lives: the config's ``journal.dir``."""
    return tmp_path / "corpus"


def test_record_adds_a_copy_and_does_not_move_the_journal(
    tmp_path: Path,
    home: Path,
    ours: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run is in the corpus, and in the caller's directory as well."""
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=ours)
    contract = lj.make_contract(tmp_path / "impl.yaml")
    theirs = tmp_path / "theirs"

    code = lj.main(lj.run_args(contract, repo, config, "--record", str(theirs)))

    assert code == 0, code
    mine = lj.rows(ours)
    assert len(mine) == 1, mine
    assert [row["attempt_id"] for row in mine] == [
        row["attempt_id"] for row in lj.rows(theirs)
    ], "the caller's copy is not the same run"


def test_the_copy_carries_the_blobs_a_review_needs(
    tmp_path: Path,
    home: Path,
    ours: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A copy without the prompt and the reply is not a journal, it is an index.

    ``tools/live/review.py`` reads a row's ``prompt_sha256`` and
    ``reply_sha256`` out of the store beside it, so a second copy that carried
    only the lines would print "missing" for every attempt in it.
    """
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=ours)
    contract = lj.make_contract(tmp_path / "impl.yaml")
    theirs = tmp_path / "theirs"

    assert lj.main(lj.run_args(contract, repo, config, "--record", str(theirs))) == 0

    assert lj.blobs(ours), "the corpus kept no blobs"
    assert lj.blobs(ours) == lj.blobs(theirs)


def test_the_corpus_keeps_a_result_even_when_result_moves_the_printed_one(
    tmp_path: Path,
    home: Path,
    ours: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--result`` says where the caller reads it, not where the record goes."""
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=ours)
    contract = lj.make_contract(tmp_path / "impl.yaml")
    asked = tmp_path / "theirs" / "answer.json"

    code = lj.main(lj.run_args(contract, repo, config, "--result", str(asked)))

    assert code == 0, code
    assert lj.result_path(capsys.readouterr().out) == asked
    assert asked.is_file()
    kept = lj.results(ours)
    assert len(kept) == 1, kept
    assert json.loads(kept[0].read_text()) == json.loads(asked.read_text())


def test_a_copy_that_cannot_be_written_does_not_take_the_run_with_it(
    tmp_path: Path,
    home: Path,
    ours: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ours is the sink; theirs is a convenience, and a convenience is not fatal.

    A file where the directory has to go is the cheapest way to be unwritable,
    and it is the shape an operator actually produces.
    """
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=ours)
    contract = lj.make_contract(tmp_path / "impl.yaml")
    theirs = tmp_path / "theirs"
    theirs.write_text("not a directory", encoding="utf-8")

    code = lj.main(lj.run_args(contract, repo, config, "--record", str(theirs)))

    assert code == 0, code
    assert len(lj.rows(ours)) == 1, "the corpus lost the run over the caller's copy"
    said = capsys.readouterr().err
    assert str(theirs) in said
    assert "copy" in said


def test_recording_into_the_corpus_itself_does_not_write_the_run_twice(
    tmp_path: Path,
    home: Path,
    ours: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--record`` at ``journal.dir`` is one journal, not one journal twice.

    A copy is written into ``<dir>/<orchestrator>.jsonl`` — the same name ours
    has — so naming our own directory appended every line to the same file
    twice. ``fold`` survives it, because a re-logged attempt id supersedes, but
    ``tools/live/index.py`` makes a table row per attempt record and would have
    counted one dispatch as two. A corpus is kept in order not to have that
    kind of quiet double-count in it.

    Spelled two ways on purpose: a relative ``--record`` and an absolute
    ``journal.dir`` are the same directory, and only a resolved comparison
    knows it.
    """
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    ours.mkdir()
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=ours)
    contract = lj.make_contract(tmp_path / "impl.yaml")
    monkeypatch.chdir(ours.parent)

    code = lj.main(lj.run_args(contract, repo, config, "--record", ours.name))

    assert code == 0, code
    assert len(lj.rows(ours)) == 1, lj.rows(ours)
    lines = (ours / "claude-s1.jsonl").read_text().splitlines()
    assert len(lines) == len(set(lines)), "a line was written twice"


def test_our_own_sink_is_still_fatal(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rule that did not change: a corpus that cannot be written stops the run.

    The asymmetry is the whole point. Silence about our own record is the
    failure :mod:`mcgyvr.telemetry` was built to end; silence about a copy the
    caller asked for is a line on stderr.
    """
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    ours = tmp_path / "corpus"
    ours.write_text("not a directory", encoding="utf-8")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=ours)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) != 0
