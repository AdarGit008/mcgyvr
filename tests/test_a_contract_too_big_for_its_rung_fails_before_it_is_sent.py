"""A contract too big for the rung it was sent to fails before it is sent.

Before this, a coding contract whose prompt did not fit the window its rung
serves went out anyway: llama.cpp answered ``400``, the runner re-raised it as
a :class:`~mcgyvr.runner.BackendError`, and the run ended as ``error`` naming
an HTTP status rather than the two numbers that did not fit. The check that
says so — :func:`mcgyvr.gate.preflight.check_contract_against_rung` — existed
and nothing called it.

Owner ruling (Round 7, "oversize contract"): a task too big for the rung it was
sent to FAILS, and is not climbed to a bigger rung on its own; the size is
asserted against that rung *before* dispatch, and the failure names the
contract's tokens, the rung's window and the rung.

What is asserted below: the refusal happens before anything reaches the
runner; it is named (its own exception class, and the numbers and the rung in
its message); through a whole run it ends as ``error`` on the rung it was sent
to, with no dearer rung tried; and because nothing was sent, the journal holds
no row for a dispatch that never happened. Every machine here is invented and
no server is started: the runner's ``dispatch`` is the substituted seam.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.pool import source_map

#: Two units on an invented rig: the cheap one serves a 2048-token window, the
#: dear one 32768. The dear one is there so "not climbed" can be asserted.
LADDER = """\
units:
  local_narrow:
    address: http://rig-a.invalid:8080
    model: narrow-coder
    rig: rig-a
    width: 1
    window: 2048
  local_wide:
    address: http://rig-a.invalid:8081
    model: wide-coder
    rig: rig-a
    width: 1
    window: 32768
ladder:
- local_narrow
- local_wide
"""

#: A coding contract whose own ceiling (the schema's 4096) is larger than the
#: narrow rung's 2048: question 1 of the rung check.
CONTRACT = """
id: oversize
task_type: function_implementation
task: Set VALUE to 1.
target: src/pkg/value.py
stop_conditions: ["The value is not stated."]
acceptance: ["sh -c 'grep -q VALUE src/pkg/value.py'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""


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
    from mcgyvr.pool import Protocol
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
            model="wide-coder",
            source=rung,
            protocol=Protocol.OPENAI,
            max_output_tokens=request.max_output_tokens,
            latency_s=0.0,
        )

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    return seen


# --- the binding refuses, by name, before the runner ----------------------


def test_a_contract_whose_ceiling_exceeds_the_rungs_window_is_not_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.drive import ContractTooLargeForRungError, dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    sent = _sent(monkeypatch)
    pool = source_map(parse_config(LADDER))
    contract = load_contract(CONTRACT)
    assert contract.max_input_tokens == 4096

    with pytest.raises(ContractTooLargeForRungError) as refused:
        dispatch_prompt(pool, "local_narrow", build_prompt(contract), contract)

    assert sent == [], "nothing may reach the runner once the size is known not to fit"
    said = str(refused.value)
    for named in ("oversize", "local_narrow", "4096", "2048"):
        assert named in said, f"the refusal must name {named!r}: {said}"


def test_a_prompt_bigger_than_the_rungs_window_is_not_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The case the contract's own ceiling cannot see: question 3.

    The contract declares a ceiling the rung serves, and the prompt it is
    assembled into fits that ceiling — but not beside the reply the rung must
    hold room for. This is the request llama.cpp answered with a ``400``.
    """
    from mcgyvr.drive import ContractTooLargeForRungError, dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    sent = _sent(monkeypatch)
    pool = source_map(parse_config(LADDER))
    contract = load_contract(
        CONTRACT
        + "context:\n  max_input_tokens: 2048\n"
        + f"interface: |\n  {'def value() -> int: ...  ' * 140}\n"
    )
    prompt = build_prompt(contract)
    assert prompt.fits, "the prompt fits the contract's own ceiling"

    with pytest.raises(ContractTooLargeForRungError) as refused:
        dispatch_prompt(pool, "local_narrow", prompt, contract)

    assert sent == []
    said = str(refused.value)
    assert "local_narrow" in said and "2048" in said, said
    assert "prompt-too-large" in said, said


def test_the_same_contract_is_sent_to_a_rung_that_serves_its_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.drive import dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    sent = _sent(monkeypatch)
    pool = source_map(parse_config(LADDER))
    contract = load_contract(CONTRACT)

    dispatch_prompt(pool, "local_wide", build_prompt(contract), contract)

    assert sent == ["local_wide"]


def test_a_contract_cap_too_large_for_the_window_names_the_contracts_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reply-cap refusal says whose number it is.

    The narrow rung declares no ``output_tokens``, so the cap is the
    contract's. Telling the operator to lower the rung's ``output_tokens`` — a
    key that is not set — sends them to the wrong file.
    """
    from mcgyvr.drive import OutputCapTooLargeError, dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    sent = _sent(monkeypatch)
    pool = source_map(parse_config(LADDER))
    contract = load_contract(
        CONTRACT.replace("max_output_tokens: 256", "max_output_tokens: 2048")
        + "context:\n  max_input_tokens: 2048\n"
    )

    with pytest.raises(OutputCapTooLargeError) as refused:
        dispatch_prompt(pool, "local_narrow", build_prompt(contract), contract)

    assert sent == []
    said = str(refused.value)
    assert "limits.max_output_tokens" in said, said
    assert "units.local_narrow.output_tokens" not in said, said


# --- through a whole run: it fails, on its rung, and is not climbed ---------


def test_a_run_fails_on_the_rung_it_was_sent_to_and_does_not_climb(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.drive import Recording, worker_attempt
    from mcgyvr.escalate import Halted, Outcome, escalate

    sent = _sent(monkeypatch)
    config = parse_config(LADDER)
    pool = source_map(config)
    contract = load_contract(CONTRACT)
    journal = tmp_path / "journal" / "orch.jsonl"
    journal.parent.mkdir()
    recording = Recording(path=journal, orchestrator="orch")

    from mcgyvr.sandbox.tempdir import TempDirSandbox

    with TempDirSandbox(repo) as sandbox:
        outcome = escalate(
            config,
            pool,
            contract,
            worker_attempt(config, pool, contract, sandbox, recording=recording),
        )

    assert isinstance(outcome, Halted), outcome
    assert outcome.outcome is Outcome.ERROR
    assert sent == [], "neither rung was sent the contract — no climb to the wide one"
    (only,) = outcome.history
    assert only.rung == "local_narrow"
    assert only.raised
    assert "ContractTooLargeForRungError" in only.detail, only.detail
    assert "4096" in only.detail and "2048" in only.detail, only.detail
    assert (outcome.attempts_spent, outcome.escalations) == (0, 0)
    assert (only.rows, only.draw) == (0, None), (
        "nothing was dispatched, so no journal row was written for it"
    )
    rows = journal.read_text(encoding="utf-8") if journal.exists() else ""
    assert rows.strip() == "", (
        f"the journal records a dispatch that never happened: {rows}"
    )
