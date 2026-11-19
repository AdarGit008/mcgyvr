#!/usr/bin/env python3
"""Read a page's HTML through Firecrawl, for the hosts that refuse a plain request.

Only hosts in :data:`ALLOWED` are sent to the service. The key, when there is
one, is read from this process's environment under :data:`KEY_NAME`, inside this
process, and is never printed, logged or passed on a command line. What goes
out: the public URL and the key, nothing else. Without a key (or with one that
is out of credits) the service's free tier is used, which takes no key and is
capped per address per day.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

ALLOWED = ("www.techpowerup.com", "techpowerup.com")
#: The environment variable the Firecrawl key is read from.
KEY_NAME = "FIRECRAWL_API_KEY"
ENDPOINT = "https://api.firecrawl.dev/v2/scrape"

_KEY_SPENT = False


def _post(url: str, body: dict[str, Any], headers: dict[str, str]) -> str:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers=headers
    )
    with urllib.request.urlopen(request, timeout=150) as answer:
        return str(answer.read().decode("utf-8", "replace"))


def refused(text: str) -> bool:
    """Whether a service handed back the site's refusal page instead of the page.

    techpowerup's bot check comes with status 200 and the real page's title, so
    it is known by its own words.
    """
    head = text[:600].lower()
    if "access denied" in head or "error 403" in head or "403 - " in head:
        return True
    return "Automated bot check in progress" in text


def raw_html(url: str) -> tuple[str | None, str]:
    """A page's own HTML through Firecrawl, or (None, why).

    With the key from the environment while it has credits; when there is no key,
    or it is out of credits (402), through the free tier (429 when spent).
    """
    global _KEY_SPENT  # one 402 is enough for the whole run
    host = urllib.parse.urlparse(url).netloc.lower()
    if host not in ALLOWED:
        return None, f"host {host} is not one a scraper may be used for"
    body = {"url": url, "formats": ["rawHtml"]}
    key = None if _KEY_SPENT else os.environ.get(KEY_NAME) or None
    tries: list[tuple[str, dict[str, str]]] = []
    if key:
        tries.append(("firecrawl key", {"Authorization": f"Bearer {key}"}))
    tries.append(("firecrawl free tier", {}))
    why = []
    for name, heads in tries:
        try:
            raw = _post(ENDPOINT, body, {**heads, "Content-Type": "application/json"})
            data = json.loads(raw).get("data") or {}
            page = data.get("rawHtml") or ""
            status = (data.get("metadata") or {}).get("statusCode")
            if page and status == 200 and not refused(page):
                return page, f"ok {name}"
            why.append(f"{name}: page status {status}, {len(page)} characters")
        except urllib.error.HTTPError as exc:
            if exc.code == 402 and heads:
                _KEY_SPENT = True
            why.append(f"{name}: http {exc.code}")
        except Exception as exc:  # reported by its type only, never with the key
            why.append(f"{name}: {type(exc).__name__}")
    if not key:
        why.append(f"no key: set {KEY_NAME} to read through a Firecrawl key")
    return None, "; ".join(why)
