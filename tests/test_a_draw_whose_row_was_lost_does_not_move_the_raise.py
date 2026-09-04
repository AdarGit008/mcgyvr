"""Which dispatch raised is the raise site's fact, not a count of rows.

:func:`~mcgyvr.telemetry.observe` stores the reply blob *after* the attempt
returns and *before* the row that names it, so a blob store that cannot be
written — ``ENOSPC``, ``EDQUOT``, a ``blobs/`` replaced by a file — raises out
of a dispatch that answered and leaves no row at all. That same raise is what
ends the attempt, so the journal shows one row for an attempt that made two
dispatches, and a repair that counted rows to find "the dispatch in flight"
counted one and put the ``error`` on draw 0: the draw that answered, which is
the very bug finding 7 was about. A torn last line, which
:func:`~mcgyvr.telemetry.fold` silently skips, shifts the count the same way.

Two things are asserted here and they are the two halves of the answer. Which
draw raised comes from the party that knows — the attempt that was dispatching
it — so no count of rows can move it. And a dispatch that was made always
leaves exactly one row, which is what ``observe`` promises: the blob is still a
sink and still raises, but the row goes down first, as the failure it is.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.telemetry import ATTEMPT_KIND, CORRECTION_KIND, fold
from tests import livejournal as lj

TWO_DRAWS = "breadth:\n  draws: 2\n"

#: Prompt blob, reply blob, prompt blob, reply blob — the fourth is the second
#: draw's answer, and it is the one made unwritable.
LAST_BLOB_OF_THE_SECOND_DRAW = 4


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


def _records(journal: Path) -> list[dict[str, Any]]:
    return [
        record for path in sorted(journal.glob("*.jsonl")) for record in fold(path=path)
    ]


def _rows(journal: Path) -> list[dict[str, Any]]:
    return sorted(
        (r for r in _records(journal) if r.get("record_kind") == ATTEMPT_KIND),
        key=lambda record: str(record["attempt_id"]),
    )


def _orphans(journal: Path) -> list[dict[str, Any]]:
    return [r for r in _records(journal) if r.get("record_kind") == CORRECTION_KIND]


def test_the_second_draws_unwritable_blob_still_names_the_second_draw(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The blob store dies on draw 1's reply: the raise is still draw 1's."""
    import mcgyvr.telemetry as telemetry

    lj.scripted(monkeypatch, lj.BAD_REPLY, lj.BAD_REPLY)
    real_store = telemetry._store
    stored = 0

    def store_until_the_disk_fills(path: Path, data: bytes) -> str:
        nonlocal stored
        stored += 1
        if stored == LAST_BLOB_OF_THE_SECOND_DRAW:
            raise OSError(28, "No space left on device")
        return real_store(path, data)

    monkeypatch.setattr(telemetry, "_store", store_until_the_disk_fills)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    config.write_text(config.read_text() + TWO_DRAWS, encoding="utf-8")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1
    assert stored == LAST_BLOB_OF_THE_SECOND_DRAW, "both draws were dispatched"

    rows = _rows(journal)
    assert len(rows) == 2, (
        "a dispatch that was made leaves a row: the second one answered and "
        f"its reply could not be stored, which is a failed row, not no row: {rows}"
    )
    first, second = rows
    assert second["attempt_id"] == f"{first['attempt_id']}#1", rows
    assert second.get("ok") is False, "the row says the dispatch did not land"
    assert "reply_sha256" not in second, "no row points at a blob that is not there"
    assert second.get("outcome") == "error", "the raise is corrected onto its own row"
    assert _orphans(journal) == []

    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    landed = result["attempts"][-1]
    assert landed["verdict"] == "error"
    assert (landed["draw"], landed["draws"]) == (1, 2)
    assert landed["attempt_id"] == second["attempt_id"], (
        "the result names the dispatch that raised and not the one that answered"
    )
