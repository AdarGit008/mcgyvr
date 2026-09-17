"""A draw's temperature is on its journal row.

:mod:`mcgyvr.consensus` says breadth "cannot be evaluated before the telemetry
that counts crossings exists". The row already carries the draw — the
``#<index>`` suffix on its ``attempt_id`` — and carries the temperature
the draw was dispatched at, so "given that a gate-passing candidate exists
among N, at what index does it first appear, and at what temperature" is a
question the journal can answer instead of one it invites.

The temperature is identity, known before the dispatch and the same fact on
the answering row and the failing one, so it is written with the rest of the
identity and reaches both. A row for an attempt that was never a dispatch —
the deterministic floor, a caller that named none — has no ``temperature``
key at all, under the rule that keeps an unreported token count out of the
row: absent, never zeroed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr.telemetry import observe
from tests import livejournal as lj
from tests._helpers import _rows


def test_each_draws_row_carries_the_temperature_it_was_dispatched_at(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lj.scripted(monkeypatch, lj.BAD_REPLY, lj.BAD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "setup", journal_dir=journal)
    lj.append_policy(config, "breadth:\n  draws: 2\n")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1

    greedy, sampled = _rows(journal)
    assert "#" not in greedy["attempt_id"] and sampled["attempt_id"].endswith("#1")
    assert greedy["temperature"] == 0.0, "draw 0 is greedy"
    assert sampled["temperature"] == 0.7, "draw 1 sampled at the schema's default"


def _lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_a_row_with_no_temperature_omits_the_key(tmp_path: Path) -> None:
    path = tmp_path / "j.jsonl"
    observe(lambda: "ran", path=path, attempt_id="a", orchestrator="t", rung="ruff")

    (row,) = _lines(path)
    assert "temperature" not in row, "absent, never zeroed"


def test_a_dispatch_that_raised_still_says_its_temperature(tmp_path: Path) -> None:
    path = tmp_path / "j.jsonl"

    def dies() -> str:
        raise RuntimeError("connection refused")

    with pytest.raises(RuntimeError):
        observe(
            dies,
            path=path,
            attempt_id="a#1",
            orchestrator="t",
            rung="local_qwen-7b",
            temperature=0.7,
        )

    (row,) = _lines(path)
    assert row["ok"] is False
    assert row["temperature"] == 0.7, "the failing row names the temperature too"
