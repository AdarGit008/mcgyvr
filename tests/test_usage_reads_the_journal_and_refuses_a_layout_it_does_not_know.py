"""``mcgyvr usage`` reads the journal back, and refuses a row it cannot read.

Every run appends rows to the journal, and until this verb nothing a user ran
read them. ``usage`` folds each journal file with :func:`mcgyvr.telemetry.fold`
and prints what the attempts added up to, per run and per rung: rows, how many
answered, tokens, time and the verdicts they folded to. Each row is stamped
with the layout version it was written under; a row of a version this build
does not write is refused, naming the file, the line and the version, rather
than read under meanings it was not written with.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pytest

from mcgyvr.cli import main
from mcgyvr.drive.record import run_of
from mcgyvr.ladder_map import Protocol
from mcgyvr.runner import Completion, StopReason
from mcgyvr.telemetry import (
    TELEMETRY_VERSION,
    JournalVersionError,
    correct,
    fold,
    observe,
)
from tests._helpers import write_setup

#: One run's stamp, spelled as ``run_stamp`` spells one.
RUN = "20261110T120000.000001Z"

#: What ``usage`` says of a journal that holds no attempt yet.
EMPTY = "no attempt rows yet. Every run writes its rows here."


def _completion(input_tokens: int, output_tokens: int) -> Completion:
    return Completion(
        text="x = 1\n",
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="qwen2.5-coder:7b",
        source="workstation",
        protocol=Protocol.OPENAI,
        max_output_tokens=4096,
        latency_s=1.5,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _journal(journal: Path, session: str = "sess-a", rung: str = "flash") -> Path:
    """A journal one session wrote: three attempts over two rungs, corrected.

    The first two land on ``flash`` and report tokens; the third raises on
    ``pro``. Each is corrected with a verdict, and one correction names an
    attempt no row holds.
    """
    sink = journal / f"{session}.jsonl"

    def attempt(rung: str, n: int, answer: object) -> str:
        attempt_id = f"{session}:{RUN}:c1:{rung}:{n}"

        def call() -> object:
            if isinstance(answer, BaseException):
                raise answer
            return answer

        with contextlib.suppress(RuntimeError):
            observe(
                call,
                path=sink,
                attempt_id=attempt_id,
                orchestrator=session,
                rung=rung,
            )
        return attempt_id

    first = attempt(rung, 1, _completion(100, 20))
    second = attempt(rung, 2, _completion(50, 5))
    third = attempt("pro", 1, RuntimeError("the unit went away"))
    correct(path=sink, attempt_id=first, outcome="failed", orchestrator=session)
    correct(path=sink, attempt_id=second, outcome="passed", orchestrator=session)
    correct(path=sink, attempt_id=third, outcome="error", orchestrator=session)
    correct(path=sink, attempt_id="ghost", outcome="passed", orchestrator=session)
    return sink


def _line(out: str, key: str) -> list[str]:
    """The columns of the one table line whose first column is ``key``."""
    (found,) = [line.split() for line in out.splitlines() if line.split()[:1] == [key]]
    return found


def test_the_fold_is_printed_per_run_and_per_rung(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = tmp_path / "journal"
    _journal(journal)

    assert main(["usage", str(journal)]) == 0
    out = capsys.readouterr().out

    assert out.splitlines()[0].endswith("3 attempt row(s) in 1 file(s)"), out
    # rows, ok, failed, input tokens, output tokens, time, then the verdicts.
    run = _line(out, RUN)
    assert run[1] == "sess-a", run
    assert run[2:7] == ["3", "2", "1", "150", "25"], run
    assert "error 1" in " ".join(run) and "passed 1" in " ".join(run), run
    flash = _line(out, "flash")
    assert flash[1:6] == ["2", "2", "0", "150", "25"], flash
    assert " ".join(flash).endswith("failed 1, passed 1"), flash
    pro = _line(out, "pro")
    # The raised attempt reported no tokens: unmeasured, not zero.
    assert pro[1:6] == ["1", "0", "1", "-", "-"], pro
    assert " ".join(pro).endswith("error 1"), pro
    assert "1 correction(s) name an attempt no row holds" in out, out


def test_the_journal_the_setup_names_is_the_one_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = tmp_path / "state" / "journal"
    _journal(journal)
    folder = write_setup(
        tmp_path / "setup",
        f"units:\n  flash:\n    address: http://localhost:11434\n"
        f"    model: qwen2.5-coder:3b\n    rig: workstation\n"
        f"ladder:\n- flash\njournal:\n  dir: {journal}\n",
    )

    assert main(["usage", "--config", str(folder)]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"{journal}: 3 attempt row(s)"), out


@pytest.mark.parametrize("version", [TELEMETRY_VERSION + 1, None, True, "1"], ids=str)
def test_a_row_of_a_layout_it_does_not_know_is_refused_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], version: object
) -> None:
    journal = tmp_path / "journal"
    sink = _journal(journal)
    row: dict[str, object] = {"record_kind": "attempt", "attempt_id": "later"}
    if version is not None:
        row["version"] = version
    with sink.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    line = len(sink.read_text(encoding="utf-8").splitlines())

    with pytest.raises(JournalVersionError) as raised:
        fold(path=sink)
    assert (raised.value.path, raised.value.line) == (sink, line)
    assert raised.value.version == version

    assert main(["usage", str(journal)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "", captured.out
    assert f"{sink}:{line}:" in captured.err, captured.err
    assert f"reads layout version {TELEMETRY_VERSION} only" in captured.err
    stated = (
        "carries no layout version"
        if version is None
        else f"layout version {json.dumps(version)},"
    )
    assert stated in captured.err, captured.err


def test_an_empty_journal_says_so_and_is_not_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = tmp_path / "journal"
    journal.mkdir()

    assert main(["usage", str(journal)]) == 0
    assert capsys.readouterr().out == f"{journal}: {EMPTY}\n"


def test_with_no_setup_the_default_journal_is_read(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The test's own HOME (conftest) holds no setup and no journal yet.
    assert main(["usage"]) == 0
    out = capsys.readouterr().out
    assert out.endswith(f"/.local/state/mcgyvr/journal: {EMPTY}\n"), out


def test_a_journal_named_and_missing_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["usage", str(tmp_path / "nowhere")]) == 1
    assert "no journal at" in capsys.readouterr().err


def test_the_tally_columns_line_up_under_long_session_and_rung_names(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A real session id is `claude-<uuid>`, 43 characters; a rung may be long too.
    session = "claude-0b6c2f4e-1d3a-4c5b-9e8f-7a6b5c4d3e2f"
    rung = "a-rung-whose-name-is-longer-than-any-fixed-width-column"
    journal = tmp_path / "journal"
    _journal(journal, session=session, rung=rung)

    assert main(["usage", str(journal)]) == 0
    out = capsys.readouterr().out

    for heading in ("Per run, oldest first:", "Per rung:"):
        lines = out.split(heading + "\n", 1)[1].split("\n\n", 1)[0].splitlines()
        header, *table = lines
        assert table, out
        for column in ("rows", "time", "outcomes"):
            end = header.index(column) + len(column)
            for line in table:
                # Right-aligned numbers end where their heading ends, and the
                # verdicts start where `outcomes` starts.
                if column == "outcomes":
                    start = header.index(column)
                    assert line[start - 1] == " " and line[start] != " ", (column, out)
                else:
                    assert line[end - 1] != " " and line[end : end + 1] == " ", (
                        column,
                        out,
                    )


@pytest.mark.parametrize(
    ("attempt_id", "session", "run"),
    [
        (f"sess-a:{RUN}:c1:flash:1", "sess-a", RUN),
        (f"sess-a:{RUN}:c1:flash:1#2", "sess-a", RUN),
        # Written with no run stamp: the contract follows the session.
        ("sess-a:c1:flash:1", "sess-a", ""),
        # A segment `strptime` would take but `run_stamp` never writes.
        ("sess-a:2026111T120000.1Z:c1:flash:1", "sess-a", ""),
        # An id that does not start with the row's session.
        (f"other:{RUN}:c1:flash:1", "sess-a", ""),
        (f"sess-ab:{RUN}:c1:flash:1", "sess-a", ""),
        ("", "sess-a", ""),
    ],
)
def test_the_run_stamp_is_read_back_only_when_it_is_one(
    attempt_id: str, session: str, run: str
) -> None:
    assert run_of(attempt_id, session) == run


def test_an_attempt_with_no_run_stamp_is_tallied_under_no_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sink = tmp_path / "sess-a.jsonl"
    observe(
        lambda: None,
        path=sink,
        attempt_id="sess-a:c1:flash:1",
        orchestrator="sess-a",
        rung="flash",
    )

    assert main(["usage", str(sink)]) == 0
    assert _line(capsys.readouterr().out, "-")[1:3] == ["sess-a", "1"]
