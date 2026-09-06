"""One unreadable reply must not throw away the draws that were already gated.

:func:`mcgyvr.consensus.best_of` was built before anything called it, and its
sampler was typed ``Callable[[int], str]``. Wiring the first real caller —
:func:`mcgyvr.drive.worker_attempt`, which draws by dispatching to a model —
contradicted that signature immediately, because the answer a dispatch most
often produces is not a string at all. ``parse_reply`` refuses by name:
truncated at the token ceiling, prose where a fenced block was asked for, a
refusal in place of a file.

A sampler holding one of those had two moves and both were wrong.

* **Fabricate a string.** It is then written into the workspace, gated, ranked
  and reported as a candidate the gate rejected — a verdict about a draw that
  never existed, and findings from a gate run that judged the last draw's tree
  or the base.
* **Raise.** ``best_of`` deliberately does not catch what the sampler raises,
  so the whole attempt ends. That is exact at ``n = 1`` and lossy above it: draw
  0 can pass the gate, and draw 1 coming back truncated discards its verdict,
  its binding and the dispatch that paid for both.

The second shipped, because it is at least honest about what happened. This
file is the third answer: the sampler may return :class:`~mcgyvr.consensus.Unusable`,
that draw is recorded rather than gated, and only a run in which *every* draw
refused is a failed attempt — which is the single-draw behaviour unchanged.

The last test drives it through ``mcgyvr run`` with ``breadth.draws: 3``,
because the loss this fixes is not visible in a unit: it takes a configured
install, three dispatches and one truncated reply for a delivered change to
turn into a spent attempt.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from mcgyvr.consensus import NoUsableDrawError, Unusable, best_of
from mcgyvr.contract import loads
from mcgyvr.gate import Finding, GateResult
from mcgyvr.sandbox import Sandbox

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.invalid",
}

TARGET = "src/pkg/fetch.py"
BASE = "def fetch(url):\n    return url\n"

#: Passes the acceptance command below; the other draw does not.
GOOD = "RETRY = 3\n\n\ndef fetch(url):\n    return url\n"
POOR = "TIMEOUT = 5\n\n\ndef fetch(url):\n    return url\n"

CONTRACT = f"""
id: retry
task_type: function_implementation
task: Give the fetch helper a retry budget named RETRY.
target: {TARGET}
stop_conditions: ["The retry policy is not stated anywhere in the repo."]
demonstration: ["sh -c 'grep -q RETRY {TARGET}'"]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""


def _git(repo: Path, *args: str) -> None:
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
    (root / TARGET).write_text(BASE, encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _reads_the_tree(seen: list[str]):  # type: ignore[no-untyped-def]
    """A gate that judges what is on disk, and records what it was shown.

    Recording is half the assertion: an unusable draw must not reach the gate at
    all, and a gate that was never called about it is the only way to tell
    "skipped" from "gated and rejected".
    """

    def gate(sandbox: Sandbox) -> GateResult:
        content = (sandbox.workspace / TARGET).read_text(encoding="utf-8")
        seen.append(content)
        if "RETRY" in content:
            return GateResult()
        return GateResult(
            findings=(
                Finding(check="acceptance", path=TARGET, message="RETRY is not set"),
            )
        )

    return gate


def test_an_unusable_draw_does_not_discard_the_draws_already_gated(
    repo: Path,
) -> None:
    """Draw 0 passes, draw 1 comes back unreadable, draw 2 is beaten.

    The winner is draw 0 — the verdict it earned before the unreadable reply
    arrived — and the bytes that travel are its own binding. Under the raising
    sampler this attempt had no result at all.
    """
    seen: list[str] = []
    answers: list[str | Unusable] = [
        GOOD,
        Unusable("the reply could not be read: it was truncated at 1024 tokens"),
        POOR,
    ]

    picked = best_of(
        repo=repo,
        contract=loads(CONTRACT),
        sample=lambda index: answers[index],
        gate=_reads_the_tree(seen),
        n=3,
    )

    assert picked.accepted
    assert picked.winner.content == GOOD
    assert seen == [GOOD, POOR], (
        f"the gate was asked about {len(seen)} draw(s); an unusable draw has no "
        f"bytes to judge, so gating it would be a verdict about somebody else's "
        f"tree"
    )


def test_the_draw_that_produced_nothing_is_recorded_rather_than_scored(
    repo: Path,
) -> None:
    """It is in ``unusable`` and not in ``gates``, and the run still counts three.

    A synthetic rejection would have been the easy way to keep the indexes
    aligned, and it would put "the gate refused this" into the record of a gate
    run that never happened — the same fabrication the sampler is no longer
    forced into. What breadth actually bought is the measurement this lever
    exists for, so the draw that bought nothing is kept in the sampler's words.
    """
    picked = best_of(
        repo=repo,
        contract=loads(CONTRACT),
        sample=lambda index: GOOD if index == 0 else Unusable("no fenced block"),
        gate=_reads_the_tree([]),
        n=3,
    )

    assert len(picked.gates) == 1
    assert len(picked) == 3, (
        "a draw that refused was still a dispatch that was paid for"
    )
    assert picked.unusable == (
        "draw 1: no fenced block",
        "draw 2: no fenced block",
    )


def test_every_draw_refusing_is_a_failed_attempt_and_says_why(repo: Path) -> None:
    """No winner can be invented from nothing, and ``NoUsableDrawError`` is the answer.

    Distinct from a bare :class:`~mcgyvr.consensus.ConsensusError` because a
    driver can act on it — this is an attempt that failed, which the ladder
    knows what to do with — and each refusal is named, because these sentences
    are the only account of the draws that exists.
    """
    with pytest.raises(NoUsableDrawError) as raised:
        best_of(
            repo=repo,
            contract=loads(CONTRACT),
            sample=lambda index: Unusable(f"refusal {index}"),
            gate=_reads_the_tree([]),
            n=2,
        )

    assert "refusal 0" in str(raised.value)
    assert "refusal 1" in str(raised.value)


# --------------------------------------------------------------------------
# The loss, as an operator would have met it
# --------------------------------------------------------------------------

LADDER = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 2
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
breadth:
  draws: 3
"""


def _completion(text: str):  # type: ignore[no-untyped-def]
    from mcgyvr.pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    return Completion(
        text=text,
        stop_reason=StopReason.COMPLETE,
        raw_stop_reason="stop",
        model="qwen2.5-coder:7b",
        source="workstation",
        protocol=Protocol.OLLAMA,
        max_output_tokens=1024,
        latency_s=0.0,
    )


def _answers(monkeypatch: pytest.MonkeyPatch, *replies: str) -> list[str]:
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


def test_one_unreadable_reply_does_not_cost_a_breadth_attempt_its_winner(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three draws, the middle one unreadable, and the third is delivered.

    This is the run the raising sampler lost: draw 1 ended the attempt from
    underneath the other two, the rung was reported as having produced nothing,
    and the ladder escalated over a reply that was merely truncated. Asserting
    on the repository rather than on the ``Consensus``, because what was lost
    was a change, not a data structure.
    """
    from mcgyvr.cli import main

    config = tmp_path / "mcgyvr.yaml"
    config.write_text(LADDER, encoding="utf-8")
    contract = tmp_path / "retry.yaml"
    contract.write_text(CONTRACT, encoding="utf-8")

    sent = _answers(
        monkeypatch,
        f"```python\n{POOR}```\n",
        "I am afraid I cannot help with that.",
        f"```python\n{GOOD}```\n",
    )

    code = main(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(config),
            "--sandbox",
            "tempdir",
            "--commit",
        ]
    )

    assert code == 0, "the attempt was lost to one unreadable draw"
    assert len(sent) == 3, f"the rung was asked {len(sent)} time(s), not three"
    assert (repo / TARGET).read_text(encoding="utf-8") == GOOD
