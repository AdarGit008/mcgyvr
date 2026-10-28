"""A use case is offered only the models tagged for it.

Candidates come from the Hugging Face Hub only, and the use
case is told from the Hub's own metadata — tags, pipeline, model naming and
the chat template: coding is the code/coder models, chat the instruct/chat
models, agent the chat models whose template calls tools.

Promises:

* Every shipped record names its use cases, each one a use case of the task
  catalog, and the three coder models are coding and nothing else.
* A use case read without the Hub is answered by the records tagged for it
  alone: coding gets no chat model, chat and agent no coder.
* ``mcgyvr.knowledge.hub.use_cases_of`` classifies the rows the Hub search
  answered (recorded 2026-10-20): a code-named model is coding only, a chat
  model whose template handles ``tools`` is chat and agent, one whose template
  does not is chat only, and a pipeline that is not text is none.
* ``names_code`` reads the words of an id: coder and starcoder are code,
  encoder is not.
* A cached record written before records named use cases keeps the shipped
  record's, so it is not lost to every use case.
"""

from __future__ import annotations

import dataclasses

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.knowledge import hub
from mcgyvr.knowledge import store as ks
from tests import hub_recorded as hr

CODERS = {
    "Qwen/Qwen2.5-Coder-7B-Instruct",
    "Qwen/Qwen2.5-Coder-14B-Instruct",
    "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
}


def _rows() -> dict[str, hub.Listed]:
    url = hub.search_url(hub.CHAT)
    return {one.id: one for one in hub.listed(hr.recorded(url))}


def _uses(one: hub.Listed) -> tuple[str, ...]:
    return hub.use_cases_of(
        one.id,
        one.model_id,
        tags=one.tags,
        pipeline_tag=one.pipeline_tag,
        chat_template=one.chat_template,
    )


def test_every_shipped_record_names_use_cases_the_task_catalog_has() -> None:
    names = {u.name for u in catalog().use_cases}
    for one in ks.shipped():
        assert one.use_cases, f"{one.model_id} names no use case"
        assert set(one.use_cases) <= names & set(hub.USE_CASES)
    coders = {r.model_id: r.use_cases for r in ks.shipped() if r.model_id in CODERS}
    assert coders == dict.fromkeys(CODERS, ("code",))


@pytest.mark.parametrize("use_case", hub.USE_CASES)
def test_without_the_hub_a_use_case_gets_only_its_own_records(use_case: str) -> None:
    answer = hub.known(use_case)

    assert answer.records
    assert all(use_case in one.use_cases for one in answer.records)
    tagged = [one for one in ks.shipped() if use_case in one.use_cases]
    assert list(answer.records) == tagged
    if use_case == hub.CODE:
        assert {one.model_id for one in answer.records} == CODERS
    else:
        assert not {one.model_id for one in answer.records} & CODERS


def test_the_hubs_rows_are_classified_by_name_template_and_pipeline() -> None:
    rows = _rows()

    assert _uses(rows["unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF"]) == ("code",)
    assert "tools" in (rows["unsloth/Qwen3.5-4B-GGUF"].chat_template or "")
    assert _uses(rows["unsloth/Qwen3.5-4B-GGUF"]) == ("chat", "agent")
    hy = rows["tencent/Hy-MT2-7B-GGUF"]
    assert hy.chat_template and "tools" not in hy.chat_template
    assert not set(hy.tags) & hub.TOOL_TAGS
    assert _uses(hy) == ("chat",)
    assert rows["mudler/locate-anything.cpp-gguf"].pipeline_tag == "object-detection"
    assert _uses(rows["mudler/locate-anything.cpp-gguf"]) == ()


def test_a_tool_tag_makes_a_chat_model_an_agent_without_tools_in_its_template() -> None:
    jirack = _rows()["CMSManhattan/JiRackUltra_1b"]
    assert "tools" not in (jirack.chat_template or "")
    assert "tool-call" in jirack.tags
    assert _uses(jirack) == ("chat", "agent")


def test_a_cached_record_that_names_no_use_case_keeps_the_shipped_ones() -> None:
    shipped = ks.shipped()[0]
    ks.write(dataclasses.replace(shipped, use_cases=()))

    (known,) = [k for k in ks.offline().known if k.record.key == shipped.key]

    assert known.origin == ks.CACHE
    assert known.record.use_cases == shipped.use_cases


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("Qwen/Qwen2.5-Coder-7B-Instruct", True),
        ("bigcode/starcoder2-15b", True),
        ("mistralai/Codestral-22B-v0.1", True),
        ("Qwen/Qwen3-8B", False),
        ("org/text-encoder-small", False),
    ],
)
def test_names_code_reads_the_words_of_an_id(name: str, code: bool) -> None:
    assert hub.names_code(name) is code
