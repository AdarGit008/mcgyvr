"""A contract cannot claim more of a window than its run allows.

Owner ruling (after #621): the run's ``max_window_fraction`` is a hard
ceiling. Before, a contract's own ``limits.max_window_fraction`` won wherever
it stated one, so a contract could grant itself nine tenths of a rung's window
under a run that allowed a quarter. Now the stricter of the two applies: a
contract may hold itself to less than the run allows, never to more.

Through a whole run on an invented rig, as #621's tests run it: the refusal is
the same outcome as any share refusal — ``error`` on the rung the contract was
sent to, nothing dispatched, nothing woken, no climb — and it names the limit
that was hit, the run's, because raising the contract's would change nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_a_contract_claiming_more_than_the_runs_window_share_fails_before_it_is_sent import (  # noqa: E501
    RUN_SHARE,
    _run,
    _sharing,
    repo,
)

__all__ = ["repo"]  # the fixture, used by name


def test_a_contract_declaring_a_wider_share_than_its_run_is_refused_unsent(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.escalate import Halted, Outcome

    outcome, sent, waker, _ = _run(
        repo, tmp_path, monkeypatch, policy=RUN_SHARE, contract_text=_sharing(0.9)
    )

    assert isinstance(outcome, Halted), outcome
    assert outcome.outcome is Outcome.ERROR
    assert sent == [], "the contract's own 0.9 let it past the run's 0.25"
    assert waker.woken == []
    (only,) = outcome.history
    assert only.rung == "local_narrow"
    assert "window-share" in only.detail, only.detail
    assert "run's `max_window_fraction`" in only.detail, only.detail
    assert "0.25" in only.detail, only.detail
    assert "limits.max_window_fraction" not in only.detail, (
        "the run's share was hit, and raising the contract's would change "
        f"nothing: {only.detail}"
    )


def test_a_contract_holding_itself_to_less_than_its_run_is_held_to_its_own(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run allows nine tenths and the contract a quarter: the quarter."""
    from mcgyvr.escalate import Halted

    outcome, sent, _, _ = _run(
        repo,
        tmp_path,
        monkeypatch,
        policy="max_window_fraction: 0.9\n",
        contract_text=_sharing(0.25),
    )

    assert isinstance(outcome, Halted) and sent == []
    (only,) = outcome.history
    assert "contract's own `limits.max_window_fraction`" in only.detail, only.detail
    assert "run's `max_window_fraction`" not in only.detail, only.detail


def test_a_contract_inside_both_shares_is_sent(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, sent, _, _ = _run(
        repo,
        tmp_path,
        monkeypatch,
        policy="max_window_fraction: 0.9\n",
        contract_text=_sharing(0.8),
    )

    assert sent[:1] == ["local_narrow"], sent
