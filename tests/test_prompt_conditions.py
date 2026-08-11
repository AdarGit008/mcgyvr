"""The scaffold ablation (#225): one named condition, and it is run identity.

The bench's driver question — what actually makes a problem hard for the
floor model — was first asked as two separately authored cohorts, and that
design could not answer it: unpaired comparisons spend power like two
independent samples, which is ADR-0019's wall in a new costume
(`tools/bench/strata.json`, block 3). The paired form asks the same question
of *one* problem under two renders, so the discordant pairs carry the power.

`noscaffold` is that render: it empties `target_content`, which is the single
field `render_user_message` turns into the "CURRENT CONTENT OF <target>"
section. The problem, the interface, the stop conditions and the checker are
untouched — only how much code the model must produce moves.

What these tests hold is the part that is easy to get wrong and expensive to
discover later: that the ablation removes exactly one section and nothing
else, that it is refused as a *silent* variation by being written into
run.json (`bundle_sha256` hashes the system prompt, so a user-message
ablation is invisible to it), and that a directory measured under one
condition refuses the other — the cap's own argument, which this project
already applies to a resume across output caps.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest

from mcgyvr.contract import Contract, loads
from mcgyvr.worker.prompt import build_prompt

REPO = Path(__file__).resolve().parent.parent


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


breadth = _by_path("breadth_measure", REPO / "tools" / "breadth" / "measure.py")


SCAFFOLDED = """
id: t001-worked-example
task_type: function_implementation
task: >-
  Implement countTicks. It returns how many ticks a schedule fires.
target: solution.ts
target_content: |
  export function countTicks(schedule: string): number {
    // TODO: implement
    return 0;
  }
interface: "export function countTicks(schedule: string): number"
stop_conditions:
  - the schedule syntax is not stated
acceptance: ["node accept.mjs"]
risk: low
scope:
  allow: ["solution.ts"]
"""


def _contract() -> Contract:
    return loads(SCAFFOLDED)


def test_the_ablation_removes_the_scaffold_section_and_nothing_else() -> None:
    """One section leaves; every other section survives byte for byte."""
    contract = _contract()
    stock = build_prompt(contract).user
    ablated = build_prompt(breadth.ablate(contract, breadth.NO_SCAFFOLD)).user

    assert "CURRENT CONTENT OF solution.ts" in stock
    assert "CURRENT CONTENT OF solution.ts" not in ablated
    assert "TODO: implement" not in ablated

    # Everything the contract says about the *task* is unchanged: what is
    # asked, what it must expose, when to stop, and where to write.
    survivors = [
        section
        for section in stock.split("\n\n")
        if "CURRENT CONTENT OF" not in section
    ]
    assert survivors, "a prompt of nothing but scaffold would make this vacuous"
    for section in survivors:
        assert section in ablated


def test_the_stock_condition_is_the_contract_untouched() -> None:
    """`stock` must be exactly what production dispatches, not a copy of it."""
    contract = _contract()
    assert breadth.ablate(contract, breadth.STOCK) is contract


def test_ablating_a_contract_without_a_scaffold_is_a_no_op() -> None:
    """Which is why the eligible set is chosen by the caller, not here.

    An ineligible task rendered under both conditions produces two identical
    prompts and therefore a concordant pair, diluting the paired test it was
    added to. The ablation cannot detect that for the caller; it can only be
    honest that it did nothing.
    """
    bare = loads(
        SCAFFOLDED.replace(
            "target_content: |\n"
            "  export function countTicks(schedule: string): number {\n"
            "    // TODO: implement\n"
            "    return 0;\n"
            "  }\n",
            "",
        )
    )
    assert not bare.target_content
    assert (
        build_prompt(breadth.ablate(bare, breadth.NO_SCAFFOLD)).user
        == build_prompt(bare).user
    )


def test_an_unknown_condition_is_refused_rather_than_ignored() -> None:
    """A typo must not silently dispatch the stock render under a false name."""
    with pytest.raises(breadth.bundle.MeasureError):
        breadth.ablate(_contract(), "no-scaffold")


def test_the_condition_is_recorded_in_run_identity(tmp_path: Path) -> None:
    """`bundle_sha256` hashes the system prompt; the ablation is in the user
    message. Without this field the two runs are indistinguishable on paper."""
    written = _write_run(tmp_path, breadth.NO_SCAFFOLD)
    assert written["condition"] == breadth.NO_SCAFFOLD


def test_a_directory_refuses_a_resume_under_another_condition(
    tmp_path: Path,
) -> None:
    """The cap's argument: resuming across conditions averages two experiments.

    This is the check that makes the knob safe to leave in the tool. A run
    directory that accepted rows from both renders would report a single rate
    over a mixture nobody chose.
    """
    _write_run(tmp_path, breadth.STOCK)
    with pytest.raises(breadth.bundle.MeasureError, match="condition"):
        _write_run(tmp_path, breadth.NO_SCAFFOLD)


@dataclass(frozen=True)
class _Protocol:
    """Stands in for the runner enum, which `record_run` reads `.value` off."""

    value: str = "openai"


@dataclass(frozen=True)
class _Worker:
    endpoint: str = "http://rig:11434"
    model: str = "qwen2.5-coder:3b"
    protocol: _Protocol = _Protocol()


def _write_run(out: Path, condition: str) -> dict[str, object]:
    breadth.record_run(
        out,
        _Worker(),
        {"started": "2026-08-11T00:00:00+00:00", "tasks": []},
        tier="bench-ts",
        draws=0,
        condition=condition,
    )
    written: dict[str, object] = json.loads(
        (out / "run.json").read_text(encoding="utf-8")
    )
    return written
