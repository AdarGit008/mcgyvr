"""What is safe to quote to an operator.

One shape of credential is removed here: the userinfo of a URL, the
``user:token@`` part that a model endpoint's address tends to carry.
``safe_url`` redacts a single URL by parsing it into its parts and rebuilding it
without the userinfo, so an address can still name its host in a message.
``scrub`` redacts the same thing by pattern in free text — a prompt, a reply, an
exception's message, an environment value — where the URL is a fragment of a
larger string and there is nothing to parse.

Neither function alters a URL that has no userinfo, so a caller can compare the
result with its argument to ask whether a credential was present."""

from __future__ import annotations

import re
import urllib.parse

#: What a removed userinfo is replaced with. Bracketed and spelled out rather
#: than emptied, so a reader of a message can see that something was dropped and
#: can still read the host, port and path that were kept.
REDACTED = "<redacted>"


def safe_url(url: str) -> str:
    """``url`` with the userinfo in it replaced by ``REDACTED``.

    The address is split on its last ``@``: everything before it is the
    userinfo and goes, everything after it is host, port, path, query and
    fragment, and those are carried through unchanged, so the result is still
    an address a reader can follow. A URL with no ``@`` in its netloc has no
    userinfo to remove and is returned exactly as given.
    """
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


#: Every ``scheme://userinfo@`` in free text: the scheme is the RFC 3986 shape
#: and must start at a word boundary, and the userinfo runs up to the next ``@``,
#: ``/`` or whitespace, so a match cannot run past the authority into the path.
#: A pattern rather than a parse, because the URL being redacted is a fragment of
#: a sentence, a log line or a JSON string and there is nothing to parse around.
_URL_WITH_USERINFO = re.compile(r"\b([a-zA-Z][a-zA-Z0-9+.-]*://)([^\s/@]+)@")


def scrub(text: str) -> str:
    """``text`` with the userinfo of every URL in it replaced by ``REDACTED``.

    Everything else in the string is passed through, including the rest of each
    URL, so the text keeps its shape and stays readable. Text with no
    credentialed URL comes back unchanged, which is how callers test for one:
    a value this had to alter is a value holding a secret.
    """
    return _URL_WITH_USERINFO.sub(rf"\1{REDACTED}@", text)
