""

from __future__ import annotations

import re
import urllib.parse

#
#
#
REDACTED = "<redacted>"


def safe_url(url: str) -> str:
    ""
    parts = urllib.parse.urlsplit(url)
    _, at, hostport = parts.netloc.rpartition("@")
    if not at:
        return url
    return urllib.parse.urlunsplit(
        (
            parts.scheme,
            f"{REDACTED}@{hostport}",
            parts.path,
            parts.query,
            parts.fragment,
        )
    )


#
#
#
#
#e.
_URL_WITH_USERINFO = re.compile(r"\b([a-zA-Z][a-zA-Z0-9+.-]*://)([^\s/@]+)@")


def scrub(text: str) -> str:
    ""
    return _URL_WITH_USERINFO.sub(rf"\1{REDACTED}@", text)
