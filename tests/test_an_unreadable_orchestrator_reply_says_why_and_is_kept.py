"""An unreadable orchestrator reply says why, and the reply itself is kept.

A reply that finished on its own but does not parse used to be reported only by
its first 120 characters, with no decoder message and no position, and the reply
itself was dropped, so a failed run could not be diagnosed. The error now names
the decoder's message, the line and column, an excerpt either side of the point
it failed and the reply's length, and `mcgyvr delegate` prints the whole reply,
delimited, on stderr after the error.

A complete JSON value with prose only before or after it is read, and the prose
ignored. Malformed JSON inside the value is not repaired: a trailing comma
still fails, now with the reason. A reply cut off at its cap is still named as
cut off (#776), even when its text would read.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import mcgyvr.delegate as delegate
from mcgyvr.config import parse
from mcgyvr.delegate import (
    OrchestratorReplyCutOffError,
    UnreadableProposalError,
    proposals_from_reply,
    proposer_for,
)
from mcgyvr.local_pool import Protocol, source_map
from mcgyvr.orchestrator.decompose import Evidence
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import explore
from mcgyvr.orchestrator.resolve import resolve
from mcgyvr.runner import Completion, StopReason

CONFIG = """\
units:
  planner:
    address: http://localhost:11434
    model: planner-model
    rig: workstation
    width: 1
ladder:
- planner
orchestrator:
  unit: planner
  model: planner-model
"""

#: A complete, well-formed proposal array, pretty-printed as a model writes it.
ARRAY = json.dumps(
    [
        {
            "task_type": "code",
            "task": "Fix normalize_sku to raise InvalidSku as documented.",
            "target": "listing.py",
            "stop_conditions": ["the documented behaviour is ambiguous"],
        }
    ],
    indent=2,
)

#: The same array with a trailing comma after its last field: not JSON.
TRAILING_COMMA = ARRAY.replace(
    '"the documented behaviour is ambiguous"\n    ]',
    '"the documented behaviour is ambiguous"\n    ],',
)


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "listing.py").write_text("def listing(items):\n    return items\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return root


@pytest.fixture
def evidence(root: Path) -> Evidence:
    index: Index = build_index(root)
    resolution = resolve(index, "document listing")
    return Evidence(
        prompt="document listing",
        index=index,
        resolution=resolution,
        exploration=explore(index, resolution),
        vocabulary=(),
    )


def _answer(text: str, stop: StopReason = StopReason.COMPLETE) -> Completion:
    return Completion(
        text=text,
        stop_reason=stop,
        raw_stop_reason="stop" if stop is StopReason.COMPLETE else "length",
        model="planner-model",
        source="planner",
        protocol=Protocol.OPENAI,
        max_output_tokens=2000,
        latency_s=0.0,
        output_tokens=2000 if stop is StopReason.TRUNCATED else 120,
    )


def _patch(monkeypatch: pytest.MonkeyPatch, answer: Completion) -> None:
    def fake_dispatch_role(source_map, role, request, *, capacity=None):  # type: ignore[no-untyped-def]
        return answer

    monkeypatch.setattr(delegate, "dispatch_role", fake_dispatch_role)


def test_trailing_prose_after_a_complete_array_is_read() -> None:
    reply = ARRAY + "\n\nThis fixes the documented contract; the rename follows."

    (proposal,) = proposals_from_reply(reply)

    assert proposal.target == "listing.py"
    assert proposal.task.startswith("Fix normalize_sku")


def test_leading_prose_before_the_array_is_read() -> None:
    reply = "Here are the proposals for the request:\n\n" + ARRAY

    (proposal,) = proposals_from_reply(reply)

    assert proposal.target == "listing.py"


def test_leading_prose_before_a_single_object_is_read_as_one_proposal() -> None:
    entry = json.dumps({"task_type": "code", "task": "t", "target": "listing.py"})

    (proposal,) = proposals_from_reply("One proposal: " + entry + " - done.")

    assert proposal.task == "t"


def test_a_trailing_comma_inside_still_fails_with_the_reason_and_where() -> None:
    reply = TRAILING_COMMA + "\n"
    comma = TRAILING_COMMA.index("],") + 1
    line = TRAILING_COMMA.count("\n", 0, comma) + 1

    with pytest.raises(UnreadableProposalError) as raised:
        proposals_from_reply(reply)

    said = str(raised.value)
    assert "not JSON" in said
    # The decoder's own message, and where it stopped.
    assert "Expecting property name enclosed in double quotes" in said
    assert f"line {line + 1} column" in said
    # The reply's length, and an excerpt either side of the failure, repr'd.
    assert f"{len(reply)} chars" in said
    assert repr(TRAILING_COMMA[comma - 20 : comma]).strip("'") in said
    assert '"the documented behaviour is ambiguous"' in said
    # Nothing was repaired: the raw reply is carried for the caller to keep.
    assert raised.value.reply == reply


def test_prose_with_no_json_value_at_all_still_fails_with_the_reason() -> None:
    with pytest.raises(UnreadableProposalError) as raised:
        proposals_from_reply("sure, here is a proposal: listing.py")

    said = str(raised.value)
    assert "not JSON" in said
    assert "Expecting value" in said
    assert "line 1 column 1" in said


def test_the_cli_prints_the_raw_reply_on_an_unreadable_reply(
    tmp_path: Path,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.cli import main

    config = tmp_path / "mcgyvr.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    reply = "Plan first.\n" + TRAILING_COMMA + "\nThat is all."
    _patch(monkeypatch, _answer(reply))

    code = main(
        ["delegate", "document listing", "--repo", str(root), "--config", str(config)]
    )

    assert code == 1
    err = capsys.readouterr().err
    assert "error: the orchestrator's reply" in err
    assert "not JSON" in err
    opening = "--- the orchestrator's raw reply"
    closing = "--- end of the orchestrator's raw reply ---"
    assert opening in err and closing in err
    # The block comes after the error and holds the reply verbatim, whole.
    assert err.index("error:") < err.index(opening)
    kept = err[err.index("\n", err.index(opening)) + 1 : err.index(closing)]
    assert kept == reply + "\n"


def test_a_cut_off_reply_still_gets_the_cut_off_error_even_when_its_text_would_read(
    monkeypatch: pytest.MonkeyPatch, evidence: Evidence
) -> None:
    # A whole array then prose stopped mid-sentence at the cap: the text alone
    # would now be read, but the stop reason says the reply never finished.
    text = ARRAY + "\n\nNote that the rename of fam to sku_famil"
    _patch(monkeypatch, _answer(text, StopReason.TRUNCATED))
    propose = proposer_for(source_map(parse(CONFIG)))
    assert propose is not None

    with pytest.raises(OrchestratorReplyCutOffError) as raised:
        propose(evidence)

    said = str(raised.value)
    assert "cut off" in said
    assert "not JSON" not in said
    assert raised.value.reply == text
