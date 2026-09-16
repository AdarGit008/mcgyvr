"""A unit's ``draws`` override the ladder's ``breadth.draws`` for that unit.

Breadth is most defensible on a cheap rung that is often almost right, and
least on the dear rung a climb ends on — and ``breadth.draws`` was one number
for the whole ladder. The override is spelled the way ``attempts`` is spelled:
a policy map keyed by unit name, cross-checked against the declared units at
load, read beside :func:`~mcgyvr.route.attempts_for` by a function of the same
shape. It is not a fact about the unit — a unit is what a process is and can
physically do, and how many answers to ask it for is how work moves — so it
lives in ``policy.yaml`` with the other routing decisions, and never in the
locked ``fleet.yaml``.

The effective breadth for a rung is its own entry where it has one and the
ladder's ``breadth.draws`` where it has not, and ``mcgyvr pool`` prints it
beside the attempt budget, where the routing decision is already shown.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.config import ConfigSchemaError, parse
from mcgyvr.contract import loads as load_contract
from mcgyvr.drive import worker_attempt
from mcgyvr.pool import Rung, source_map
from mcgyvr.route import Try, Verdict, draws_for
from mcgyvr.sandbox.tempdir import TempDirSandbox
from tests import livejournal as lj

TWO_UNITS = """\
units:
  small:
    address: http://localhost:11434
    model: qwen2.5-coder:3b
    rig: workstation
  big:
    address: http://localhost:11435
    model: qwen2.5-coder:7b
    rig: workstation
ladder:
- small
- big
"""


def test_draws_for_reads_the_units_override_and_falls_back_to_the_breadth() -> None:
    config = parse(TWO_UNITS + "breadth:\n  draws: 2\ndraws:\n  small: 3\n")

    assert draws_for(config, "small") == 3, "the unit's own entry wins"
    assert draws_for(config, "big") == 2, "a unit with no entry draws the breadth"
    assert draws_for(parse(TWO_UNITS), "small") == 1, "and the breadth defaults to 1"


def test_a_draws_entry_for_an_undeclared_unit_is_refused_at_load() -> None:
    with pytest.raises(
        ConfigSchemaError, match=r"draws\.ghost: 'ghost' is not a declared"
    ):
        parse(TWO_UNITS + "draws:\n  ghost: 2\n")


def test_a_draws_entry_below_one_is_refused_at_load() -> None:
    with pytest.raises(ConfigSchemaError, match=r"draws\.small: must be at least 1"):
        parse(TWO_UNITS + "draws:\n  small: 0\n")


def test_the_attempt_draws_what_its_unit_declares(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three dispatches under ``draws: {unit: 3}`` and no ``breadth`` block at all."""
    sent = lj.scripted(monkeypatch, lj.BAD_REPLY, lj.BAD_REPLY, lj.BAD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    config = parse(lj.LADDER + "draws:\n  local_qwen-7b: 3\n")
    contract = load_contract(lj.MODEL_CONTRACT)
    rung = Rung(name="local_qwen-7b", model="qwen2.5-coder:7b")

    with TempDirSandbox(repo) as sandbox:
        attempt = worker_attempt(config, source_map(config), contract, sandbox)
        judgement = attempt(Try(rung=rung, attempt=1, of=1))

    assert judgement.verdict is Verdict.FAILED
    assert len(sent) == 3, "the unit's breadth is what was dispatched"
    assert judgement.draws == 3, "and what the judgement says was asked for"


def test_pool_prints_the_effective_draws_beside_the_attempts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = lj.make_config(tmp_path / "setup")
    assert lj.main(["pool", str(config)]) == 0
    plain = capsys.readouterr().out
    assert "1 attempt" in plain
    assert "draw" not in plain, "a single draw is the default and is not announced"

    lj.append_policy(config, "draws:\n  local_qwen-7b: 3\n")
    assert lj.main(["pool", str(config)]) == 0
    widened = capsys.readouterr().out
    (line,) = [line for line in widened.splitlines() if "local_qwen-7b" in line]
    assert "1 attempt" in line and "3 draws" in line, line
