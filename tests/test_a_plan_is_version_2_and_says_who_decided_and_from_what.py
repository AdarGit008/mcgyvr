"""A plan is version 2: units per rig, sized by the serving sizer, and it says
who decided and from what.

Owner, Round 2 (2026-10-07): "Plan shape: a FULL LADDER PER RIG. Each unit has
rig, card(s), model, quant, context, slots, and role (always-on /
sleeps-until-needed / Jev). Sized with the product's existing serving sizer
(serving.fit, sharding.py, vramfit), not recommend's own _fits." Plan section 7
is the schema; orchestrator calls on P2 and P4: the decision is
``decision: {by, why}``, a question to Jev is shortlisted to 8 options or
fewer, and the plan's ``knowledge`` names the cache files that were skipped.

Promises:

* The plan says ``schema_version: 2``, the use case, the priority, the users,
  the fleet name the stamp will carry, and per rig what was measured and the
  units planned there. Every unit is named ``<rig>-<model>-<port>``, unique in
  the plan, and the ladder lists the units.
* Every unit says its card(s), engine, model (repository, revision, file,
  quantisation), port, context per slot, slots, KV cache types, expert
  offload, speculative head, the serving sizer's own fit sentence, its
  download (bytes, sha256, whether it is already there, where it goes) and
  where its numbers came from. The download total is the sum of what is not
  there yet.
* ``decision`` is ``{by, why}``: ``deterministic`` with the reason when no Jev
  unit is bound or it does not answer, ``jev`` when the bound unit named every
  pick. Each question to it holds at most 8 options, the best-ranked.
* ``knowledge`` names each cache file that was skipped, model records and
  geometry rows both, with why.
* A coding plan's top rung is sized at 32k per slot (or the model's own
  context, when that is shorter), and its spare card memory becomes slots.
* Hosts that could not be read are listed with why.

The rigs, models and Jev answers are invented; the shipped knowledge is read.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import availability, cli, decision, planner
from mcgyvr import recommend as recommend_module
from mcgyvr import scan as scan_module
from mcgyvr.availability import AvailabilityVerdict
from mcgyvr.knowledge import geometry as kg
from mcgyvr.knowledge import store as ks
from tests.test_recommend import JEV_CONFIG, RecordedSsh, fake_header

RIGS = ("rig-a.invalid", "rig-b.invalid")


def _dense(index: int) -> planner.Model:
    """An invented dense model, small enough that a dozen fit the invented card."""
    file = f"invented-dense-{index:02d}-Q4_K_M.gguf"
    size = 1_000_000_000 + index * 10_000_000
    row = dict(fake_header(file, size))
    row.update(
        {
            "bytes_experts": 0,
            "bytes_nonexpert": size,
            "placeable_blocks": [],
            "expert_blocks": [],
            "expert_bytes_by_block": {},
            "nextn_blocks": [],
            "n_expert": 0,
            "n_expert_used": 0,
        }
    )
    return planner.Model(
        model_id=f"invented-org/dense-{index:02d}",
        quant="Q4_K_M",
        file=file,
        size_bytes=size,
        context_length=32768,
        geometry=row,
        repo=f"invented-org/dense-{index:02d}-GGUF",
        revision="2" * 40,
        sha256=f"{index:064x}",
        present=None,
        sources={
            "size": "hub-api:invented",
            "context": "hub-config:invented",
            "geometry": "gguf-header-range:invented",
        },
    )


class Answers:
    """A stand-in for ``decision.classify``: names each question's first option."""

    def __init__(self) -> None:
        self.questions: list[Mapping[str, Any]] = []

    def __call__(
        self,
        endpoint: Any,
        model: str,
        state: Any,
        questions: Mapping[str, Any],
        *,
        timeout_s: float,
    ) -> decision.Decision:
        self.questions.append(questions)
        answers = {}
        for key, question in questions.items():
            first = next(iter(question.options))
            answers[key] = decision.ChoiceAnswer(
                choice=first, probabilities={first: 1.0}, confidence=1.0
            )
        return decision.Decision(answers=answers)


@pytest.fixture
def rigs(monkeypatch: pytest.MonkeyPatch) -> RecordedSsh:
    ssh = RecordedSsh(*RIGS)
    monkeypatch.setattr(scan_module, "_ssh", ssh)
    return ssh


def _plan(
    capsys: pytest.CaptureFixture[str], *extra: str, use_case: str = "coding"
) -> dict[str, Any]:
    argv = ["recommend", "--use-case", use_case, "--users", "2"]
    for rig in RIGS:
        argv += ["--host", rig]
    code = cli.main([*argv, *extra])
    out = capsys.readouterr().out
    assert code == 0, out
    plan: dict[str, Any] = json.loads(out)
    return plan


def _units(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [unit for rig in plan["rigs"].values() for unit in rig["units"]]


def test_the_plan_is_version_2_with_units_per_rig(
    rigs: RecordedSsh, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _plan(capsys, "--priority", "quality")

    assert plan["schema_version"] == 2
    assert plan["use_case"] == "coding"
    assert plan["priority"] == "quality"
    assert plan["users"] == 2
    assert plan["fleet"]
    assert set(plan["rigs"]) == set(RIGS)
    units = _units(plan)
    assert units
    names = [unit["name"] for unit in units]
    assert len(set(names)) == len(names)
    assert plan["ladder"] == [n for n in plan["ladder"] if n in names]
    assert set(plan["ladder"]) == set(names)
    for rig, laid in plan["rigs"].items():
        measured = laid["measured"]
        assert measured["read_at"]
        assert measured["cards"] and "free_mib" in measured["cards"][0]
        for unit in laid["units"]:
            assert re.fullmatch(
                rf"{re.escape(rig)}-[a-z0-9._-]+-{unit['port']}", unit["name"]
            ), unit["name"]


def test_every_unit_says_what_it_is_and_where_its_numbers_came_from(
    rigs: RecordedSsh, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _plan(capsys)

    total = 0
    for unit in _units(plan):
        assert unit["role"] == "always-on"
        assert unit["engine"] == "llama.cpp"
        assert unit["cards"]
        model = unit["model"]
        for key in ("id", "quant", "repo", "revision", "file", "context_length"):
            assert model[key], key
        assert unit["ctx_per_slot"] > 0
        assert unit["slots"] >= 1
        assert unit["kv_cache"]["k"] in ("f16", "q8_0")
        assert isinstance(unit["n_cpu_moe"], int)
        assert unit["speculative"] in ("none", "mtp")
        assert unit["fit"]["why"] and unit["fit"]["vram_gib"] > 0
        assert unit["args"]["--model"].endswith(model["file"])
        download = unit["download"]
        assert download["present"] is False
        assert download["bytes"] > 0 and len(download["sha256"]) == 64
        assert download["to"]
        for key in ("size", "context", "geometry"):
            assert unit["sources"][key], key
        total += download["bytes"]
    assert plan["downloads"]["total_bytes"] == total
    assert sum(plan["downloads"]["by_rig"].values()) == total


def test_a_coding_top_rung_is_sized_at_32k_and_fills_its_card_with_slots(
    rigs: RecordedSsh, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _plan(capsys, "--offline")

    for laid in plan["rigs"].values():
        (top,) = laid["units"]
        assert top["ctx_per_slot"] == min(32768, top["model"]["context_length"])
        assert top["slots"] >= 1
    if any(unit["slots"] > plan["users"] for unit in _units(plan)):
        assert plan["fanout"] == "idle"


def test_ctx_per_slot_overrides_the_use_cases_context(
    rigs: RecordedSsh, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _plan(capsys, "--ctx-per-slot", "4096")
    assert {unit["ctx_per_slot"] for unit in _units(plan)} == {4096}


def test_with_no_jev_bound_the_decision_is_deterministic_and_says_why(
    rigs: RecordedSsh,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    plan = _plan(capsys)
    assert plan["decision"]["by"] == "deterministic"
    assert "jev" in plan["decision"]["why"]
    assert set(plan["decision"]) == {"by", "why"}


def test_a_bound_jev_unit_is_asked_at_most_8_options_per_question(
    rigs: RecordedSsh,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(JEV_CONFIG, encoding="utf-8")
    models = tuple(_dense(index) for index in range(12))
    monkeypatch.setattr(
        recommend_module,
        "load_models",
        lambda: planner.Library(models=models),
    )
    answers = Answers()
    monkeypatch.setattr(decision, "classify", answers)

    def live(endpoint: Any, timeout_s: float = 2.0) -> AvailabilityVerdict:
        return AvailabilityVerdict(
            source="x", live=True, reason="stub", how="stub", elapsed_s=0.0
        )

    monkeypatch.setattr(availability, "probe_endpoint", live)

    plan = _plan(capsys, "--config", str(config))

    assert plan["decision"]["by"] == "jev"
    assert "judge" in plan["decision"]["why"]
    (questions,) = answers.questions
    assert len(questions) == len(RIGS)
    for question in questions.values():
        assert 1 <= len(question.options) <= 8
    for rig, laid in plan["rigs"].items():
        (unit,) = laid["units"]
        (question,) = [q for k, q in questions.items() if rig in k]
        first = next(iter(question.options))
        assert unit["model"]["id"] in first


def test_the_knowledge_names_every_cache_file_it_skipped(
    rigs: RecordedSsh, capsys: pytest.CaptureFixture[str]
) -> None:
    ks.cache_dir().mkdir(parents=True, exist_ok=True)
    broken_record = ks.cache_dir() / "broken-record.json"
    broken_record.write_text("{ not json", encoding="utf-8")
    kg.cache_dir().mkdir(parents=True, exist_ok=True)
    broken_row = kg.cache_dir() / "broken-row.json"
    broken_row.write_text("{ not json", encoding="utf-8")

    plan = _plan(capsys, "--offline")

    skipped = {entry["file"]: entry["why"] for entry in plan["knowledge"]["skipped"]}
    assert set(skipped) == {str(broken_record), str(broken_row)}
    assert all(skipped.values())
    assert plan["knowledge"]["mode"] == "offline"
    assert plan["knowledge"]["oldest_read_at"]


def test_a_rig_that_could_not_be_read_is_listed_with_why(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(scan_module, "_ssh", RecordedSsh(RIGS[0]))

    plan = _plan(capsys)

    assert set(plan["rigs"]) == {RIGS[0]}
    ((down,),) = [[u for u in plan["unreachable"] if u["host"] == RIGS[1]]]
    assert down["why"]
