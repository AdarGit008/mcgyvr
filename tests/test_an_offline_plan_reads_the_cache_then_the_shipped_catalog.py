"""An offline plan reads the cache, then the shipped catalog.

Owner, 2026-10-07: model knowledge comes from the Hub and the public boards
when a network is there; "every number records its source and date. Offline
falls back to the shipped catalog." The cache under ``$MCGYVR_HOME/knowledge/``
is what an online run left behind, so it is read first.

Promises:

* With no cache, the knowledge is the shipped catalog, model for model.
* A model the cache holds is read from the cache, every other model from the
  shipped catalog, and each says which of the two it came from. A model only
  the cache knows is known too.
* ``mcgyvr recommend``'s catalog (:func:`mcgyvr.recommend.load_catalog`, the
  one seam its plan prices catalog picks from) is that knowledge: a cached
  figure reaches the plan before the shipped one.
* The cache is where ``$MCGYVR_HOME`` puts it.
* A cache file that cannot be read, or that is of another format version, is
  not read: it is named, with why, and the shipped catalog still answers.
* The knowledge says the oldest day any of its numbers was read.
* Reading it offline opens no socket.

Every cached record here is invented; the shipped catalog is read, never
restated.
"""

from __future__ import annotations

import dataclasses
import json
import socket
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import recommend
from mcgyvr.knowledge import record as kr
from mcgyvr.knowledge import store as ks

#: The day the invented cache records say they were read: after anything the
#: shipped catalog can say, so the oldest-day check cannot pass by accident.
CACHED_ON = date(2099, 1, 2)


def _number(value: int | float, source: str) -> kr.Number:
    return kr.Number(value=value, kind="fact", source=source, read_at=CACHED_ON)


def _recached(one: kr.ModelRecord, size: int | float) -> kr.ModelRecord:
    """``one`` as an online run would have cached it, with another size."""
    return dataclasses.replace(
        one, size_bytes=_number(size, "hub-api:invented-recheck@" + "1" * 40)
    )


def _invented() -> kr.ModelRecord:
    shipped = ks.shipped()[0]
    return dataclasses.replace(
        _recached(shipped, 1_234_567_891),
        model_id="invented-org/Only-In-The-Cache",
        quant="Q5_K_M",
        weights=None,
        scores=(),
    )


def test_with_no_cache_the_knowledge_is_the_shipped_catalog() -> None:
    known = ks.offline()
    shipped = ks.shipped()
    assert [k.record for k in known.known] == list(shipped)
    assert {k.origin for k in known.known} == {"shipped"}
    assert known.skipped == ()


def test_a_cached_model_is_read_from_the_cache_and_the_rest_from_the_catalog() -> None:
    shipped = ks.shipped()
    assert len(shipped) > 1, "the check needs a model the cache does not hold"
    first = shipped[0]
    cached = _recached(first, first.size_bytes.value + 1)
    ks.write(cached)

    known = {k.record.key: k for k in ks.offline().known}

    assert known[first.key].origin == "cache"
    assert known[first.key].record == cached
    for other in shipped[1:]:
        assert known[other.key].origin == "shipped"
        assert known[other.key].record == other


def test_a_model_only_the_cache_knows_is_known() -> None:
    invented = _invented()
    ks.write(invented)

    known = {k.record.key: k for k in ks.offline().known}

    assert known[invented.key].origin == "cache"
    assert known[invented.key].record == invented
    assert {s.key for s in ks.shipped()} <= set(known)


def test_the_plans_catalog_reads_the_cache_first() -> None:
    shipped = ks.shipped()
    first, rest = shipped[0], shipped[1:]
    cached = _recached(first, first.size_bytes.value + 1)
    ks.write(cached)

    models = {
        (m["model_id"], m["quant"]): m for m in recommend.load_catalog()["models"]
    }

    assert models[first.key]["size_bytes"] == cached.size_bytes.value
    for other in rest:
        assert models[other.key]["size_bytes"] == other.size_bytes.value
        assert models[other.key]["context_length"] == other.context_length.value
        assert models[other.key]["kv_bytes_per_token"] == other.kv_bytes_per_token.value
        assert models[other.key]["engines"] == list(other.engines)


def test_the_cache_is_where_mcgyvr_home_puts_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    moved = tmp_path / "elsewhere"
    monkeypatch.setenv("MCGYVR_HOME", str(moved))
    written = ks.write(_invented())
    assert written.parent == moved / "knowledge"
    assert ks.cache_dir() == moved / "knowledge"


def _cache_file(name: str, text: str) -> Path:
    folder = ks.cache_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("{ not json", "JSON"),
        (json.dumps({"schema_version": 1, "models": []}), "schema_version"),
        (
            json.dumps(
                {"schema_version": kr.SCHEMA_VERSION, "models": [{"model_id": 7}]}
            ),
            "model_id",
        ),
    ],
)
def test_a_cache_file_that_cannot_be_read_is_named_and_the_catalog_still_answers(
    text: str, why: str
) -> None:
    path = _cache_file("broken.json", text)

    known = ks.offline()

    assert [k.record for k in known.known] == list(ks.shipped())
    ((skipped_path, reason),) = known.skipped
    assert skipped_path == path
    assert why in reason


def test_the_knowledge_says_the_oldest_day_any_number_was_read() -> None:
    shipped_days = {n.read_at for s in ks.shipped() for _name, n in s.numbers()}
    ks.write(_invented())

    known = ks.offline()

    assert known.oldest_read_at == min(shipped_days)
    assert known.oldest_read_at < CACHED_ON


def test_reading_it_offline_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    ks.write(_invented())

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the offline read opened a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert ks.offline().known
