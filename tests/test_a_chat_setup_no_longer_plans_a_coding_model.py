"""A chat setup no longer plans a coding model.

``mcgyvr setup`` planned every rig as ``coding`` whatever use case it asked,
and the catalog held coder models only, so a chat or agent setup got a coder.
Now setup hands the use case it asked to the plan.

Chat and agent are one unit with the biggest model
that fits, with the most context that fits, at least 8k per user; coding keeps
the shape ``recommend.plan`` gave it.

Promises, read with no Hub (the shipped catalog answers):

* A chat or an agent setup plans a model tagged for that use case and never a
  coder: the biggest that fits the card with 8k of context.
* Its context is the most that fits beside the weights, in whole 256-cell
  steps, never more than the model's own and never under 8192.
* A coding setup plans what it planned before: the largest coder whose
  declared context fits, at that declared context.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr import availability
from mcgyvr.availability import AvailabilityVerdict
from mcgyvr.cli.commands.setup import _setup_placements
from mcgyvr.knowledge import store as ks
from mcgyvr.recommend import MIN_CONTEXT_PER_USER
from mcgyvr.scan import Scan

RIG = "rig.example"


def _placement(use_case: str, vram_mib: int) -> dict[str, Any]:
    scans = {RIG: Scan.of(host=RIG, vram_mib=vram_mib, ram_gb=64.0, cores=8)}
    plan = _setup_placements((RIG,), scans, use_case)[RIG]
    assert plan["candidates_from"] == "shipped"
    placement: dict[str, Any] = dict(plan["placement"])
    return placement


@pytest.fixture(autouse=True)
def _no_decision_model(monkeypatch: pytest.MonkeyPatch) -> None:
    def not_live(endpoint: Any, timeout_s: float = 2.0) -> AvailabilityVerdict:
        return AvailabilityVerdict(
            source="recommend",
            live=False,
            reason="stub",
            how="stub",
            elapsed_s=0.0,
        )

    monkeypatch.setattr(availability, "probe_endpoint", not_live)


def _cost(one: Any, context: int) -> int:
    return int(
        one.size_bytes.value
        + context * one.kv_bytes_per_token.value
        + one.recurrent_bytes_per_slot.value
    )


@pytest.mark.parametrize("use_case", ["chat", "agent"])
@pytest.mark.parametrize("vram_mib", [12288, 16384, 24576])
def test_chat_and_agent_plan_the_biggest_model_of_their_own_that_fits(
    use_case: str, vram_mib: int
) -> None:
    free = vram_mib << 20
    own = [one for one in ks.shipped() if use_case in one.use_cases]
    fitting = [one for one in own if _cost(one, MIN_CONTEXT_PER_USER) <= free]

    placement = _placement(use_case, vram_mib)

    biggest = max(fitting, key=lambda one: one.size_bytes.value)
    assert placement["model_id"] == biggest.model_id
    coders = {one.model_id for one in ks.shipped() if "coding" in one.use_cases}
    assert placement["model_id"] not in coders


@pytest.mark.parametrize("vram_mib", [12288, 16384, 24576])
def test_the_context_is_the_most_that_fits_and_at_least_8k(vram_mib: int) -> None:
    free = vram_mib << 20

    placement = _placement("chat", vram_mib)

    record = next(r for r in ks.shipped() if r.model_id == placement["model_id"])
    context = placement["context_length"]
    assert context % 256 == 0
    assert MIN_CONTEXT_PER_USER <= context <= record.context_length.value
    assert _cost(record, context) <= free
    assert (
        context + 256 > record.context_length.value
        or _cost(record, context + 256) > free
    )


@pytest.mark.parametrize(
    ("vram_mib", "coder"),
    [
        (12288, "Qwen/Qwen2.5-Coder-7B-Instruct"),
        (24576, "Qwen/Qwen2.5-Coder-14B-Instruct"),
    ],
)
def test_a_coding_setup_plans_the_coder_it_planned_before(
    vram_mib: int, coder: str
) -> None:
    placement = _placement("coding", vram_mib)

    assert placement["model_id"] == coder
    record = next(r for r in ks.shipped() if r.model_id == coder)
    assert placement["context_length"] == record.context_length.value
    assert placement["quant"] == "Q4_K_M"
