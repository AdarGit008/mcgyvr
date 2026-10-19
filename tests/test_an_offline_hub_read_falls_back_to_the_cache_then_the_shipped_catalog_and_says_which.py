"""An offline Hub read falls back to the cache, then the catalog, and says which.

Owner, 2026-10-19: the Hub is asked live at setup time; a cache under the
user's data dir answers when it cannot be, and when nothing is cached the
shipped catalog answers. Setup says which of the three answered.

Promises:

* A Hub that does not answer (the suite's own, ``tests/conftest.py``) leaves
  the shipped catalog to answer, kept to the use case, and the answer names
  why the Hub did not.
* A Hub that answered once filed its records in the cache; offline afterwards
  the cache answers, the shipped records beside it.
* ``HF_HUB_OFFLINE`` is obeyed: the Hub is not asked at all.
* A search that answers nothing usable is a Hub that did not answer.
* ``mcgyvr setup`` prints, rig by rig, which of the Hub, the cache or the
  shipped catalog its candidates came from.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from mcgyvr.cli.commands.setup import _setup_placements
from mcgyvr.knowledge import hub
from mcgyvr.knowledge import store as ks
from mcgyvr.scan import Scan
from tests import hub_recorded as hr

RIG = "rig.example"


def _scan() -> dict[str, Scan]:
    return {RIG: Scan.of(host=RIG, vram_mib=24576, ram_gb=64.0, cores=8)}


def _shipped(use_case: str) -> list[Any]:
    return [one for one in ks.shipped() if use_case in one.use_cases]


def test_a_hub_that_does_not_answer_leaves_the_shipped_catalog_to_answer() -> None:
    answer = hub.candidates(hub.CHAT, max_bytes=hr.ROOMIEST)

    assert answer.origin == ks.SHIPPED
    assert list(answer.records) == _shipped(hub.CHAT)
    assert any("did not answer" in why for _what, why in answer.skipped)


def test_after_one_hub_read_the_cache_answers_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with monkeypatch.context() as live:
        hr.install(live)
        read = hub.candidates(hub.CHAT, max_bytes=hr.ROOMIEST, today=hr.DAY)
    assert read.origin == hub.LIVE

    answer = hub.candidates(hub.CHAT, max_bytes=hr.ROOMIEST)

    assert answer.origin == ks.CACHE
    keys = {one.key for one in answer.records}
    assert {one.key for one in read.records} <= keys
    assert {one.key for one in _shipped(hub.CHAT)} <= keys


def test_hf_hub_offline_asks_the_hub_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def never(url: str, *, headers: Mapping[str, str], limit: int) -> bytes:
        raise AssertionError(f"asked the Hub for {url}")

    monkeypatch.setattr(hub, "fetch", never)
    monkeypatch.setenv(hub.OFFLINE_ENV, "1")

    answer = hub.candidates(hub.AGENT, max_bytes=hr.ROOMIEST)

    assert answer.origin == ks.SHIPPED
    assert list(answer.records) == _shipped(hub.AGENT)


def test_a_search_that_answers_nothing_usable_is_a_hub_that_did_not_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = hr.install(monkeypatch)
    transport.bodies[hub.search_url(hub.CODING)] = b"{not json"

    answer = hub.candidates(hub.CODING, max_bytes=hr.ROOMIEST)

    assert answer.origin == ks.SHIPPED
    assert list(answer.records) == _shipped(hub.CODING)


@pytest.mark.parametrize(
    ("where", "said"),
    [
        ("live", "the Hugging Face Hub, read now"),
        ("cache", "the cache of an earlier Hugging Face Hub read"),
        ("shipped", "the catalog shipped with mcgyvr"),
    ],
)
def test_setup_says_where_the_candidates_came_from(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    where: str,
    said: str,
) -> None:
    if where == "cache":
        with monkeypatch.context() as live:
            hr.install(live)
            hub.candidates(hub.CHAT, max_bytes=hr.ROOMIEST, today=hr.DAY)
    if where == "live":
        hr.install(monkeypatch)

    plans = _setup_placements((RIG,), _scan(), "chat")

    assert plans[RIG]["candidates_from"] == where
    out = capsys.readouterr().out
    assert f"{RIG}: the chat candidates came from {said}" in out
