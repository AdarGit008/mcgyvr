"""A model is sized from its header before it is downloaded.

Owner, 2026-10-07: online, model knowledge comes from the Hugging Face Hub API
("sizes, quants, architecture incl. MoE/MTP"), and "every number records its
source and date". Plan section 4.1: the file's own header, read over HTTP
``Range`` before any download, gives the tensor table, so an online pick is
sized by the same law as a file on a rig.

Promises:

* The Hub lookup answers one record per single-file GGUF quantisation of a
  repository: its size and sha256 from the Hub API, its KV width per token and
  recurrent state from the file's header, its context from the base model's
  ``config.json`` (the shipped catalog's source for it) or, when that does not
  answer, from the header. Each number says where it was read, at which
  revision, and the day.
* The header is read with ``Range`` requests only, slice after slice, each
  starting where the last ended, until the tensor table parses, and never past
  a ceiling or the file's size. No byte of a weight is asked for.
* The header row is the one ``ggufscan`` gives for the whole file, so it says
  what a placement needs: which blocks carry experts (an MoE) and which block
  is a multi-token-prediction head (MTP).
* A server that ignores ``Range`` and starts sending the whole file is cut off
  after the slice that was asked for, and the file is named as not read.
* A split file and a vision projector are not records, and each is named with
  why.
* A known model whose repository has moved to a new revision is read again,
  header and all, and filed in the cache at that revision; one whose revision
  has not moved, and whose header row is filed, keeps its numbers and its
  header is not read again.

The repository, its files and its header are invented; the header is real
GGUF whose weights are absent, because nothing here reads a weight.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.knowledge import geometry as kg
from mcgyvr.knowledge import online
from mcgyvr.knowledge import record as kr
from mcgyvr.knowledge import store as ks
from mcgyvr.serving import ggufscan
from tests.sizings import (
    BASE,
    BASE_SHA,
    CONFIG_CONTEXT,
    DAY,
    FILE,
    FILE_SHA256,
    HEADER_CONTEXT,
    REPO,
    SHA,
    SIZE,
    hub,
    invented_header,
)


def whole_file_row(header: bytes, tmp_path: Path) -> dict[str, Any]:
    path = tmp_path / FILE
    path.write_bytes(header)
    row: dict[str, Any] = ggufscan.scan(str(path))  # type: ignore[no-untyped-call]
    assert "error" not in row, row
    return row


def test_the_record_takes_size_from_the_hub_and_geometry_from_the_header() -> None:
    header = invented_header()
    lookup = online.HubLookup(get=hub(header), today=DAY)
    (one,) = lookup(REPO)

    assert one.model_id == BASE
    assert one.quant == "Q4_K_M"
    assert one.weights == kr.Weights(
        repo=REPO, revision=SHA, file=FILE, sha256=FILE_SHA256
    )
    at = f"{REPO}@{SHA}/{FILE}"
    assert one.size_bytes == kr.Number(SIZE, "fact", f"hub-api:{at}", DAY)
    # Three caching layers of 2 heads x 16 wide, K and V, at an f16 cache.
    assert one.kv_bytes_per_token == kr.Number(
        3 * (2 * 16 + 2 * 16) * 2, "fact", f"gguf-header-range:{at}", DAY
    )
    assert one.recurrent_bytes_per_slot == kr.Number(
        0, "fact", f"gguf-header-range:{at}", DAY
    )
    assert one.context_length == kr.Number(
        CONFIG_CONTEXT,
        "fact",
        f"hub-config:{BASE}@{BASE_SHA}/config.json#max_position_embeddings",
        DAY,
    )


def test_with_no_base_config_the_context_is_the_headers() -> None:
    lookup = online.HubLookup(get=hub(invented_header(), base_config=False), today=DAY)
    (one,) = lookup(REPO)
    assert one.context_length == kr.Number(
        HEADER_CONTEXT, "fact", f"gguf-header-range:{REPO}@{SHA}/{FILE}", DAY
    )


def test_the_header_is_read_in_ranges_and_no_weight_is_asked_for() -> None:
    header = invented_header()
    assert len(header) > online.HEADER_FIRST_BYTES, "the header must outgrow a slice"
    server = hub(header)
    online.HubLookup(get=server, today=DAY)(REPO)

    file_url = online.resolve_url(REPO, SHA, FILE)
    reads = [one for one in server.asked if one.url == file_url]
    assert len(reads) >= 2, "the first slice cannot hold this header"
    # Each slice starts where the last ended: no byte is asked for twice.
    held = 0
    for one in reads:
        first, _, last = one.headers["Range"].removeprefix("bytes=").partition("-")
        assert int(first) == held
        assert int(last) + 1 <= online.HEADER_MAX_BYTES
        assert int(last) + 1 < SIZE
        held = int(last) + 1
    assert sum(one.answered for one in reads) < 2 * len(header)
    assert not [u for u in server.urls() if u.endswith(".gguf") and u != file_url]


def test_the_header_row_is_the_whole_files_and_says_moe_and_mtp(tmp_path: Path) -> None:
    header = invented_header()
    lookup = online.HubLookup(get=hub(header), today=DAY)
    (one,) = lookup(REPO)
    row = lookup.header(one)
    assert row is not None

    whole = whole_file_row(header, tmp_path)
    # The row names the file and the size the Hub states, as a scan of the
    # downloaded file would; everything else is the scan's own.
    assert row["file"] == FILE
    assert row["size_bytes"] == SIZE
    assert {k: v for k, v in row.items() if k not in ("file", "size_bytes")} == {
        k: v for k, v in whole.items() if k not in ("file", "size_bytes")
    }
    assert row["placeable_blocks"] == [0, 1], "an MoE: its experts can move"
    assert row["nextn_blocks"] == [2], "an MTP head, never placed as a block"


def test_a_server_that_ignores_range_is_cut_off_and_the_file_named() -> None:
    server = hub(invented_header())
    server.ignores_range = True
    lookup = online.HubLookup(get=server, today=DAY)
    assert lookup(REPO) == ()
    file_url = online.resolve_url(REPO, SHA, FILE)
    reads = [one for one in server.asked if one.url == file_url]
    assert len(reads) == 1
    assert reads[0].answered == online.HEADER_FIRST_BYTES + 1
    (why,) = [why for what, why in lookup.skipped if what.endswith(FILE)]
    assert "more than" in why


def test_a_split_file_and_a_projector_are_named_and_not_read() -> None:
    server = hub(invented_header())
    lookup = online.HubLookup(get=server, today=DAY)
    lookup(REPO)
    skipped = dict(lookup.skipped)
    assert "split" in skipped[f"{REPO}/invented-moe-Q8_0-00001-of-00002.gguf"]
    assert "projector" in skipped[f"{REPO}/mmproj-invented-F16.gguf"]
    assert not [u for u in server.urls() if "Q8_0" in u or "mmproj" in u]


def test_a_quantisation_not_asked_for_is_not_read() -> None:
    server = hub(invented_header())
    lookup = online.HubLookup(get=server, today=DAY, quants=("Q5_K_M",))
    assert lookup(REPO) == ()
    assert not [u for u in server.urls() if u.endswith(".gguf")]


def _known_at(revision: str) -> kr.ModelRecord:
    """The invented model as an earlier run filed it, at ``revision``."""
    (one,) = online.HubLookup(get=hub(invented_header()), today=date(2026, 1, 2))(REPO)
    assert one.weights is not None
    return dataclasses.replace(
        one,
        engines=("llama.cpp", "vllm"),
        weights=dataclasses.replace(one.weights, revision=revision),
    )


@pytest.mark.parametrize("moved", [True, False])
def test_a_known_model_is_read_again_only_when_its_revision_moved(
    moved: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "home"))
    monkeypatch.delenv(online.OFFLINE_ENV, raising=False)
    known = _known_at("0" * 40 if moved else SHA)
    if not moved:
        # Its header was read before: the row is in the cache.
        kg.write(REPO, SHA, FILE, {"file": FILE, "size_bytes": SIZE}, today=DAY)
    server = hub(invented_header())
    done = online.refresh([known], use_case=None, offline=False, get=server, today=DAY)
    assert done.failed == ()
    assert done.written == (ks.cache_file(BASE, "Q4_K_M"),)

    (filed,) = [k.record for k in ks.offline().known if k.origin == ks.CACHE]
    assert filed.weights is not None
    assert filed.weights.revision == SHA
    assert filed.engines == ("llama.cpp", "vllm"), "what serves it is kept"
    file_url = online.resolve_url(REPO, SHA, FILE)
    if moved:
        assert file_url in server.urls()
        assert filed.size_bytes.read_at == DAY
    else:
        assert file_url not in server.urls()
        assert filed == known
