"""One rung's retry note outlived the attempt that produced it.

:func:`mcgyvr.drive.worker_attempt` keeps a per-rung note so a second attempt is
told what the first got wrong — #43's rule, and the reason ``build_prompt`` has
a ``retry`` parameter at all. It wrote the note like this::

    if judgement.retry is not None:
        notes[this.rung.name] = judgement.retry

which stores a note and never clears one. Two attempts produce none. The
``ReplyError`` branch returns before that line is reached at all — deliberately,
because "the note vocabulary is the gate's findings, and nothing was gated" —
and a ``reviewer_failed`` judgement carries ``retry=None`` because the gate
passed and the verifier produced no verdict to quote. Either way the previous
attempt's note stays in the dictionary, so the attempt after it is prompted with
findings from two attempts ago, which the worker has already been asked to fix
once and may well have fixed.

**Why that is worse than sending nothing.** The retry prompt does not say "here
is some old context". ``render_user_message`` renders it under PREVIOUS ATTEMPT
WAS REJECTED, followed by "fix these and nothing else — every other check
passed". Every clause of that is false about a stale note: the previous attempt
was not rejected by those findings, they are not what to fix, and the claim that
everything else passed is a claim about a gate run that never happened. A worker
told to fix a line it already fixed is a worker being pushed away from a correct
answer, and the third attempt is exactly where the budget is thinnest.

**The sibling settles which spelling is right.** ``tools/missions/attempt.py`` is
the standalone form of this loop and assigns unconditionally into a
``dict[str, RetryNotes | None]``, so an attempt with nothing to say says nothing.
Two spellings of one loop that disagree is how this project got two deliveries
(pattern B) and two answers to "which rung is this", so the question is not
which reading is more convenient but which one is true — and it is the sibling's:
a note is *this* attempt's account of *this* attempt, and an attempt that
produced no account has none to hand on.

The rejected alternative is to keep the guard and make the parse failure produce
a note of its own — which the sibling does, in ``_unparsed``. That would fix this
file's first case and not its second: ``reviewer_failed`` reaches the guard with
``retry=None`` on purpose, and no note invented there would be about the gate.
The guard is what is wrong, not the branch that trips over it.

Nothing here is stubbed but the model. The gate runs for real over a real
sandbox, the notes are the ones :func:`~mcgyvr.escalate.judge` builds, and what
is asserted is the text of the prompt that would have been sent — because the
defect is not a dictionary entry, it is what a worker was told.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.drive import worker_attempt
from mcgyvr.pool import Rung, source_map
from mcgyvr.route import Try, Verdict
from mcgyvr.sandbox.tempdir import TempDirSandbox

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

#: The banner `render_user_message` puts a retry note under. Asserting on it
#: rather than on `notes` keeps this about what the worker reads: a dictionary
#: entry nobody rendered would be a bookkeeping detail, and this is not one.
BANNER = "PREVIOUS ATTEMPT WAS REJECTED"

LADDER = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: openai
    max_parallel: 2
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
verifier:
  enabled: true
  source: workstation
  model: qwen2.5-coder:14b
"""

CONTRACT = """
id: impl
task_type: function_implementation
task: Set VALUE to 1.
target: src/pkg/messy.py
stop_conditions: ["The value is not stated."]
acceptance: ["sh -c 'grep -q VALUE src/pkg/messy.py'"]
scope:
  allow: ["src/**"]
"""

#: Fails the contract's acceptance command, so the gate rejects and `judge`
#: builds a note. This is the note that must not outlive its attempt.
REJECTED = "```python\nOTHER = 1\n```"

#: No fenced block, so `parse_reply` refuses and `worker_attempt` returns on the
#: `ReplyError` branch without reaching the note assignment at all.
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
    from mcgyvr.pool import Protocol
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


def test_an_unreadable_reply_does_not_leave_the_last_notes_standing(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Attempt 3 must not be handed attempt 1's findings.

    Attempt 1 is rejected by the gate and produces a note. Attempt 2's reply
    cannot be read, so nothing is gated and there is nothing to say. Attempt 3
    is therefore a first attempt as far as evidence goes, and telling it "the
    previous attempt was rejected, fix these and nothing else" is three false
    statements about a gate run that did not happen.

    Attempt 2 carrying the note is asserted too, and it is the half that keeps
    this honest: the note is not being deleted, it is being scoped to the
    attempt that earned it.
    """
    sent = _driven(monkeypatch, REJECTED, UNREADABLE, ACCEPTED)

    first, second, third = _attempts(repo, 3)

    assert first.verdict is Verdict.FAILED
    assert first.retry is not None, "the premise did not hold: the gate accepted"
    assert second.verdict is Verdict.FAILED
    assert second.retry is None, (
        "the premise did not hold: the unreadable reply produced a note, so this "
        "asserts nothing about an attempt that produced none"
    )

    assert BANNER not in sent[0], "a first attempt carries no note"
    assert BANNER in sent[1], (
        "the note did not reach the attempt that follows the one that earned "
        "it; scoping a note is not deleting it"
    )
    assert BANNER not in sent[2], (
        f"attempt 3 was prompted with attempt 1's gate findings. The worker has "
        f"already been asked to fix them once, and the note is rendered as "
        f"{BANNER!r} — a claim about an attempt that was never gated.\n"
        f"prompt: {sent[2]}"
    )
    assert third.verdict is Verdict.PASSED


def test_a_verifier_with_no_verdict_does_not_leave_the_last_notes_standing(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second producer of ``retry=None``, and the one the guard itself lets past.

    ``judge`` returns ``reviewer_failed`` with no note when the gate *passed*
    and the verifier came back unusable: there is nothing of the gate's to
    repeat, and the reviewer's non-answer is not something to ask a worker to
    fix. This one reaches ``if judgement.retry is not None`` and is waved
    through by it, which is why fixing only the ``ReplyError`` branch — giving
    it a note of its own, as the sibling's ``_unparsed`` does — would leave the
    defect standing here.

    It is also the worse case of the two. The gate accepted attempt 2's change;
    attempt 3 is then told that the previous attempt was rejected over findings
    the gate has since stopped reporting.
    """

    def unusable(prompt: str) -> str:
        """A reply that names no outcome, which `verify` reads as no verdict.

        The reviewer seam rather than a finished ``Review``: ``worker_attempt``
        takes an ``Ask`` now, so what is stubbed here is the one thing a test
        cannot have — the model — and everything between it and the judgement
        is the code under test.
        """
        return "The change looks broadly reasonable to me."

    sent = _driven(monkeypatch, REJECTED, ACCEPTED, ACCEPTED)

    first, second, _third = _attempts(repo, 3, reviewer=unusable)

    assert first.retry is not None, "the premise did not hold: the gate accepted"
    assert second.reviewer_failed, (
        f"the premise did not hold: attempt 2 did not reach the verifier "
        f"({second.detail})"
    )
    assert second.retry is None

    assert BANNER in sent[1]
    assert BANNER not in sent[2], (
        f"attempt 3 was told the previous attempt was rejected, over findings "
        f"from a gate run two attempts ago that the gate no longer reports.\n"
        f"prompt: {sent[2]}"
    )


def test_a_note_still_replaces_the_one_before_it(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: consecutive rejections still each hand on their own note.

    A fix that cleared the note on every attempt satisfies both tests above and
    removes the feature. What must hold is narrower: the note handed to an
    attempt is the previous attempt's, whatever that turns out to be.
    """
    sent = _driven(monkeypatch, REJECTED, REJECTED, ACCEPTED)

    first, second, third = _attempts(repo, 3)

    assert first.retry is not None
    assert second.retry is not None
    assert BANNER not in sent[0]
    assert BANNER in sent[1]
    assert BANNER in sent[2], (
        "a rejected attempt stopped telling the next one what failed, which is "
        "the whole of what the note is for (#43)"
    )
    assert third.verdict is Verdict.PASSED


def test_the_two_spellings_of_one_loop_agree() -> None:
    """The sibling assigns unconditionally, and this is the claim that they match.

    ``tools/missions/attempt.py`` is the standalone form of the same loop for a
    caller that is not climbing, and its ``_retry`` is a
    ``dict[str, RetryNotes | None]`` written on every attempt. Asserted by
    reading the annotation rather than by driving the mission runner, because
    what is being held is that the two agree about *how a note is scoped* — a
    behavioural test of the sibling would be a test of the sibling, and it has
    its own.
    """
    import ast
    import inspect

    import mcgyvr.drive as drive

    tree = ast.parse(inspect.getsource(drive.worker_attempt))
    stores = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "notes"
        and isinstance(node.ctx, ast.Store)
    ]
    assert len(stores) == 1, (
        f"`notes` is written at {len(stores)} places. One assignment, on every "
        f"path, is what makes a note this attempt's account of this attempt."
    )
    guarded = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and any(
            isinstance(inner, ast.Subscript)
            and isinstance(inner.value, ast.Name)
            and inner.value.id == "notes"
            and isinstance(inner.ctx, ast.Store)
            for inner in ast.walk(node)
        )
    ]
    assert not guarded, (
        "the write to `notes` is inside an `if`. A conditional store cannot "
        "clear a note, which is the defect: an attempt with nothing to say "
        "leaves the last attempt's findings in place for the next one."
    )
