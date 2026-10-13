"""A relief rung taking work the rider's own rung is too full for."""

from __future__ import annotations

from pathlib import Path

from mcgyvr.capacity import Capacity
from mcgyvr.config import Config, parse
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.escalate import (
    Assurance,
    Judgement,
)
from mcgyvr.local_pool import SourceMap, source_map
from mcgyvr.route import Try, Verdict
from tests.rungs import RIDE

FAST = "local_fast"


API = "api_big"


RUNG_ID = "0f3c9a1e2b4d4c6f8a0b1c2d3e4f5a6b"


CONTRACT = """
id: fetch-retry
task_type: code
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["pytest -q"]
scope:
  allow: ["src/**/*.py"]
limits:
  attempts: 5
"""


SETUP = """
units:
  local_fast:
    address: http://fast-box.example:8000
    model: qwen2.5-coder-3b
    width: 1
  api_big:
    address: https://api.example.com/v1
    model: vendor-large
    width: 1
    api_key_env: EXAMPLE_API_KEY
ladder:
- local_fast
- api_big
max_escalations: {escalations}
fanout: {fanout}
"""


RELIEF = f"""
relief:
  {RIDE}:
    address: https://hub.example.org/v1
    model: hitchhike@{RUNG_ID}
    api_key_env: HUB_KEY
    width: 1
    position: above_ceiling
"""


def mapped(
    fanout: str = "idle", *, relief: str = RELIEF, escalations: int = 1
) -> tuple[Config, SourceMap]:
    config = parse(SETUP.format(fanout=fanout, escalations=escalations) + relief)
    return config, source_map(config)


def contract() -> Contract:
    return load_contract(CONTRACT)


def capacity_of(
    config: Config, tmp_path: Path, servers: dict[str, int | None] | None = None
) -> Capacity:
    return Capacity.of(config, root=tmp_path / "slots", busy=(servers or {}).get)


class Script:
    """An attempt function that answers from a script, per rung, and logs."""

    def __init__(self, **verdicts: Verdict) -> None:
        self._verdicts = dict(verdicts)
        self.tried: list[str] = []

    def __call__(self, this: Try) -> Judgement:
        name = this.rung.name
        self.tried.append(name)
        verdict = self._verdicts.get(name)
        if verdict is None:
            raise AssertionError(f"an unscripted attempt on {name!r}")
        if verdict is Verdict.PASSED:
            return Judgement(verdict=Verdict.PASSED, assurance=Assurance.UNVERIFIED)
        if verdict is Verdict.DECLINED:
            return Judgement(
                verdict=Verdict.DECLINED, detail="cannot take the request now"
            )
        return Judgement(verdict=Verdict.FAILED, detail="the gate rejected it")
