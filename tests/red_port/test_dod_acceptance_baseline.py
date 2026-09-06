"""The evidence a contract carries is checked against the tree before it is spent.

``Acceptance`` has two lists with opposite baseline expectations, and the schema
states both. ``acceptance`` commands "must also pass on the *unchanged* tree (the
preflight refuses a suite that is already red)". ``demonstration`` commands are
"the `failing_test_first` evidence": each "must FAIL on the unchanged tree and
pass after the change".

``Acceptance.precondition`` is the method that establishes both. It has no caller
anywhere in the product, in the tools, or in the tests. Only ``run`` is called,
and ``run``'s own docstring reasons from a baseline nobody took: "they failed at
baseline, so one still failing is ...".

Two silent failures follow. A ``bug_fix`` whose demonstration was already passing
— a wrong ``-k`` filter, a test that was never red — is judged by running it
after the change, seeing green, and reporting the bug fixed; nothing was proved
and the result file cannot say so. And a contract whose acceptance suite was
already broken charges the model for the tree's fault, which is the exact thing
the preflight exists to prevent.

**Asserted through the run, not through a new checker.** The finding is that a
method exists and has no caller; a test that required a fresh
``check_evidence_baseline`` and called it directly would be satisfied by adding
a second thing nothing calls. So the assertion is that ``mcgyvr run`` refuses,
and that it refuses **before dispatching** — the count of prompts sent is zero,
which is the "before a rung is spent" half of the requirement stated as an
observation rather than as a hope.

What must be observably true: a run refuses, before spending a rung, when the
evidence it was handed cannot signal — a demonstration that does not fail on the
unchanged tree, or an acceptance command that does not pass on it. The two
refusals must be told apart, because the operator's next move differs completely:
one says fix the contract, the other says fix the tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

LADDER = """
version: 1
sources:
  workstation:
    base_url: http://localhost:8080
    api: openai
    max_parallel: 1
ladder:
  tiers:
    - name: local
      source: workstation
      model: "qwen2.5-coder:7b"
"""

PASSES = "python3 -c 'import sys; sys.exit(0)'"
ALSO_PASSES = "python3 -c 'import sys; sys.exit(0)  # regression'"
FAILS = "python3 -c 'import sys; sys.exit(1)'"
ALSO_FAILS = "python3 -c 'import sys; sys.exit(1)  # regression'"

BUG_FIX = """
id: fix-fetch
task_type: bug_fix
task: fetch returns the url instead of the document; fix it.
target: src/pkg/fetch.py
interface: "def fetch(url: str) -> str"
stop_conditions:
  - The demonstrating test does not fail on the current code.
demonstration: ["{demonstration}"]
acceptance: ["{acceptance}"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/pkg/**"]
"""


def _prompts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every prompt the run dispatches, so "before a rung is spent" is checkable.

    The stub answers rather than raising: a raise would be swallowed by the
    driver and reported as an ``error`` verdict, which is indistinguishable from
    the refusal under test. Counting prompts separates the two — a refused run
    sends none, a run that reached a rung sends one.
    """
    import mcgyvr.drive as drive
    from mcgyvr.pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    sent: list[str] = []

    def fake_dispatch(source_map, rung, request, *, capacity=None):  # type: ignore[no-untyped-def]
        sent.append(request.prompt)
        return Completion(
            text="```python\ndef fetch(url: str) -> str:\n    return url\n```\n",
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="qwen2.5-coder:7b",
            source="workstation",
            protocol=Protocol.OPENAI,
            max_output_tokens=256,
            latency_s=0.01,
            input_tokens=10,
            output_tokens=10,
        )

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    return sent


def _run(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    demonstration: str,
    acceptance: str,
) -> tuple[int, list[str], str]:
    """Run the contract the way a person does, and report what came back."""
    from mcgyvr.cli import main
    from mcgyvr.config import CONFIG_PATH_ENV

    config = tmp_path / "mcgyvr.yaml"
    config.write_text(LADDER, encoding="utf-8")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(config))

    contract = tmp_path / "contract.yaml"
    contract.write_text(
        BUG_FIX.format(demonstration=demonstration, acceptance=acceptance),
        encoding="utf-8",
    )
    sent = _prompts(monkeypatch)
    import contextlib
    import io

    err = io.StringIO()
    argv = [
        "run",
        str(contract),
        "--repo",
        str(repo),
        "--sandbox",
        "tempdir",
    ]
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        try:
            code = main(argv)
        except SystemExit as exited:  # argparse refuses before the run starts
            code = int(exited.code or 0)
    assert "usage:" not in err.getvalue(), (
        f"the fixture's command line is wrong, not the product: {err.getvalue()}"
    )
    return code, sent, err.getvalue()


def test_a_demonstration_that_already_passes_refuses_before_a_rung_is_spent(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `bug_fix` that proves nothing.

    A demonstration is the one command whose *failure* is the evidence. One that
    passes on the unchanged tree cannot distinguish a fix from a no-op, and a run
    that accepts on it reports a bug fixed that was never demonstrated.
    """
    code, sent, err = _run(
        repo,
        tmp_path,
        monkeypatch,
        demonstration=PASSES,
        acceptance=ALSO_PASSES,
    )
    assert code != 0, (
        "a demonstration passing on the unchanged tree must refuse: it is the "
        "failing_test_first evidence and it did not fail"
    )
    assert not sent, (
        f"the refusal must come before a rung is spent; {len(sent)} prompt(s) "
        "were dispatched first"
    )
    assert "demonstration" in err.lower(), (
        f"the refusal must say which list is wrong: {err}"
    )


def test_an_acceptance_suite_already_red_refuses_and_says_so_differently(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The opposite direction, and the opposite next move.

    An acceptance command failing before the model touched anything charges the
    model for the tree. The operator fixes the tree; they do not rewrite the
    contract, which is what the other refusal asks for — so one message that
    named both lists would leave them unable to tell which.
    """
    code, sent, err = _run(
        repo,
        tmp_path,
        monkeypatch,
        demonstration=FAILS,
        acceptance=ALSO_FAILS,
    )
    assert code != 0, (
        "an acceptance command already failing must refuse before a rung is spent"
    )
    assert not sent, "and must refuse before dispatching"
    assert "acceptance" in err.lower() and "demonstration" not in err.lower(), (
        f"this refusal is about the acceptance suite alone: {err}"
    )


def test_evidence_that_signals_is_not_refused(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shape the schema describes must reach a rung, or the check is a wall.

    A demonstration that fails on the unchanged tree and an acceptance suite
    that passes on it is exactly the contract the documentation asks for. It is
    expected to reach a rung, which is what distinguishes a check that fits from
    one that blocks — without this, "refuse everything" satisfies the two tests
    above.
    """
    _code, sent, _err = _run(
        repo,
        tmp_path,
        monkeypatch,
        demonstration=FAILS,
        acceptance=PASSES,
    )
    assert sent, (
        "evidence in exactly the shape the schema documents was refused before "
        "a rung was reached; the baseline check must fit, not block"
    )
