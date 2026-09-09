"""An attempt that drew three unreadable replies wrote three rows and owned one.

:func:`~mcgyvr.telemetry.observe` writes one journal row per *dispatch*, keyed
by :meth:`~mcgyvr.drive.Recording.attempt_id` — ``…:1`` for the first draw and
``…:1#1``, ``…:1#2`` for the rest. How each of those rows landed is appended
afterwards by ``_report_climb``, which walks ``range(step.draws)`` and corrects
every draw of the attempt.

``draws`` reaches it from :class:`~mcgyvr.escalate.Judgement`, and on one branch
the judgement did not carry it. When every draw came back unreadable,
``best_of`` raises :class:`~mcgyvr.consensus.NoUsableDrawError` and
:func:`~mcgyvr.drive.worker_attempt` built its judgement from the exception
alone — verdict, policy, detail — leaving the dataclass defaults ``draw=0,
draws=1`` standing on an attempt that had just paid for three dispatches. Every
other branch replaces both fields from the ``Consensus``; this one described
three dispatches as one.

What that costs is the whole of the failing case in the journal. Three rows go
in, one correction comes out, and the two suffixed rows keep no outcome at all
— so a reader counting how the ladder's cheap rung fares sees one refused draw
where three were paid for, and the rows that would say so are indistinguishable
from an attempt that crashed before it could be corrected. The failure is
exactly where the measurement matters most: breadth is a lever whose only
justification is what it buys, and an all-refused attempt is the case that
argues against it.

The verdict is carried on draw 0. No draw earned it — nothing was gated, and
the refusal names every one of them — so what is wanted is the row a reader
reaches first, and the one an unconfigured single-draw install already writes
unsuffixed. Which draw it is matters less than that it is one of the draws
written: the fields have to describe the dispatches that happened.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.drive import worker_attempt
from mcgyvr.pool import Rung, source_map
from mcgyvr.route import Try, Verdict
from mcgyvr.sandbox.tempdir import TempDirSandbox
from mcgyvr.telemetry import fold
from tests import livejournal as lj

#: No fenced block and no JSON: ``parse_reply`` refuses it, so the draw reaches
#: ``best_of`` as :class:`~mcgyvr.consensus.Unusable` and is never gated.
UNREADABLE = "I am afraid I cannot help with that."

DRAWS = 3

BREADTH = f"breadth:\n  draws: {DRAWS}\n"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


def test_an_attempt_whose_draws_all_refused_says_how_many_it_drew(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The judgement describes three dispatches, because three were made.

    Asserted on the judgement rather than through the ladder because this is
    the field's only producer: ``route`` copies it, the report prints it and
    the journal corrects by it, and all three are as right as what
    ``worker_attempt`` put there.
    """
    lj.scripted(monkeypatch, *[UNREADABLE] * DRAWS)
    repo = lj.make_repo(tmp_path / "repo")
    config = parse_config(lj.LADDER + BREADTH)
    contract = load_contract(lj.MODEL_CONTRACT)
    rung = Rung(name="local_qwen-7b", model="qwen2.5-coder:7b")

    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(config, source_map(config), contract, sandbox)
        judgement = attempt(Try(rung=rung, attempt=1, of=1))

    assert judgement.verdict is Verdict.FAILED
    assert judgement.draws == DRAWS, (
        f"the attempt dispatched {DRAWS} draws and wrote a journal row for each; "
        f"a judgement saying {judgement.draws} leaves the rest unaccounted for"
    )
    assert 0 <= judgement.draw < DRAWS, judgement.draw


def test_every_row_of_an_all_refused_attempt_is_corrected(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Three unreadable replies, three rows, three outcomes.

    The run itself fails — that is the honest answer and not what is being
    fixed here. What is being fixed is the journal it leaves: under the
    defaulted ``draws`` only the unsuffixed row was corrected, so two of the
    three dispatches this rung was paid for said nothing about how they landed.
    """
    lj.scripted(monkeypatch, *[UNREADABLE] * DRAWS)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    config.write_text(config.read_text() + BREADTH, encoding="utf-8")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1

    rows = {r["attempt_id"]: r for r in fold(path=journal / "claude-s1.jsonl")}
    assert len(rows) == DRAWS, sorted(rows)
    uncorrected = sorted(key for key, row in rows.items() if "outcome" not in row)
    assert not uncorrected, (
        f"{len(uncorrected)} of {DRAWS} rows never learned how they landed: "
        f"{uncorrected}"
    )

    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    (attempt,) = result["attempts"]
    assert attempt["draws"] == DRAWS
    assert attempt["attempt_id"] in rows, attempt["attempt_id"]
