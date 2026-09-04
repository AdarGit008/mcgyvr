"""The prompt blob is a sink like the reply blob, and its failure leaves a row.

``observe`` promises exactly one record per call, and the repair that made that
true covered only half of the blob store. The reply blob was wrapped so that an
unwritable store still put the row down as a failure; the *prompt* blob is
stored by ``_identity``, before the clock starts and outside every ``try``, so
the case the repair's own comment cites — ``ENOSPC``, a ``blobs/`` replaced by
a file — still raised out of ``observe`` with no row at all.

That hole is the one finding 7 is about, one level down. The driver counts a
row per dispatch it sends to ``observe``; a dispatch that wrote none makes the
count one too many, so the attempt claims a row that does not exist, the
correction for it is an orphan :func:`~mcgyvr.telemetry.fold` drops, and the
result's ``attempt_id`` names a row no reader can open.

Both halves are asserted from one run: draw 1's prompt cannot be stored, and
the answer is two rows — draw 1's saying it did not land and naming no blob —
rather than one row and a claim of two.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.telemetry import ATTEMPT_KIND, CORRECTION_KIND, fold
from tests import livejournal as lj

TWO_DRAWS = "breadth:\n  draws: 2\n"

#: Prompt, reply, prompt — the third blob of the run is the second draw's
#: prompt, stored before that dispatch is made.
PROMPT_BLOB_OF_THE_SECOND_DRAW = 3


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


def test_the_second_draws_unstorable_prompt_is_a_row_not_a_hole(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The store dies on draw 1's prompt: two rows, and no row is invented."""
    import mcgyvr.telemetry as telemetry

    lj.scripted(monkeypatch, lj.BAD_REPLY, lj.BAD_REPLY)
    real_store = telemetry._store
    stored = 0

    def store_until_the_disk_fills(path: Path, data: bytes) -> str:
        nonlocal stored
        stored += 1
        if stored == PROMPT_BLOB_OF_THE_SECOND_DRAW:
            raise OSError(28, "No space left on device")
        return real_store(path, data)

    monkeypatch.setattr(telemetry, "_store", store_until_the_disk_fills)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    config.write_text(config.read_text() + TWO_DRAWS, encoding="utf-8")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1
    assert stored == PROMPT_BLOB_OF_THE_SECOND_DRAW, "draw 1 got as far as its prompt"

    rows = _rows(journal)
    assert len(rows) == 2, (
        "a dispatch that reached `observe` leaves a row whichever sink failed: "
        f"{[r['attempt_id'] for r in rows]}"
    )
    first, second = rows
    assert second["attempt_id"] == f"{first['attempt_id']}#1", rows
    assert second.get("ok") is False, "the row says the dispatch did not land"
    assert "prompt_sha256" not in second, "no row points at a blob that is not there"
    assert [r.get("outcome") for r in rows] == ["error", "error"]
    assert _orphans(journal) == [], (
        "a row counted where the dispatch was intended is a correction for a "
        "row nobody wrote"
    )

    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    landed = result["attempts"][-1]
    assert (landed["draw"], landed["draws"], landed["rows"]) == (1, 2, 2)
    assert landed["attempt_id"] == second["attempt_id"], (
        "the result names a row a reader can open"
    )
