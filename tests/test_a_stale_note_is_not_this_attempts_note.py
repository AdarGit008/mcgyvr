"""A failure note names the attempt it is about, and is never presented as another's.

:func:`mcgyvr.drive.worker_attempt` keeps the climb's failure-notes records —
one per failed attempt that left one, each naming its rung and attempt — and
:func:`mcgyvr.notes.handed_on` picks what the next try is shown under
``retry_notes``. An attempt that left no record adds none. Three kinds of
attempt leave one: a gate rejection, a reviewer's refusal, and a reply that
could not be read (the parser's own sentence, kind ``unreadable``). A passed
attempt, a ``reviewer_failed`` one among them, leaves none.

**Why a misattributed note is worse than sending nothing.** The banner a record
is rendered under says what happened to *that* attempt — "ATTEMPT 1 ON r WAS
REJECTED BY THE GATE. Fix exactly these and change nothing else — every other
check passed". Told about an attempt that was not the one it names, every
clause is false: those findings are not what the gate said about it, and the
claim that everything else passed is a claim about a gate run that never
happened. So the banner names the rung and attempt, and nothing the worker
reads says "your previous attempt" about a record that may be two attempts or
a rung below it.

**The rule, restated from the per-rung note it replaced.** Before records
travelled, each rung kept one note and overwrote it on every attempt, so an
attempt with nothing to say cleared it. The record is now never cleared and
never overwritten: it is the history, and what keeps it honest is that it
says which attempt it is about. ``retry_notes: rung`` keeps the old reading —
only the attempt just before this one on this rung — and is asserted here too.

Nothing here is stubbed but the model. The gate runs for real over a real
sandbox, the records are the ones :func:`~mcgyvr.escalate.judge` and the
driver build, and what is asserted is the text of the prompt that would have
been sent — because what matters is not a list entry, it is what a worker was
told.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.drive import worker_attempt
from mcgyvr.local_pool import Rung, source_map
from mcgyvr.route import Try, Verdict
from mcgyvr.sandbox.tempdir import TempDirSandbox

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}


#: The banner of attempt ``n``'s gate rejection, as the worker reads it.
#: Asserting on the rendered text rather than on the records keeps this about
#: what the worker reads.
def rejected_banner(n: int) -> str:
    return f"ATTEMPT {n} ON local_qwen-7b WAS REJECTED BY THE GATE"


#: The banner of attempt ``n``'s unreadable reply.
def unreadable_banner(n: int) -> str:
    return f"THE REPLY TO ATTEMPT {n} ON local_qwen-7b COULD NOT BE READ"


#: The wording a record must never be rendered under: it would present any
#: record as the attempt just before this one.
PREVIOUS = "YOUR PREVIOUS ATTEMPT"

LADDER = """\
units:
  local_qwen-7b:
    address: http://localhost:11434
    model: qwen2.5-coder:7b
    rig: workstation
    width: 2
    window: 32768
ladder:
- local_qwen-7b
verifier:
  enabled: true
  model: qwen2.5-coder:14b
  unit: local_qwen-7b
"""

CONTRACT = """
id: impl
task_type: code
task: Set VALUE to 1.
target: src/pkg/messy.py
stop_conditions: ["The value is not stated."]
demonstration: ["sh -c 'grep -q VALUE src/pkg/messy.py'"]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""

#: Fails the contract's acceptance command, so the gate rejects and `judge`
#: builds a note. This is the note that must not outlive its attempt.
REJECTED = "```python\nOTHER = 1\n```"

#: No fenced block, so `parse_reply` refuses, no draw is usable, and the
#: attempt's judgement carries `retry=None`.
UNREADABLE = "I am afraid I cannot help with that."

#: Satisfies the acceptance command, so the gate accepts.
ACCEPTED = "```python\nVALUE = 1\n```"


def _git(repo: Path, *args: str) -> None:
    import os

    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={**os.environ, **_IDENTITY},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "messy.py").write_text("x = 0\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _completion(text: str):  # type: ignore[no-untyped-def]
    from mcgyvr.local_pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    return Completion(
        text=text,
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="qwen2.5-coder:7b",
        source="workstation",
        protocol=Protocol.OPENAI,
        max_output_tokens=1024,
        latency_s=0.0,
    )


def _driven(monkeypatch: pytest.MonkeyPatch, *replies: str) -> list[str]:
    """Answer each dispatch from a script, recording the prompt each one carried.

    The one substitution in the file, and the same one ``test_drive`` makes: a
    test that needed a live model would not run on a machine with no backend.
    Everything the prompt passes through on its way here is real.
    """
    import mcgyvr.drive as drive

    sent: list[str] = []
    scripted = list(replies)

    def fake_dispatch(source_map, rung, request, *, capacity=None):  # type: ignore[no-untyped-def]
        sent.append(request.prompt)
        if not scripted:
            raise AssertionError(f"an unscripted dispatch was made to {rung!r}")
        return _completion(scripted.pop(0))

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    return sent


def _attempts(repo: Path, count: int, **kwargs: object):  # type: ignore[no-untyped-def]
    """Run ``count`` attempts on one rung, the way ``climb`` would."""
    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(CONTRACT)
    rung = Rung(name="local_qwen-7b", model="m")
    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(config, pool, contract, sandbox, **kwargs)  # type: ignore[arg-type]
        return [
            attempt(Try(rung=rung, attempt=n, of=count)) for n in range(1, count + 1)
        ]


def _attempts_under(mode: str, repo: Path, count: int, **kwargs: object):  # type: ignore[no-untyped-def]
    """``_attempts`` with ``retry_notes`` set to ``mode``."""
    config = parse_config(LADDER + f"retry_notes: {mode}\n")
    pool = source_map(config)
    contract = load_contract(CONTRACT)
    rung = Rung(name="local_qwen-7b", model="m")
    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(config, pool, contract, sandbox, **kwargs)  # type: ignore[arg-type]
        return [
            attempt(Try(rung=rung, attempt=n, of=count)) for n in range(1, count + 1)
        ]


def test_an_unreadable_reply_is_its_own_record_and_not_attempt_ones(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Attempt 3 is told about attempt 2's unreadable reply, not handed attempt 1's
    findings as if they were the latest word.

    Attempt 1 is rejected by the gate. Attempt 2's reply cannot be read, so
    nothing is gated — and that is what its record says, under a banner naming
    attempt 2. Attempt 1's record is still history, and attempt 3 sees it as an
    earlier line, never under the banner that would claim it is the latest.
    """
    sent = _driven(monkeypatch, REJECTED, UNREADABLE, ACCEPTED)

    first, second, third = _attempts(repo, 3)

    assert first.verdict is Verdict.FAILED
    assert first.retry is not None, "the premise did not hold: the gate accepted"
    assert second.verdict is Verdict.FAILED
    assert second.retry is not None and second.retry.attempt == 2
    assert {note.kind.value for note in second.retry.notes} == {"unreadable"}

    assert "WAS REJECTED" not in sent[0], "a first attempt carries no record"
    assert rejected_banner(1) in sent[1]
    assert unreadable_banner(2) in sent[2], sent[2]
    assert rejected_banner(1) not in sent[2], (
        f"attempt 3 was shown attempt 1's findings under the banner of the latest "
        f"record, though attempt 2 came after it and was never gated.\n"
        f"prompt: {sent[2]}"
    )
    assert "earlier: local_qwen-7b #1 — acceptance (1)" in sent[2]
    assert all(PREVIOUS not in prompt for prompt in sent)
    assert third.verdict is Verdict.PASSED


def test_under_rung_only_the_attempt_just_before_is_handed_on(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``retry_notes: rung`` is the per-rung note as it was: one record, the last."""
    sent = _driven(monkeypatch, REJECTED, UNREADABLE, ACCEPTED)

    _attempts_under("rung", repo, 3)

    assert rejected_banner(1) in sent[1]
    assert unreadable_banner(2) in sent[2]
    assert "earlier:" not in sent[2], "rung hands on one record, not the history"


def test_a_verifier_with_no_verdict_leaves_no_record_to_misattribute(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The producer of no record: a pass the reviewer could not judge.

    ``judge`` returns ``reviewer_failed`` with no record when the gate *passed*
    and the verifier came back unusable: there is nothing of the gate's to
    repeat, and the reviewer's non-answer is not something to ask a worker to
    fix. A climb ends on that pass, so no attempt 3 follows it; driven past it
    here, attempt 3 must still never read attempt 1's findings as attempt 2's.
    Under ``rung`` it reads nothing, as the per-rung note did; under ``climb``
    it reads attempt 1's record under attempt 1's name.
    """

    def unusable(prompt: str) -> str:
        """A reply that names no outcome, which `verify` reads as no verdict.

        The reviewer seam rather than a finished ``Review``: ``worker_attempt``
        takes an ``Ask``, so what is stubbed here is the one thing a test
        cannot have — the model — and everything between it and the judgement
        is the code under test.
        """
        return "The change looks broadly reasonable to me."

    sent = _driven(monkeypatch, REJECTED, ACCEPTED, ACCEPTED)
    first, second, _third = _attempts_under("rung", repo, 3, reviewer=unusable)

    assert first.retry is not None, "the premise did not hold: the gate accepted"
    assert second.reviewer_failed, (
        f"the premise did not hold: attempt 2 did not reach the verifier "
        f"({second.detail})"
    )
    assert second.retry is None
    assert rejected_banner(1) in sent[1]
    assert "WAS REJECTED" not in sent[2], (
        f"under `rung`, attempt 3 was told about attempt 1 although attempt 2 "
        f"left no record of its own.\nprompt: {sent[2]}"
    )

    climbed = _driven(monkeypatch, REJECTED, ACCEPTED, ACCEPTED)
    _attempts_under("climb", repo, 3, reviewer=unusable)

    assert rejected_banner(1) in climbed[2]
    assert "ATTEMPT 2" not in climbed[2], (
        f"attempt 3 was told something about attempt 2, which left no record.\n"
        f"prompt: {climbed[2]}"
    )
    assert all(PREVIOUS not in prompt for prompt in climbed)


def test_a_record_still_follows_the_one_before_it(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: consecutive rejections each hand on their own record.

    A fix that handed on nothing would satisfy every test above and remove the
    feature. What must hold is narrower: the latest record shown is the latest
    attempt's, named as such, with the ones before it kept as history.
    """
    sent = _driven(monkeypatch, REJECTED, REJECTED, ACCEPTED)

    first, second, third = _attempts(repo, 3)

    assert first.retry is not None
    assert second.retry is not None
    assert "WAS REJECTED" not in sent[0]
    assert rejected_banner(1) in sent[1]
    assert rejected_banner(2) in sent[2], (
        "a rejected attempt stopped telling the next one what failed, which is "
        "the whole of what the record is for"
    )
    assert "earlier: local_qwen-7b #1 — acceptance (1)" in sent[2]
    assert third.verdict is Verdict.PASSED


def test_nothing_is_handed_on_under_none(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``retry_notes: none`` sends every attempt the contract alone."""
    sent = _driven(monkeypatch, REJECTED, REJECTED, ACCEPTED)

    _attempts_under("none", repo, 3)

    assert all("WAS REJECTED" not in prompt for prompt in sent)


def test_the_driver_keeps_a_history_and_never_a_per_rung_slot() -> None:
    """The climb is appended to, once, from the judgement's own record.

    Asserted by reading the driver rather than by driving it, because what is
    held is how a record is kept: a store into a per-rung slot can overwrite
    one attempt's record with another's, and a record appended from anywhere
    but the judgement it belongs to would be a record of nothing.
    """
    import ast
    import inspect

    import mcgyvr.drive as drive

    tree = ast.parse(inspect.getsource(drive.worker_attempt))
    stores = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store)
    ]
    assert not stores, "the driver writes into a slot; records are a history"
    appends = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "climb"
        and node.func.attr == "append"
    ]
    assert len(appends) == 1, f"the climb is appended to at {len(appends)} places"
    (record,) = appends[0].args
    assert ast.unparse(record) == "judgement.retry"
