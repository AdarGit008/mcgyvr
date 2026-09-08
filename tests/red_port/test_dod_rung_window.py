"""The window a rung serves is readable below the seam, and the fit check uses it.

Every token budget in mcgyvr is spent against a number the *contract* declared.
``context.max_input_tokens`` defaults to 4096 and is the only ceiling the live
path enforces (``mcgyvr.worker.prompt.build_prompt``), so a contract is measured
against the window it was written for and never against the window it reaches.

Two failures follow, and they are opposite. A contract declaring a ceiling
larger than the rung it lands on passes the check and is truncated by the engine
at a boundary nobody chose. A contract declaring a smaller one is refused on a
rung that had room. Which of the two happens is decided by a number the operator
typed into a file about the work, not by the machine that will answer.

**Where the window lives is the seam question, and an earlier draft got it
wrong.** It asserted ``Rung.context_window`` on a bare ``Rung(name=..., model=...)``.
That cannot go green. ``tests/test_pool.py::test_a_rung_cannot_say_where_its_work_runs``
pins ``dataclasses.fields(Rung) == {"name", "model"}``, and ``pool.py:164``
argues that emptiness *is* the seam — "a caller holding a ``Rung`` cannot come to
depend on where its work runs". A window is a fact about the machine, so putting
it on ``Rung`` breaks the seam; and a bare ``Rung`` with no source could only
answer from a baked-in default, which ``test_dod_one_context_number.py`` exists
to forbid.

So the requirement is stated where the machine is already known: **below the
seam, on what the pool resolves a rung to.** Above it, a rung is still a name and
a model. What must be true is that the dispatch path can ask, and that the answer
comes from the source rather than from a constant — two rungs on differently
configured sources must report different numbers.

The share added on 2026-09-06 (``limits.max_window_fraction``) is a share OF this
number, so it cannot be enforced until this exists.
"""

from __future__ import annotations

from typing import Any

from tests.red_port.conftest import required

#: Two sources declaring different windows, so a constant cannot satisfy both.
LADDER = """
version: 1
sources:
  narrow:
    base_url: "http://rig:8080"
    api: openai
    max_parallel: 1
    context_window: 4096
  wide:
    base_url: "http://rig:8081"
    api: openai
    max_parallel: 1
    context_window: 32768
ladder:
  tiers:
    - name: small
      source: narrow
      model: "a-model"
    - name: big
      source: wide
      model: "a-model"
"""

BIG_CONTRACT = """
id: too-wide
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
context:
  max_input_tokens: 32768
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
limits:
  max_output_tokens: 1024
"""


def _bound(rung: str) -> Any:
    """What the pool resolves a rung to — below the seam, where the machine is."""
    from mcgyvr.config import parse
    from mcgyvr.pool import source_map

    pool = source_map(parse(LADDER))
    return pool.bind(rung)


def test_a_resolved_rung_reports_the_window_its_source_serves() -> None:
    """Asked below the seam, and answered from the source.

    Two rungs, two sources, two declared windows. A default baked into a
    dataclass satisfies neither, which is the point of asserting both.
    """
    small = required(
        "read the context window a rung serves, from what the pool resolved it to",
        lambda: _bound("small").context_window,
    )
    big = _bound("big").context_window
    assert small == 4096 and big == 32768, (
        f"the window must come from the source that serves the rung; got "
        f"small={small!r} big={big!r}"
    )


def test_a_rung_above_the_seam_still_says_nothing_about_its_machine() -> None:
    """The invariant this must not buy its way past.

    ``pool.py:164`` makes the emptiness of ``Rung`` the seam, and
    ``tests/test_pool.py`` pins it. A window added there would let every caller
    above the seam depend on where its work runs.
    """
    import dataclasses

    from mcgyvr.pool import Rung

    assert {f.name for f in dataclasses.fields(Rung)} == {"name", "model"}, (
        "the window belongs below the seam; adding it to Rung breaks the "
        "property that lets a rung be re-pointed at another machine"
    )


def test_a_contract_wider_than_the_rung_it_reaches_is_refused() -> None:
    """The case that is silently truncated today.

    A contract declaring 32768 of input, dispatched to the rung serving 4096,
    must be refused — and the refusal must name 4096, because the operator's
    next move is to decompose against the rung's real window and a message
    quoting 32768 tells them the opposite.
    """
    from mcgyvr.contract import loads

    check = required(
        "refuse a contract that cannot fit the window of the rung it reaches",
        lambda: (
            __import__(
                "mcgyvr.gate.preflight", fromlist=["check_contract_against_rung"]
            ).check_contract_against_rung
        ),
    )
    issue = check(loads(BIG_CONTRACT), "x" * 200, rung=_bound("small"))
    assert issue is not None, "a 32768-token ceiling on a 4096 rung must refuse"
    assert "4096" in issue.message, (
        f"the refusal must name the rung's window, not the contract's: {issue.message}"
    )


def test_the_same_contract_is_not_refused_on_a_rung_that_has_room() -> None:
    """The opposite direction, on the same contract.

    Same 32768 ceiling, same prompt, a rung serving 32768. A check that refused
    here would be a wall rather than a fit.
    """
    from mcgyvr.contract import loads

    check = required(
        "refuse a contract that cannot fit the window of the rung it reaches",
        lambda: (
            __import__(
                "mcgyvr.gate.preflight", fromlist=["check_contract_against_rung"]
            ).check_contract_against_rung
        ),
    )
    assert check(loads(BIG_CONTRACT), "x" * 200, rung=_bound("big")) is None


def test_a_prompt_larger_than_the_rung_is_refused_whatever_the_contract_declared() -> (
    None
):
    """The truncation the contract's own ceiling cannot see.

    A contract declaring a small ceiling is measured against that and passes,
    while the assembled prompt is larger than the rung will hold. Today only the
    contract's number is enforced, so this is the case that reaches the engine
    and comes back cut.
    """
    from mcgyvr.contract import loads

    narrow = loads(
        BIG_CONTRACT.replace("max_input_tokens: 32768", "max_input_tokens: 2048")
    )
    check = required(
        "refuse a contract that cannot fit the window of the rung it reaches",
        lambda: (
            __import__(
                "mcgyvr.gate.preflight", fromlist=["check_contract_against_rung"]
            ).check_contract_against_rung
        ),
    )
    issue = check(narrow, "x" * 200_000, rung=_bound("small"))
    assert issue is not None, (
        "a prompt far larger than the rung's window must refuse even though the "
        "contract declared a ceiling it fits under"
    )
