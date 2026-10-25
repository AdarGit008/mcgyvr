"""A ladder with the defaults climbs every rung; a stated `max_escalations` still caps.

`max_escalations` used to default to 1, so a three-rung ladder stopped after
its second rung with `escalation_ceiling` — the dearest rung, the one most
likely to do the work, was never entered unless a setup knew to raise it.
Unset now means every rung of the ladder may be entered; a number a setup
states is the ceiling it says.
"""

from __future__ import annotations

from mcgyvr.config import SCHEMA, parse
from mcgyvr.contract import loads as load_contract
from mcgyvr.escalate import Ceiling, Halted, Outcome, ascent, escalate, judge
from mcgyvr.local_pool import source_map
from mcgyvr.route import Try, Verdict, family_of

LADDER = """\
units:
  local_a:
    address: http://localhost:11434
    model: small-coder
    rig: workstation
    width: 1
    window: 32768
  local_b:
    address: http://localhost:11435
    model: medium-coder
    rig: workstation
    width: 1
    window: 32768
  local_c:
    address: http://localhost:11436
    model: large-coder
    rig: workstation
    width: 1
    window: 32768
ladder:
- local_a
- local_b
- local_c
"""

CONTRACT = """
id: impl
task_type: code
task: Set VALUE to 1.
target: src/pkg/messy.py
stop_conditions: ["The value is not stated."]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""


def _climb(policy: str = "") -> tuple[Halted, list[str]]:
    """Climb the ladder with every attempt refused; return the halt and the rungs."""
    from mcgyvr.gate import Finding, GateResult

    config = parse(LADDER + policy)
    pool = source_map(config)
    contract = load_contract(CONTRACT)
    tried: list[str] = []
    refused = GateResult(
        findings=(Finding(check="lint", path="src/pkg/messy.py", message="E501"),)
    )

    def attempt(this: Try):  # type: ignore[no-untyped-def]
        tried.append(this.rung.name)
        return judge(
            contract,
            family_of(config, this.rung.name),
            refused,
            rung=this.rung.name,
            attempt=this.attempt,
        )

    outcome = escalate(config, pool, contract, attempt)
    assert isinstance(outcome, Halted), outcome
    return outcome, tried


def test_the_default_is_unset_and_reads_as_every_rung() -> None:
    (field,) = [f for f in SCHEMA if f.name == "max_escalations"]
    assert field.default is None
    assert "every rung of the ladder" in field.doc

    config = parse(LADDER)
    assert Ceiling.of(config).escalations is None
    route = ascent(config, source_map(config), load_contract(CONTRACT))
    assert route.most_rungs == 3


def test_a_three_rung_ladder_with_defaults_climbs_every_rung() -> None:
    halted, tried = _climb()

    assert tried == ["local_a", "local_b", "local_c"]
    assert halted.outcome is Outcome.LADDER_SPENT, halted.detail
    assert halted.escalations == 2
    assert [a.verdict for a in halted.history] == [Verdict.FAILED] * 3
    assert [a.notes.rung for a in halted.history if a.notes] == tried


def test_a_stated_ceiling_still_caps_the_climb() -> None:
    halted, tried = _climb("max_escalations: 1\n")

    assert tried == ["local_a", "local_b"]
    assert halted.outcome is Outcome.ESCALATION_CEILING
    assert "max_escalations (1)" in halted.detail
