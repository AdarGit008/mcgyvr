"""A recorded Hugging Face Hub: answers by URL, from files, and an invented header.

:class:`Recorded` stands where :func:`mcgyvr.knowledge.hub.fetch` stands. It
answers a URL from ``tests/fixtures/hub/`` (the answers recorded on 2026-10-20
and named in ``recorded.json``), answers any file's resolve URL with
:data:`HEADER`, an invented GGUF whose header and tensor table are real GGUF
and whose weights are absent, honours ``Range`` the way the Hub does, and
keeps every request it was asked. A URL it holds no answer for is an HTTP 404.

Nothing here opens a socket.
"""

from __future__ import annotations

import json
import re
import struct
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pytest

from mcgyvr.knowledge import hub
from tests._paths import TESTS

FIXTURES = TESTS / "fixtures" / "hub"
#: The day the answers were recorded, and the day the tests read them on.
DAY = date(2026, 10, 20)
#: The roomiest card a test plans for: 24 GiB, the largest consumer card.
ROOMIEST = 24 << 30
_RANGE = re.compile(r"^bytes=(\d+)-(\d+)$")
#: What the invented header states.
CONTEXT = 32768
KV_HEADS, KEY_LENGTH, BLOCKS = 2, 8, 2


def manifest() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(
        (FIXTURES / "recorded.json").read_text(encoding="utf-8")
    )
    return loaded


def recorded(url: str) -> Any:
    """The recorded answer to `url`, read as JSON."""
    entry = manifest()["responses"][url]
    return json.loads((FIXTURES / entry["file"]).read_text(encoding="utf-8"))


def _string(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def _kv(key: str, value: str | int) -> bytes:
    if isinstance(value, str):
        return _string(key) + struct.pack("<I", 8) + _string(value)
    return _string(key) + struct.pack("<I", 4) + struct.pack("<I", value)


def _tensor(name: str, dims: tuple[int, ...]) -> bytes:
    head = _string(name) + struct.pack("<I", len(dims))
    head += b"".join(struct.pack("<Q", d) for d in dims)
    return head + struct.pack("<I", 1) + struct.pack("<Q", 0)  # F16


def invented_header() -> bytes:
    """An invented two-block model's GGUF header and tensor table."""
    keys: dict[str, str | int] = {
        "general.architecture": "invented",
        "invented.block_count": BLOCKS,
        "invented.context_length": CONTEXT,
        "invented.embedding_length": 64,
        "invented.attention.head_count": 8,
        "invented.attention.head_count_kv": KV_HEADS,
        "invented.attention.key_length": KEY_LENGTH,
        "invented.attention.value_length": KEY_LENGTH,
    }
    tensors = [("token_embd.weight", (64, 100)), ("output.weight", (64, 100))]
    for block in range(BLOCKS):
        tensors.append((f"blk.{block}.attn_q.weight", (64, 64)))
    body = b"GGUF" + struct.pack("<I", 3)
    body += struct.pack("<Q", len(tensors)) + struct.pack("<Q", len(keys))
    body += b"".join(_kv(k, v) for k, v in keys.items())
    body += b"".join(_tensor(n, d) for n, d in tensors)
    return body


#: The bytes one token of context takes in the invented header's f16 cache.
KV_BYTES_PER_TOKEN = BLOCKS * KV_HEADS * KEY_LENGTH * 2 * 2


@dataclass
class Asked:
    """One request: its URL and its headers."""

    url: str
    headers: Mapping[str, str]


@dataclass
class Recorded:
    """A transport that answers from recorded bodies and keeps what it was asked."""

    bodies: dict[str, bytes] = field(default_factory=dict)
    asked: list[Asked] = field(default_factory=list)

    def __post_init__(self) -> None:
        for url, entry in manifest()["responses"].items():
            self.bodies.setdefault(url, (FIXTURES / entry["file"]).read_bytes())

    def __call__(self, url: str, *, headers: Mapping[str, str], limit: int) -> bytes:
        self.asked.append(Asked(url, dict(headers)))
        body = self.bodies.get(url)
        if body is None and "/resolve/" in url:
            body = invented_header()
        if body is None:
            raise hub.HubError(f"{url} answered HTTP 404")
        wanted = headers.get("Range")
        if wanted is not None:
            matched = _RANGE.match(wanted)
            assert matched, f"a Range this server does not read: {wanted!r}"
            body = body[int(matched[1]) : int(matched[2]) + 1]
        if len(body) > limit:
            raise hub.HubError(f"{url} answered more than {limit} bytes")
        return body

    def urls(self) -> list[str]:
        return [one.url for one in self.asked]


def install(monkeypatch: pytest.MonkeyPatch) -> Recorded:
    """Stand a recorded Hub where the suite's offline one stands."""
    transport = Recorded()
    monkeypatch.setattr(hub, "fetch", transport)
    return transport
