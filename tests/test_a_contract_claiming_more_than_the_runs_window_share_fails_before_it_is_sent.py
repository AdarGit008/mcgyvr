"""A contract claiming more than the run's window share fails before it is sent.

The run-wide ``max_window_fraction`` was in the config schema and nothing read
it: a run that declared "no contract may claim more than a quarter of a rung's
window" sent every contract anyway. The check that enforces a share —
:func:`mcgyvr.gate.preflight.check_contract_against_rung`, through its
``default_fraction`` — already existed and already enforced the contract's own
``limits.max_window_fraction`` at dispatch (#616); it was never handed the
run's.

Owner ruling (contract assert, after #616): make the run-wide config work. A
contract claiming more than that share fails before it is sent — the same
outcome as #616's oversize refusal: ``error`` on the rung it was sent to, no
journal row, no wake, no climb.

How the two shares combine is ``test_window_fraction``'s to pin: the stricter
of the contract's own share and the run's applies, so the run's is a ceiling a
contract cannot raise (owner ruling, after #621; the whole run is in
``test_a_contract_cannot_claim_more_of_a_window_than_its_run_allows``). The
refusal names which of the two was hit, because the fix lives in a different
file for each.

Every machine here is invented and no server is started: the runner's
``dispatch`` and the waker are the substituted seams.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.local_pool import source_map

#: Two units on an invented rig. The narrow one serves 4096 tokens, which the
#: contract's own ceiling (the schema's 4096) fits, so only the share can
#: refuse it; the wide one is there so "not climbed" can be asserted.
LADDER = """\
units:
  local_narrow:
    address: http://rig-b.invalid:8080
    model: narrow-coder
    rig: rig-b
    width: 1
    window: 4096
  local_wide:
    address: http://rig-b.invalid:8081
    model: wide-coder
    rig: rig-b
    width: 1
    window: 32768
ladder:
- local_narrow
- local_wide
"""

#: The run's share: a quarter of any rung's window.
RUN_SHARE = "max_window_fraction: 0.25\n"

#: A reply of 1024 tokens alone is a quarter of the narrow window, so with any
#: prompt beside it the contract claims more than a quarter — and still fits.
CONTRACT = """
id: greedy
task_type: function_implementation
task: Set VALUE to 1.
target: src/pkg/value.py
stop_conditions: ["The value is not stated."]
acceptance: ["sh -c 'grep -q VALUE src/pkg/value.py'"]
limits:
  max_output_tokens: 1024
scope:
  allow: ["src/**"]
"""


def _sharing(share: float) -> str:
    """The same contract, declaring its own share of the window."""
    return CONTRACT.replace(
        "max_output_tokens: 1024\n",
        f"max_output_tokens: 1024\n  max_window_fraction: {share}\n",
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "value.py").write_text("VALUE = 0\n", encoding="utf-8")
    identity = ("-c", "user.name=t", "-c", "user.email=t@example.invalid")
    for args in (("init", "-q"), ("add", "-A"), (*identity, "commit", "-qm", "base")):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def _sent(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every rung a request reaches; answer with a valid file."""
    from mcgyvr import drive
    from mcgyvr.local_pool import Protocol
    from mcgyvr.runner import Completion, StopReason

    seen: list[str] = []

    def fake_dispatch(
        source_map: Any, rung: str, request: Any, *, capacity: Any = None
    ) -> Completion:
        seen.append(rung)
        return Completion(
            text="```python\nVALUE = 1\n```",
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="narrow-coder",
            source=rung,
            protocol=Protocol.OPENAI,
            max_output_tokens=request.max_output_tokens,
            latency_s=0.0,
        )

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    return seen


class _Waker:
    """A waker that records every rung it was asked to wake, then sends."""

    def __init__(self) -> None:
        self.woken: list[str] = []

    def dispatching(self, rung: str, send: Any) -> Any:
        self.woken.append(rung)
        return send()


def _run(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    policy: str,
    contract_text: str = CONTRACT,
) -> tuple[Any, list[str], _Waker, Path]:
    from mcgyvr import drive
    from mcgyvr.drive import Recording, worker_attempt
    from mcgyvr.escalate import escalate
    from mcgyvr.sandbox.tempdir import TempDirSandbox

    sent = _sent(monkeypatch)
    waker = _Waker()
    monkeypatch.setattr(drive, "wake_for_config", lambda config: waker)
    config = parse_config(LADDER + policy)
    pool = source_map(config)
    contract = load_contract(contract_text)
    journal = tmp_path / "journal" / "orch.jsonl"
    journal.parent.mkdir()
    recording = Recording(path=journal, orchestrator="orch")
    with TempDirSandbox(repo) as sandbox:
        outcome = escalate(
            config,
            pool,
            contract,
            worker_attempt(config, pool, contract, sandbox, recording=recording),
        )
    return outcome, sent, waker, journal


# --- through a whole run: the run's share is read and enforced ---------------


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
    assert "0.25" in only.detail, only.detail
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
        contract_text=_sharing(0.25),
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
            pool, "local_narrow", build_prompt(contract), contract, window_fraction=0.25
        )

    assert sent == []
    said = str(refused.value)
    assert "greedy" in said and "local_narrow" in said and "4096" in said, said
    assert "run's `max_window_fraction`" in said, said
