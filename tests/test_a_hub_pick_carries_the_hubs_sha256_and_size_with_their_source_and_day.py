"""A Hub pick carries the Hub's sha256 and size, with their source and day.

Weights may come from any Hub repository, so provenance is
weak, and every file chosen carries the sha256 the Hub itself states for it
(``/api/models/<repo>?blobs=true``); ``serve fetch`` refuses a file without
one. Every number read from the Hub carries its source and the day it was read.

Promises, read off the Hub answers recorded on 2026-10-20:

* A record's weights name the repository at the revision the model API
  answered, one single GGUF file of it at the preferred quantisation, and the
  sha256 and size the API lists for that very file.
* Its size names the model API and that file as its source; its context and KV
  figures name the file's header; its downloads and likes name the search URL
  that listed it; every number is dated the day it was read.
* The records make a fetch list ``serve fetch`` takes.
* A file is picked only when it is single, not a vision projector, of a known
  quantisation, fits the card and has a sha256: Q4_K_M first, then down
  `hub.QUANTS`.
* The header is read over HTTP Range from its first byte, filed in the
  geometry cache, and not read again; a file whose header row ships with the
  package (the shipped Qwen2.5-Coder-7B file, at the revision the Hub still
  answers) is not read at all.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr.knowledge import geometry, hub
from mcgyvr.rig.inventory import kv_bytes_per_token
from mcgyvr.serving import fetchlist
from tests import hub_recorded as hr


def _siblings(repo: str) -> dict[str, dict[str, Any]]:
    raw = hr.recorded(hub.repo_url(repo))
    return {s["rfilename"]: s for s in raw["siblings"]}


def _listed(url: str) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in hr.recorded(url)}


def test_each_record_carries_the_sha256_and_size_the_hub_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hr.install(monkeypatch)
    searched = hub.search_url(hub.CODE)
    listed = _listed(searched)

    answer = hub.candidates(hub.CODE, max_bytes=hr.ROOMIEST, today=hr.DAY)

    assert answer.records
    for one in answer.records:
        weights = one.weights
        assert weights is not None
        repo = hr.recorded(hub.repo_url(weights.repo))
        sibling = _siblings(weights.repo)[weights.file]
        assert weights.revision == repo["sha"]
        assert weights.sha256 == sibling["lfs"]["sha256"]
        assert one.size_bytes.value == sibling["size"]
        at = f"{weights.repo}@{weights.revision}/{weights.file}"
        assert one.size_bytes.source == f"hub-api:{at}"
        assert one.context_length.source == f"gguf-header-range:{at}"
        row = geometry.load().rows[(weights.repo, weights.revision, weights.file)].row
        assert one.context_length.value == row["n_ctx_train"]
        assert one.kv_bytes_per_token.value == kv_bytes_per_token(row, "f16")
        assert one.downloads is not None and one.likes is not None
        assert one.downloads.value == listed[weights.repo]["downloads"]
        assert one.likes.value == listed[weights.repo]["likes"]
        assert one.downloads.source == f"hub-search:{searched}"
        assert {n.read_at for _name, n in one.numbers()} == {hr.DAY}
        assert one.quant == "Q4_K_M"
        assert hub.quant_of(weights.file) == one.quant


def test_the_records_make_a_fetch_list_serve_fetch_takes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hr.install(monkeypatch)
    answer = hub.candidates(hub.CHAT, max_bytes=hr.ROOMIEST, today=hr.DAY)

    wants = fetchlist.parse(fetchlist.dump(fetchlist.from_records(answer.records)))

    assert {(w.repo, w.sha256) for w in wants} == {
        (one.weights.repo, one.weights.sha256)
        for one in answer.records
        if one.weights is not None
    }


def test_a_file_is_picked_single_hashed_known_and_fitting_q4_k_m_first() -> None:
    files = [
        hub.HubFile("m-Q8_0.gguf", 8_000, "a" * 64),
        hub.HubFile("m-Q4_K_M-00001-of-00002.gguf", 2_000, "b" * 64),
        hub.HubFile("mmproj-m-Q4_K_M.gguf", 500, "c" * 64),
        hub.HubFile("m-Q4_K_S.gguf", 3_900, "d" * 64),
        hub.HubFile("m-Q4_K_M.gguf", 4_000, None),
        hub.HubFile("m-UD-Q3_K_XL.gguf", 3_000, "e" * 64),
    ]

    assert hub.pick_file(files, None) == (files[3], "Q4_K_S")
    hashed = [*files, hub.HubFile("m-Q4_K_M.gguf", 4_000, "f" * 64)]
    assert hub.pick_file(hashed, None) == (hashed[-1], "Q4_K_M")
    assert hub.pick_file(hashed, 3_950) == (files[3], "Q4_K_S")
    assert hub.pick_file(hashed, 1_000) is None


def test_the_header_is_read_over_range_filed_and_not_read_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = hr.install(monkeypatch)
    shipped = {one.key for one in geometry.shipped()}

    answer = hub.candidates(hub.CODE, max_bytes=hr.ROOMIEST, today=hr.DAY)

    keys = [
        (one.weights.repo, one.weights.revision, one.weights.file)
        for one in answer.records
        if one.weights is not None
    ]
    unread = [key for key in keys if key not in shipped]
    assert unread and len(unread) < len(keys), "the check needs both kinds"
    reads = [one for one in transport.asked if "/resolve/" in one.url]
    assert [one.url.rsplit("/", 1)[-1] for one in reads] == [k[2] for k in unread]
    assert all(one.headers["Range"].startswith("bytes=0-") for one in reads)
    rows = geometry.load().rows
    for key in unread:
        assert rows[key].origin == "cache"
        assert rows[key].read_at == hr.DAY
        assert rows[key].row["n_ctx_train"] == hr.CONTEXT

    transport.asked.clear()
    again = hub.candidates(hub.CODE, max_bytes=hr.ROOMIEST, today=hr.DAY)

    assert again.records == answer.records
    assert not [one for one in transport.asked if "/resolve/" in one.url]
