"""A journal lives where the config says, and never in the repo.

The owner's ruling (2026-09-03): a default ``mcgyvr run`` takes no action on
the parent repository — no commit, no receipt, only the output files the gate
accepted, left in the working tree — and the journal is a mcgyvr-development
concern that lives on the machine, not in the user's project. So ``--record``
stops being the only way to journal: every dispatching run journals under
``journal.dir`` from the config, which ``mcgyvr init`` writes and whose default
is the XDG state dir, and ``--record DIR`` remains as a per-run override for a
campaign that wants its evidence envelope instead.

The user's repository is untouched by the journal by construction: after a run
without ``--commit``, ``git status`` in the repo shows exactly the target the
gate accepted and nothing else — no journal, no blobs, no result file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.telemetry import fold
from tests import livejournal as lj


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


def test_without_record_the_journal_goes_where_the_config_says(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "state" / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config))

    assert code == 0
    (row,) = fold(path=journal / "claude-s1.jsonl")
    assert row["ok"] is True
    assert (journal / "blobs" / row["prompt_sha256"]).is_file()


def test_the_default_journal_dir_is_the_xdg_state_dir_under_home(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "mcgyvr.yaml")  # no journal key at all
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config))

    assert code == 0
    sink = home / ".local" / "state" / "mcgyvr" / "journal" / "claude-s1.jsonl"
    assert sink.is_file(), sorted(str(p) for p in home.rglob("*.jsonl"))


def test_record_dir_adds_a_copy_and_leaves_the_configured_one_alone(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--record`` used to *override* this, and that is what changed.

    A journal is worth keeping because it can be compounded, and a flag that
    moved one run's record out of the corpus made every later question about
    the corpus unanswerable — not wrong, unanswerable, since nothing said which
    runs were missing. The caller's directory now gets a complete copy and the
    configured one keeps its own, which is what "we keep ours, they keep
    theirs" has to mean for ours to be worth reading.
    """
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    configured = tmp_path / "configured"
    envelope = tmp_path / "envelope"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=configured)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config, "--record", str(envelope)))

    assert code == 0
    assert (envelope / "claude-s1.jsonl").is_file()
    assert (configured / "claude-s1.jsonl").is_file()


def test_the_repo_shows_only_the_accepted_target_and_no_commit(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    before = lj.git(repo, "rev-parse", "HEAD").strip()
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=tmp_path / "j")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config))

    assert code == 0
    status = lj.git(repo, "status", "--porcelain").splitlines()
    assert status == [" M src/pkg/messy.py"], status
    assert lj.git(repo, "rev-parse", "HEAD").strip() == before
    assert "VALUE = 1" in (repo / "src" / "pkg" / "messy.py").read_text()


def test_init_writes_the_journal_dir_so_a_user_can_see_and_move_it() -> None:
    """`build` spells the default out, the way `breadth.draws` already is."""
    from mcgyvr.config import JOURNAL_DIR_DEFAULT
    from mcgyvr.detect import Detection
    from mcgyvr.initialize import build
    from mcgyvr.propose import Proposal

    data = build(Detection(), Proposal())
    assert data["journal"] == {"dir": JOURNAL_DIR_DEFAULT}
    assert JOURNAL_DIR_DEFAULT == "~/.local/state/mcgyvr/journal"


def test_a_target_the_user_has_edited_is_not_overwritten_by_the_default(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The sandbox judged HEAD's copy; an edit since then is work nobody has kept."""
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    target = repo / "src" / "pkg" / "messy.py"
    target.write_text("x = 0\nMY_UNFINISHED_EDIT = True\n", encoding="utf-8")
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=tmp_path / "j")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config))

    assert code == 1
    assert "MY_UNFINISHED_EDIT" in target.read_text(encoding="utf-8")
    assert "uncommitted changes" in capsys.readouterr().err
    (row,) = fold(path=tmp_path / "j" / "claude-s1.jsonl")
    assert row["outcome"] == "delivery_refused", row
