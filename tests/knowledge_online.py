"""A recorded internet for the online model knowledge: answers by URL, from files.

:class:`Recorded` stands where :func:`mcgyvr.knowledge.online.urllib_get`
stands. It answers a URL from ``tests/fixtures/knowledge_online/`` (the
responses recorded on 2026-10-07 and named in ``recorded.json``) or from a
body a test registers, honours a ``Range`` header the way a server does, reads
no more than the caller's ``limit`` plus one byte (as the real transport
does), and keeps every request it was asked, so a test can say what was and
was not fetched. A URL it holds no answer for is an HTTP 404, as it would be.

Nothing here opens a socket.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from mcgyvr.knowledge import online

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "knowledge_online"
_RANGE = re.compile(r"^bytes=(\d+)-(\d+)$")


def recorded_bodies() -> dict[str, bytes]:
    """Every recorded response, by the URL it answered."""
    manifest = json.loads((FIXTURES / "recorded.json").read_text(encoding="utf-8"))
    return {
        url: (FIXTURES / entry["file"]).read_bytes()
        for url, entry in manifest["responses"].items()
    }


@dataclass
class Asked:
    """One request: its URL, its headers, and how many bytes it was answered."""

    url: str
    headers: Mapping[str, str]
    answered: int


@dataclass
class Recorded:
    """A transport that answers from recorded bodies and keeps what it was asked."""

    bodies: dict[str, bytes] = field(default_factory=recorded_bodies)
    ignores_range: bool = False
    asked: list[Asked] = field(default_factory=list)

    def __call__(self, url: str, *, headers: Mapping[str, str], limit: int) -> bytes:
        body = self.bodies.get(url)
        if body is None:
            self.asked.append(Asked(url, dict(headers), 0))
            raise online.OnlineError(f"{url} answered HTTP 404")
        wanted = headers.get("Range")
        if wanted is not None and not self.ignores_range:
            matched = _RANGE.match(wanted)
            assert matched, f"a Range this server does not read: {wanted!r}"
            first, last = int(matched[1]), int(matched[2])
            body = body[first : last + 1]
        answer = body[: limit + 1]
        self.asked.append(Asked(url, dict(headers), len(answer)))
        if len(answer) > limit:
            raise online.OnlineError(
                f"{url} answered more than {limit} bytes; the rest was not read"
            )
        return answer

    def urls(self) -> list[str]:
        return [one.url for one in self.asked]


def never(url: str, *, headers: Mapping[str, str], limit: int) -> bytes:
    """A transport no lookup may call."""
    raise AssertionError(f"looked up {url} online")
