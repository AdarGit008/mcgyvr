"""The shipped catalog says what each model serves, and holds the Jev default.

Owner, Round 3 (OQ5): Jev is always opt-in, and when opted in its default
model is Qwen3.5-4B. Round 7 (orchestrator call): the catalog gains
Qwen3.5-4B Q4_K_M and a few chat and agent models, each with its header row.
A plan for a use case places only models that serve it: a coding ladder is
not built from a chat model, nor a chat unit from the Jev model.

Promises:

* Every shipped record says what it serves, from a closed list (the four use
  cases and ``jev``); a record that names anything else is refused by name.
* The Jev default is in the catalog: Qwen3.5-4B at Q4_K_M, serving ``jev``.
* ``chat`` and ``agent`` are each served by at least two shipped models, and
  ``coding`` by the ones it was served by.
* Every shipped record has its file's header row shipped, so each can be
  sized offline.
* A record with no ``serves`` (one only the cache knows) may serve any text
  use case; a refresh keeps what a known record serves.
"""

from __future__ import annotations

import copy
import dataclasses
import json

import pytest

from mcgyvr import planner
from mcgyvr.knowledge import geometry as kg
from mcgyvr.knowledge import record as kr
from mcgyvr.knowledge import store as ks


def test_every_shipped_record_says_what_it_serves_from_the_closed_list() -> None:
    for record in ks.shipped():
        assert record.serves, record.model_id
        assert set(record.serves) <= set(kr.SERVES), record.serves


def test_the_jev_default_is_shipped_and_serves_jev() -> None:
    by_id = {(r.model_id, r.quant): r for r in ks.shipped()}
    jev = by_id[(planner.JEV_DEFAULT, "Q4_K_M")]
    assert "jev" in jev.serves


@pytest.mark.parametrize("use_case", ["chat", "agent"])
def test_chat_and_agent_are_each_served_by_two_models_or_more(use_case: str) -> None:
    serving_it = [r for r in ks.shipped() if use_case in r.serves]
    assert len(serving_it) >= 2


def test_the_coding_models_still_serve_coding() -> None:
    coders = {r.model_id for r in ks.shipped() if "coding" in r.serves}
    assert {
        "Qwen/Qwen2.5-Coder-7B-Instruct",
        "Qwen/Qwen2.5-Coder-14B-Instruct",
        "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
    } <= coders


def test_every_shipped_record_has_its_header_row_shipped() -> None:
    rows = {one.key for one in kg.shipped()}
    for record in ks.shipped():
        assert record.weights is not None
        w = record.weights
        assert (w.repo, w.revision, w.file) in rows, record.model_id


def test_a_record_that_serves_an_unknown_use_is_refused_by_name() -> None:
    raw = json.loads(ks.catalog_path().read_text(encoding="utf-8"))
    entry = copy.deepcopy(raw["models"][0])
    entry["serves"] = ["coding", "knitting"]
    with pytest.raises(kr.KnowledgeError, match="knitting"):
        kr.parse_record(entry, "test", shipped=True)


def test_a_record_with_no_serves_may_serve_any_text_use_case() -> None:
    record = dataclasses.replace(ks.shipped()[0], serves=())
    row = kg.load().of(record.weights)
    assert row is not None
    model = planner.model_from_record(record, row)
    for use_case in ("chat", "agent", "coding"):
        assert planner.serves(model, use_case)
    assert not planner.serves(model, "jev")
