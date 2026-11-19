#!/usr/bin/env python3
"""Mechanical check of a table or wave file: is each cell's quote on its page?

  verify_quotes.py FILE...

For every cell with a source and a quote: fetch the source URL once (cached under
``cache/`` beside this script), turn the page into plain text, and look for the
quote. A table quote ("a | b | c") passes when every part is on the page. Writes
``<file>.quotes.json`` next to the input and prints a summary. It judges only
"the words are on the page", not "the words carry the value": that is
``verify_values.py``'s and a reader's job. Fetches public pages only, one request
per URL, with a plain user agent (``curl``) and no key; the hosts in
``scrape.ALLOWED`` refuse a plain request and are read through ``scrape``.
"""

from __future__ import annotations

import hashlib
import html
import json
import pathlib
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
from collections.abc import Iterator
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import scrape

HERE = pathlib.Path(__file__).resolve().parent
CACHE = HERE / "cache"
AGENT = "Mozilla/5.0 (X11; Linux x86_64) hardware-table-quote-check"


def cache_files(url: str) -> tuple[pathlib.Path, pathlib.Path]:
    """Where a URL's page and its status line are cached."""
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    return CACHE / f"{key}.body", CACHE / f"{key}.meta"


def cached(url: str) -> bool:
    """Whether the URL's page was read and is in the cache."""
    meta = cache_files(url)[1]
    return meta.exists() and meta.read_text().startswith("200")


def fetch(url: str) -> tuple[str | None, str]:
    """The page's text and a status word; cached by URL."""
    CACHE.mkdir(exist_ok=True)
    body, meta = cache_files(url)
    via_scraper = urllib.parse.urlparse(url).netloc.lower() in scrape.ALLOWED
    if via_scraper and not cached(url):
        # A host that refuses a plain request is read through a scraping service.
        # Only a page that was read is cached, so a spent daily cap can be retried.
        page, how = scrape.raw_html(url)
        time.sleep(2.0)
        if page is None:
            return None, f"scraper: {how}"
        body.write_text(page)
        meta.write_text(f"200 text/html; via {how[3:]}")
    if not meta.exists():
        done = subprocess.run(
            [
                "curl",
                "-sS",
                "-L",
                "--compressed",
                "-m",
                "30",
                "-A",
                AGENT,
                "-o",
                str(body),
                "-w",
                "%{http_code} %{content_type}",
                url,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        meta.write_text(done.stdout.strip() or f"000 curl: {done.stderr.strip()[:120]}")
        time.sleep(1.0)
    status = meta.read_text().split(" ", 1)
    code = status[0]
    kind = status[1] if len(status) > 1 else ""
    if code != "200" or not body.exists():
        return None, f"http {code}"
    if "pdf" in kind:
        try:
            done = subprocess.run(
                ["pdftotext", "-q", str(body), "-"], capture_output=True, check=False
            )
        except OSError:
            return None, "pdf: no pdftotext on this machine"
        if done.returncode != 0:
            return None, "pdf: pdftotext could not read it"
        return done.stdout.decode("utf-8", "replace"), "ok pdf"
    return body.read_bytes().decode("utf-8", "replace"), "ok"


MARKED = re.compile(r'(?is)<div class="(?:un)?supported" title="([^"]*)">(.*?)</div>')


def marks(raw: str) -> str:
    """techpowerup prints every number format on every card's page and says which
    ones the card supports only in each chip's hover title. The title is what the
    page tells a reader, so it is kept as text, in square brackets after the
    chip: 'INT8 [8-bit Integer: Supported]'."""
    return MARKED.sub(lambda m: f"{m.group(2)} [{html.unescape(m.group(1))}] ", raw)


# Typographic quotes, dashes and the no-break space, written as code points.
_PLAIN = str.maketrans(
    {
        "\u2019": "'",
        "\u2018": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2011": "-",
        "\u00a0": " ",
    }
)


def plain(text: str) -> str:
    """Page or quote as comparable text: no tags, no entities, one kind of space,
    dash, quote."""
    text = marks(text)
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
    # Inline marks are dropped without a space, so a superscript inside a word
    # leaves the word whole; every other tag becomes a space.
    text = re.sub(r"(?is)</?(sup|sub|span|b|i|em|strong|a|font|u)\b[^>]*>", "", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    # A fetch tool's rendering adds a colon after a label and may drop trade
    # marks: neither is part of what the page says, so both sides are compared
    # without them.
    text = re.sub(r"[:®™©†‡*]", " ", text)
    text = text.translate(_PLAIN)
    return re.sub(r"\s+", " ", text).strip().lower()


def cells(node: Any, path: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(node, dict):
        if "v" in node and ("src" in node or "why" in node or "quote" in node):
            yield path, node
            return
        for key, value in node.items():
            yield from cells(value, f"{path}.{key}" if path else key)


def parts(quote: str) -> list[str]:
    """The pieces of a quote that must each be on the page."""
    pieces = [
        p.strip(" \"'.,;:") for p in re.split(r"\s*\|\s*|\s*\.\.\.\s*|\s*…\s*", quote)
    ]
    return [p for p in pieces if len(p) >= 2]


def _verdict(
    cell: dict[str, Any],
    urls: dict[str, str | None],
    pages: dict[str, tuple[str | None, str]],
) -> str:
    url, quote = urls.get(cell.get("src") or ""), cell.get("quote")
    if not url or not quote:
        return "no source or quote"
    # A cell that quotes several pages names the others in "also".
    more = cell.get("also") or []
    wanted = [url] + [urls.get(m) for m in (more if isinstance(more, list) else [more])]
    texts, how = [], "ok"
    for one in [w for w in wanted if w]:
        if one not in pages:
            got, state = fetch(one)
            pages[one] = (plain(got) if got is not None else None, state)
        page_text, state = pages[one]
        if page_text is None:
            how = state
        else:
            texts.append(page_text)
    if not texts:
        return f"page not read ({how})"
    text = " ".join(texts)
    want = [plain(p) for p in parts(quote)]
    missing = [p for p in want if p and p not in text]
    if not missing:
        return "found"
    return "partly" if len(missing) < len(want) else "not found"


def main(path: str) -> None:
    doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    urls = {s["id"]: s.get("url") for s in doc.get("sources", [])}
    pages: dict[str, tuple[str | None, str]] = {}
    out, tally = [], {}
    for row in doc.get("rows", []):
        body = {k: v for k, v in row.items() if k not in ("id", "vendor", "kind")}
        for field, cell in cells(body):
            if cell.get("v") is None:
                continue
            verdict = _verdict(cell, urls, pages)
            tally[verdict] = tally.get(verdict, 0) + 1
            out.append(
                {
                    "id": row.get("id"),
                    "field": field,
                    "verdict": verdict,
                    "url": urls.get(cell.get("src") or ""),
                }
            )
    target = pathlib.Path(path).with_suffix(".quotes.json")
    target.write_text(
        json.dumps({"file": str(path), "tally": tally, "cells": out}, indent=1)
    )
    print(f"{path}: {sum(tally.values())} cells: {tally}")
    unread = {u: h for u, (t, h) in pages.items() if t is None}
    for url, how in sorted(unread.items()):
        print(f"   not read: {how}  {url}")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        main(arg)
