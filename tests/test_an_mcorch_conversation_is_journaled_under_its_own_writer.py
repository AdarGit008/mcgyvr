"""An mcorch conversation is journaled under its own writer, and runs trace to it.

Every journal row names the orchestrator that produced it, and a name a reader
can follow is one that leads to a transcript (:mod:`mcgyvr.session`). An
mcorch server is a writer like Claude Code or Pi: its id is ``mcorch-<stamp>``,
minted once when it starts, and its transcript is one JSON row per request
under ``<journal.dir>/mcorch/<id>.jsonl`` — what it was asked, what Jev
answered, what it dropped from the harness's prompt, what it handed back. The
rung passes that id as ``--orchestrator`` on every ``mcgyvr run`` it has the
harness make, and ``mcgyvr run`` attaches the transcript once it knows the
journal directory, so the run's result and rows carry the transcript's path
the way a ``claude-`` or ``pi-`` row carries its session's. The transcript is
looked up under the config's own ``journal.dir``, never a default: a writer
whose transcript is not there yet is still a name, not a refusal.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mcgyvr import session
from mcgyvr.mcorch import loop, transcript
from tests import livejournal as lj

WRITER = "mcorch-20261003T123015.123456Z"


def test_a_writer_id_is_minted_from_the_start_stamp() -> None:
    when = datetime(2026, 10, 3, 12, 30, 15, 123456, tzinfo=UTC)
    writer = transcript.writer_id(when)
    assert writer == WRITER
    assert session.resolve(writer).orchestrator == writer


def test_each_request_is_one_row_under_the_journals_mcorch_folder(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "journal"
    log = transcript.Transcript.open(journal, WRITER)
    assert log.path == journal / "mcorch" / f"{WRITER}.jsonl"
    trace = loop.Trace(
        kind="main",
        intent="work",
        jev=(("intent", "work"),),
        dropped_tools=("WebSearch",),
        dropped_system_bytes=19_000,
        dropped_blocks=("image",),
        rounds=1,
        internal_calls=(),
        next=None,
    )
    log.record(trace, model="claude-sonnet-x", stop_reason="tool_use", elapsed_s=1.5)
    log.record(trace, model="claude-sonnet-x", stop_reason="end_turn", elapsed_s=0.5)
    rows = [json.loads(line) for line in log.path.read_text().splitlines()]
    assert len(rows) == 2
    row = rows[0]
    assert row["orchestrator"] == WRITER
    assert row["kind"] == "main"
    assert row["intent"] == "work"
    assert row["jev"] == [["intent", "work"]]
    assert row["dropped_tools"] == ["WebSearch"]
    assert row["dropped_system_bytes"] == 19_000
    assert row["dropped_blocks"] == ["image"]
    assert row["model"] == "claude-sonnet-x"
    assert row["stop_reason"] == "tool_use"
    assert row["elapsed_s"] == 1.5
    assert "ts" in row


def test_the_transcript_is_attached_under_the_journal_dir_once_it_is_known(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "journal"
    log = transcript.Transcript.open(journal, WRITER)
    log.path.parent.mkdir(parents=True)
    log.path.write_text("{}\n", encoding="utf-8")
    named = session.with_mcorch_transcript(session.Session(WRITER), journal)
    assert named.orchestrator == WRITER
    assert named.session_file == log.path.resolve()
    # Not yet written: still a name, never a refusal; another writer: untouched.
    assert (
        session.with_mcorch_transcript(
            session.Session("mcorch-x"), journal
        ).session_file
        is None
    )
    claude = session.Session("claude-abc", tmp_path / "t.jsonl")
    assert session.with_mcorch_transcript(claude, journal) == claude


def test_a_run_the_rung_had_the_harness_make_carries_the_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    lj.clean_env(monkeypatch, home)
    journal = tmp_path / "journal"
    log = transcript.Transcript.open(journal, WRITER)
    log.path.parent.mkdir(parents=True)
    log.path.write_text("{}\n", encoding="utf-8")
    repo = lj.make_repo(tmp_path / "repo")
    config = lj.make_config(tmp_path / "setup", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")
    lj.scripted(monkeypatch, lj.GOOD_REPLY)

    code = lj.main(lj.run_args(contract, repo, config, "--orchestrator", WRITER))

    assert code == 0
    (result,) = lj.results(journal)
    report = json.loads(result.read_text(encoding="utf-8"))
    assert report["orchestrator"] == WRITER
    assert report["session_file"] == str(log.path.resolve())
    (row,) = lj.rows(journal)
    assert row["orchestrator"] == WRITER
    assert row["session_file"] == str(log.path.resolve())
