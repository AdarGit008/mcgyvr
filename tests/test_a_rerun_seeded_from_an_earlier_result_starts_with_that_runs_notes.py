"""A rerun seeded from an earlier result starts with that run's notes.

`retry_notes: climb` carries a climb's failure notes from rung to rung inside
one run, and nothing carried them out of it: a second run of the same contract
— on another ladder, another machine — started blind. `mcgyvr run
--notes-from RESULT` reads the earlier run's result file and primes the climb
with its records, so the first attempt of the new run is shown what the old
one was refused for, under a banner naming the earlier run. The new result
says it was seeded, and from what.

Everything is real but the model: `mcgyvr.cli.main`, the config, the sandbox,
the prompt and the gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import livejournal as lj

STAMP_LINE = "IN AN EARLIER RUN ("
NOTE_LINE = "acceptance"


@pytest.fixture
def setup(tmp_path: Path, home: Path) -> dict[str, Path]:
    journal = tmp_path / "journal"
    return {
        "repo": lj.make_repo(tmp_path / "repo"),
        "config": lj.make_config(tmp_path / "setup", journal_dir=journal),
        "contract": lj.make_contract(tmp_path / "impl.yaml"),
        "journal": journal,
        "tmp": tmp_path,
    }


def _earlier(
    setup: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    """A first run whose every attempt is rejected; its result file."""
    lj.scripted(monkeypatch, *([lj.BAD_REPLY] * 8))
    lj.main(lj.run_args(setup["contract"], setup["repo"], setup["config"]))
    path = lj.result_path(capsys.readouterr().out)
    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["outcome"] != "accepted"
    assert any(a["notes"] for a in result["attempts"])
    return path


def test_the_first_attempt_of_a_seeded_rerun_is_shown_the_earlier_runs_notes(
    setup: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    earlier = _earlier(setup, monkeypatch, capsys)
    run = json.loads(earlier.read_text(encoding="utf-8"))["run"]

    sent = lj.scripted(monkeypatch, lj.GOOD_REPLY)
    code = lj.main(
        lj.run_args(
            setup["contract"],
            setup["repo"],
            setup["config"],
            "--notes-from",
            str(earlier),
        )
    )

    assert code == 0
    assert f"{STAMP_LINE}{run}), NOT THIS ONE: ATTEMPT" in sent[0]
    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    seeded = result["seeded"]
    assert seeded["from"] == str(earlier)
    assert seeded["handed"] == len(seeded["records"]) > 0
    assert {entry["run"] for entry in seeded["records"]} == {run}
    assert seeded["records"][-1]["notes"]["schema"] == "mcgyvr.failure_notes/1"
    # The rerun's own attempts are its own: none is presented as seeded.
    assert [a["rung"] for a in result["attempts"]] == ["local_qwen-7b"]


def test_a_rerun_under_retry_notes_none_reads_the_seed_and_hands_none_of_it(
    setup: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    earlier = _earlier(setup, monkeypatch, capsys)
    lj.append_policy(setup["config"], "retry_notes: none\n")

    sent = lj.scripted(monkeypatch, lj.GOOD_REPLY)
    lj.main(
        lj.run_args(
            setup["contract"],
            setup["repo"],
            setup["config"],
            "--notes-from",
            str(earlier),
        )
    )

    assert STAMP_LINE not in sent[0]
    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    assert result["seeded"]["handed"] == 0
    assert result["seeded"]["records"]


def test_an_unseeded_result_says_nothing_of_a_seed(
    setup: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    lj.main(lj.run_args(setup["contract"], setup["repo"], setup["config"]))

    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    assert "seeded" not in result


@pytest.mark.parametrize(
    ("content", "said"),
    [
        (None, "cannot be read"),
        ("{not json", "not JSON"),
        (json.dumps({"contract": "other", "run": "R", "attempts": []}), "'other'"),
    ],
)
def test_a_seed_that_cannot_be_used_stops_the_run_before_it_spends_anything(
    setup: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    content: str | None,
    said: str,
) -> None:
    seed = setup["tmp"] / "seed.json"
    if content is not None:
        seed.write_text(content, encoding="utf-8")
    sent = lj.scripted(monkeypatch)

    code = lj.main(
        lj.run_args(
            setup["contract"],
            setup["repo"],
            setup["config"],
            "--notes-from",
            str(seed),
        )
    )

    assert code == 1
    assert sent == []
    err = capsys.readouterr().err
    assert f"error: --notes-from {seed}:" in err
    assert said in err
