"""A model is sized from its header before it is downloaded.

Owner, 2026-10-07: online, model knowledge comes from the Hugging Face Hub API
("sizes, quants, architecture incl. MoE/MTP"), and "every number records its
source and date". Plan section 4.1: the file's own header, read over HTTP
``Range`` before any download, gives the tensor table, so an online pick is
sized by the same law as a file on a rig.

Promises:

* The Hub lookup answers one record per single-file GGUF quantisation of a
  repository: its size and sha256 from the Hub API, its KV width per token and
  recurrent state from the file's header, its context from the header's
  ``n_ctx_train`` (the checkpoint's declared context; a repacked GGUF serves
  this, not the base model's ``config.json``) or, when the header does not
  state one, from the base model's ``config.json``. Each number says where it
  was read, at which revision, and the day.
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
import json
import struct
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.knowledge import geometry as kg
from mcgyvr.knowledge import online
from mcgyvr.knowledge import record as kr
from mcgyvr.knowledge import store as ks
from mcgyvr.serving import ggufscan
from tests.knowledge_online import Recorded

DAY = date(2026, 10, 7)
REPO = "example-org/Invented-MoE-GGUF"
BASE = "example-org/Invented-MoE"
SHA = "a" * 40
BASE_SHA = "c" * 40
FILE = "invented-moe-Q4_K_M.gguf"
FILE_SHA256 = "b" * 64
#: What the Hub says the file weighs: far more than its header.
SIZE = 9_000_000_000
#: The header's own context, and the base model's config.json's.
HEADER_CONTEXT = 65536
CONFIG_CONTEXT = 32768
F32, F16, Q4_K = 0, 1, 12
STRING, UINT32, ARRAY = 8, 4, 9


def _string(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def _kv(key: str, value: Any) -> bytes:
    if isinstance(value, list):
        items = b"".join(_string(v) for v in value)
        return (
            _string(key)
            + struct.pack("<I", ARRAY)
            + struct.pack("<I", STRING)
            + struct.pack("<Q", len(value))
            + items
        )
    if isinstance(value, str):
        return _string(key) + struct.pack("<I", STRING) + _string(value)
    return _string(key) + struct.pack("<I", UINT32) + struct.pack("<I", value)


def _tensor(name: str, dims: tuple[int, ...], kind: int) -> bytes:
    head = _string(name) + struct.pack("<I", len(dims))
    head += b"".join(struct.pack("<Q", d) for d in dims)
    return head + struct.pack("<I", kind) + struct.pack("<Q", 0)


def invented_header() -> bytes:
    """An MoE of two expert blocks and a grafted MTP head, with a vocabulary
    long enough that the first slice read does not hold the whole header."""
    keys: dict[str, Any] = {
        "general.architecture": "invented",
        "invented.block_count": 3,
        "invented.context_length": HEADER_CONTEXT,
        "invented.embedding_length": 64,
        "invented.attention.head_count": 8,
        "invented.attention.head_count_kv": 2,
        "invented.attention.key_length": 16,
        "invented.attention.value_length": 16,
        "invented.expert_count": 4,
        "invented.expert_used_count": 2,
        "invented.nextn_predict_layers": 1,
        "tokenizer.ggml.tokens": [f"token-{i:06d}-" + "x" * 90 for i in range(30000)],
    }
    tensors: list[tuple[str, tuple[int, ...], int]] = [
        ("token_embd.weight", (64, 30000), F16),
        ("output.weight", (64, 30000), F16),
    ]
    for block in range(3):
        tensors += [
            (f"blk.{block}.attn_q.weight", (64, 64), F16),
            (f"blk.{block}.ffn_up_exps.weight", (64, 256, 4), Q4_K),
        ]
    tensors.append(("blk.2.nextn.eh_proj.weight", (128, 64), F16))
    body = b"GGUF" + struct.pack("<I", 3)
    body += struct.pack("<Q", len(tensors)) + struct.pack("<Q", len(keys))
    body += b"".join(_kv(k, v) for k, v in keys.items())
    body += b"".join(_tensor(n, d, k) for n, d, k in tensors)
    return body


def _sibling(name: str, size: int, sha256: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"rfilename": name, "size": size}
    if sha256 is not None:
        entry["lfs"] = {"sha256": sha256, "size": size}
    return entry


def hub(header: bytes, *, base_config: bool = True) -> Recorded:
    """The invented repository, its base model and the file, as the Hub serves them."""
    api = {
        "id": REPO,
        "sha": SHA,
        "private": False,
        "gated": False,
        "cardData": {"base_model": [BASE]},
        "siblings": [
            _sibling("README.md", 10),
            _sibling(FILE, SIZE, FILE_SHA256),
            _sibling("invented-moe-Q8_0-00001-of-00002.gguf", SIZE, "d" * 64),
            _sibling("invented-moe-Q8_0-00002-of-00002.gguf", SIZE, "e" * 64),
            _sibling("mmproj-invented-F16.gguf", 1000, "f" * 64),
        ],
    }
    bodies = {
        online.api_url(REPO): json.dumps(api).encode(),
        online.resolve_url(REPO, SHA, FILE): header,
    }
    if base_config:
        bodies[online.api_url(BASE)] = json.dumps(
            {"id": BASE, "sha": BASE_SHA}
        ).encode()
        bodies[online.resolve_url(BASE, BASE_SHA, "config.json")] = json.dumps(
            {"max_position_embeddings": CONFIG_CONTEXT}
        ).encode()
    return Recorded(bodies=bodies)


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
        HEADER_CONTEXT,
        "fact",
        f"gguf-header-range:{at}",
        DAY,
    )


def test_with_no_base_config_the_context_is_the_headers() -> None:
    lookup = online.HubLookup(get=hub(invented_header(), base_config=False), today=DAY)
    (one,) = lookup(REPO)
    assert one.context_length == kr.Number(
        HEADER_CONTEXT, "fact", f"gguf-header-range:{REPO}@{SHA}/{FILE}", DAY
    )


def test_the_context_is_the_header_when_it_differs_from_the_base_config() -> None:
    """A repacked GGUF serves the header's ``n_ctx_train``, not ``config.json``."""
    server = hub(invented_header())
    at = f"{REPO}@{SHA}/{FILE}"
    assert online._context(server, BASE, {"n_ctx_train": 131072}, at, DAY) == kr.Number(
        131072, "fact", f"gguf-header-range:{at}", DAY
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
