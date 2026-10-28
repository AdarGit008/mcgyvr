"""The local orchestrator unit: when a local-only setup provisions one.

The rule under test: local-only `mcgyvr-code` provisions a local
orchestrator whose width is the number of users, flagged (not refused) on a
single-user setup. `code`, `chat` and `agent` serve their model raw, with no
proposer in the path, and need none; hybrid has an API orchestrator and
provisions none either.
"""

from __future__ import annotations

import pytest

from mcgyvr.config import CHAT, LocalOrchestrator, local_orchestrator


def test_hybrid_provisions_no_local_orchestrator() -> None:
    for use_case in ("mcgyvr-code", "code", "chat", "agent"):
        decision = local_orchestrator(use_case=use_case, local_only=False, users=1)
        assert decision == LocalOrchestrator(provision=False)


@pytest.mark.parametrize("use_case", [CHAT, "code", "agent"])
def test_local_only_raw_use_cases_provision_no_local_orchestrator(
    use_case: str,
) -> None:
    """A raw use case serves its model as is, so nothing decomposes a request."""
    decision = local_orchestrator(use_case=use_case, local_only=True, users=3)
    assert decision == LocalOrchestrator(provision=False)


def test_local_only_mcgyvr_code_provisions_an_orchestrator() -> None:
    decision = local_orchestrator(use_case="mcgyvr-code", local_only=True, users=4)
    assert decision.provision is True
    assert decision.width == 4


def test_the_orchestrators_width_is_the_number_of_users() -> None:
    for users in (1, 2, 8):
        decision = local_orchestrator(
            use_case="mcgyvr-code", local_only=True, users=users
        )
        assert decision.width == users


def test_single_user_is_flagged_not_refused() -> None:
    decision = local_orchestrator(use_case="mcgyvr-code", local_only=True, users=1)
    assert decision.provision is True
    assert decision.flag_single_user is True


def test_multi_user_is_not_flagged() -> None:
    decision = local_orchestrator(use_case="mcgyvr-code", local_only=True, users=2)
    assert decision.flag_single_user is False


def test_zero_users_is_refused_not_guessed() -> None:
    with pytest.raises(ValueError, match="users"):
        local_orchestrator(use_case="mcgyvr-code", local_only=True, users=0)
