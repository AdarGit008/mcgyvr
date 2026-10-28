"""The Hub ranks a use case's candidates by downloads, then likes.

Weights may come from any Hub repository, ranked by
downloads (the Hub's 30-day figure); no leaderboard and no outside score.

Promises, read off the Hub search answers recorded on 2026-10-20
(``tests/fixtures/hub``):

* The search is ranked by downloads, and likes break a tie.
* Chat is answered in that order by the repositories that qualify: the object
  detector and the coder are passed over before they are looked up, and a
  repository that answers nothing is named in what was skipped.
* Agent is the chat models whose template or tags call tools; a chat model
  whose shown template does not is never looked up.
* Coding is answered in rank order by the code models alone.
* A base model is offered once, from its most downloaded repository that
  qualifies: a more downloaded one that answers nothing gives way to it, and a
  less downloaded one is never asked.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from mcgyvr.knowledge import hub
from tests import hub_recorded as hr

CHAT_ORDER = [
    "ornith-ai/Ornith-1.5-9B-GGUF",
    "CMSManhattan/JiRackUltra_1b",
    "unsloth/gemma-4-12b-it-GGUF",
    "unsloth/Qwen3.5-9B-GGUF",
    "unsloth/Qwen3.5-4B-GGUF",
]
CODING_ORDER = [
    "unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF",
    "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
    "Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF",
]


def _repo_asked(transport: hr.Recorded, repo: str) -> bool:
    return hub.repo_url(repo) in transport.urls()


def test_the_search_is_ranked_by_downloads_and_likes_break_a_tie() -> None:
    rows = hub.listed(hr.recorded(hub.search_url(hub.CHAT)))
    ranked = hub.rank(rows)

    assert [one.downloads for one in ranked] == sorted(
        (one.downloads for one in rows), reverse=True
    )
    first = ranked[1]
    tied = dataclasses.replace(first, id="invented-org/tied", likes=first.likes + 1)
    assert hub.rank([first, tied]) == (tied, first)


def test_chat_is_answered_in_rank_order_by_the_repositories_that_qualify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = hr.install(monkeypatch)

    answer = hub.candidates(hub.CHAT, max_bytes=hr.ROOMIEST, today=hr.DAY)

    assert answer.origin == hub.LIVE
    assert [one.weights.repo for one in answer.records if one.weights] == CHAT_ORDER
    assert all(hub.CHAT in one.use_cases for one in answer.records)
    assert not _repo_asked(transport, "mudler/locate-anything.cpp-gguf")
    assert not _repo_asked(transport, "unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF")
    assert _repo_asked(transport, "tencent/Hy-MT2-7B-GGUF")
    assert any(what == "tencent/Hy-MT2-7B-GGUF" for what, _why in answer.skipped)


def test_agent_is_the_chat_models_that_call_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = hr.install(monkeypatch)

    answer = hub.candidates(hub.AGENT, max_bytes=hr.ROOMIEST, today=hr.DAY)

    assert [one.weights.repo for one in answer.records if one.weights] == CHAT_ORDER
    assert all(one.use_cases == ("chat", "agent") for one in answer.records)
    assert not _repo_asked(transport, "tencent/Hy-MT2-7B-GGUF")


def test_coding_is_answered_in_rank_order_by_the_code_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hr.install(monkeypatch)

    answer = hub.candidates(hub.CODE, max_bytes=hr.ROOMIEST, today=hr.DAY)

    assert [one.weights.repo for one in answer.records if one.weights] == CODING_ORDER
    assert all(one.use_cases == ("code",) for one in answer.records)


def test_a_base_model_is_offered_once_from_its_best_repository_that_qualifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = hr.install(monkeypatch)
    url = hub.search_url(hub.CHAT)
    rows = hr.recorded(url)
    qwen = next(row for row in rows if row["id"] == "unsloth/Qwen3.5-4B-GGUF")
    # Two invented repositories of the same base model: one more downloaded,
    # whose model API answers nothing, and one less downloaded.
    above = {**qwen, "id": "invented-org/Qwen3.5-4B-above"}
    above["downloads"] = qwen["downloads"] + 1
    below = {**qwen, "id": "invented-org/Qwen3.5-4B-below"}
    below["downloads"] = qwen["downloads"] - 1
    transport.bodies[url] = json.dumps([*rows, above, below]).encode()

    answer = hub.candidates(hub.CHAT, max_bytes=hr.ROOMIEST, today=hr.DAY)

    qwens = [one for one in answer.records if one.model_id == "Qwen/Qwen3.5-4B"]
    assert [one.weights.repo for one in qwens if one.weights] == [qwen["id"]]
    assert _repo_asked(transport, above["id"])
    assert not _repo_asked(transport, below["id"])
