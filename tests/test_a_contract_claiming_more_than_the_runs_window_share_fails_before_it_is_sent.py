"""A contract claiming more than the run's window share fails before it is sent.

The run-wide ``max_window_fraction`` was in the config schema and nothing read
it: a run that declared "no contract may claim more than a quarter of a rung's
window" sent every contract anyway. The check that enforces a share —
:func:`mcgyvr.gate.preflight.check_contract_against_rung`, through its
``default_fraction`` — already existed and already enforced the contract's own
``limits.max_window_fraction`` at dispatch (#616); it was never handed the
run's.

The run-wide config is enforced (after #616). A
contract claiming more than that share fails before it is sent — the same
outcome as #616's oversize refusal: ``error`` on the rung it was sent to, no
journal row, no wake, no climb.

How the two shares combine is ``test_window_fraction``'s to pin: the stricter
of the contract's own share and the run's applies, so the run's is a ceiling a
contract cannot raise (after #621; the whole run is in
``test_a_contract_cannot_claim_more_of_a_window_than_its_run_allows``). The
refusal names which of the two was hit, because the fix lives in a different
file for each.

Every machine here is invented and no server is started: the runner's
``dispatch`` and the waker are the substituted seams.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.local_pool import source_map
from tests.drives import (  # noqa: F401 - fixtures
    RUN_SHARE,
    _run,
    _sent,
    _sharing,
    _Waker,
    a_git_repo,
)
from tests.drives import SHARE_CONTRACT as CONTRACT
from tests.drives import SHARE_LADDER as LADDER

# --- through a whole run: the run's share is read and enforced ---------------


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return a_git_repo(tmp_path)


def test_a_run_whose_config_caps_the_share_fails_the_greedy_contract_unsent(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.escalate import Halted, Outcome

    outcome, sent, waker, journal = _run(repo, tmp_path, monkeypatch, policy=RUN_SHARE)

    assert isinstance(outcome, Halted), outcome
    assert outcome.outcome is Outcome.ERROR
    assert sent == [], "neither rung was sent the contract — no climb to the wide one"
    assert waker.woken == [], "a card was woken for a contract refused before send"
    (only,) = outcome.history
    assert only.rung == "local_narrow"
    assert only.raised
    assert "ContractTooLargeForRungError" in only.detail, only.detail
    assert "window-share" in only.detail, only.detail
    assert (outcome.attempts_spent, outcome.escalations) == (0, 0)
    assert (only.rows, only.draw) == (0, None)
    rows = journal.read_text(encoding="utf-8") if journal.exists() else ""
    assert rows.strip() == "", f"the journal records a dispatch never sent: {rows}"


def test_the_refusal_names_the_runs_config_as_the_limit_that_was_hit(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome, _, _, _ = _run(repo, tmp_path, monkeypatch, policy=RUN_SHARE)

    (only,) = outcome.history
    assert "run's `max_window_fraction`" in only.detail, only.detail
    assert "0.10" in only.detail, only.detail
    assert "limits.max_window_fraction" not in only.detail, (
        "the contract declared no share, so naming its own limit sends the "
        f"operator to a key that is not set: {only.detail}"
    )


def test_the_same_run_without_a_share_sends_the_contract(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unset is no share enforced, not a default the check invents."""
    _, sent, _, _ = _run(repo, tmp_path, monkeypatch, policy="")

    assert sent[:1] == ["local_narrow"], sent


# --- the contract's own share: named as its own ------------------------------


def test_a_refusal_on_the_contracts_own_share_names_the_contract(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.escalate import Halted

    outcome, sent, _, _ = _run(
        repo,
        tmp_path,
        monkeypatch,
        policy="",
        contract_text=_sharing(0.1),
    )

    assert isinstance(outcome, Halted) and sent == []
    (only,) = outcome.history
    assert "contract's own `limits.max_window_fraction`" in only.detail, only.detail
    assert "run's `max_window_fraction`" not in only.detail, only.detail


# --- the binding: dispatch_prompt takes the run's share too ------------------


def test_dispatch_prompt_refuses_on_the_runs_share_before_the_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.drive import ContractTooLargeForRungError, dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    sent = _sent(monkeypatch)
    pool = source_map(parse_config(LADDER))
    contract = load_contract(CONTRACT)

    with pytest.raises(ContractTooLargeForRungError) as refused:
        dispatch_prompt(
            pool, "local_narrow", build_prompt(contract), contract, window_fraction=0.1
        )

    assert sent == []
    said = str(refused.value)
    assert "greedy" in said and "local_narrow" in said and "4096" in said, said
    assert "run's `max_window_fraction`" in said, said
