"""What is safe to quote to an operator, and to another user.

One shape of credential is removed here: the userinfo of a URL, the
``user:token@`` part that a model endpoint's address tends to carry.
``safe_url`` redacts a single URL by parsing it into its parts and rebuilding it
without the userinfo, so an address can still name its host in a message.
``scrub`` redacts the same thing by pattern in free text — a prompt, a reply, an
exception's message, an environment value — where the URL is a fragment of a
larger string and there is nothing to parse.

Neither function alters a URL that has no userinfo, so a caller can compare the
result with its argument to ask whether a credential was present.

The other shape is a host path: what a command printed names the machine it ran
on — its workspace, its interpreter, a home directory. ``relativize`` turns a
path under a directory the caller names (the workspace a check ran in) into the
path relative to it, which is the part another reader can use, and
``scrub_paths`` replaces every absolute path still left with ``REDACTED``. Both
work by pattern on free text, for the same reason ``scrub`` does."""

from __future__ import annotations

import re
import urllib.parse
from collections.abc import Iterable

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


#: A character a path segment is spelled with. Deliberately narrow — no space,
#: quote, bracket, `:` or `,` — so a path ends where the sentence around it goes
#: on: ``File "/x/y.py", line 3`` and ``/x/y.py:7: Error`` keep their tails.
_PATH_CHAR = r"[\w.@+%~-]"

#: Where a path may begin: not straight after a character that would make it
#: the tail of something longer — a relative path, a word, a number, or a URL's
#: ``//``, whose host is an address and not a path on anyone's machine — nor
#: after ``<``, which is a closing tag (``</p>``) in the markup a test compares.
_PATH_START = r"(?<![\w.@+%~/<-])"

#: An absolute path in free text: ``/`` and at least one segment, a
#: home-relative ``~/`` or ``~user/`` one, or a ``file://`` URL to either.
_ABSOLUTE_PATH = re.compile(
    rf"{_PATH_START}(?:file://)?(?:~{_PATH_CHAR}*)?/{_PATH_CHAR}+(?:/{_PATH_CHAR}*)*"
)


def relativize(text: str, roots: Iterable[str]) -> str:
    """``text`` with every path under one of ``roots`` made relative to it.

    ``roots`` are absolute spellings of one directory — a workspace, its resolved
    form, where a container mounts it. ``<root>/pkg/mod.py`` becomes
    ``pkg/mod.py`` and ``<root>`` on its own, or ``<root>/``, becomes ``.``. A
    root is matched only as a whole path, so ``<root>-other/x`` and
    ``/elsewhere<root>`` are left as they are, and the longest spelling is
    tried first. Nothing outside the roots is touched: that is
    ``scrub_paths``'s job.
    """
    spellings = sorted(
        {root.rstrip("/") for root in roots if root.rstrip("/")},
        key=len,
        reverse=True,
    )
    if not spellings:
        return text
    under = re.compile(
        rf"{_PATH_START}(?:{'|'.join(map(re.escape, spellings))})"
        rf"(?:(?P<into>/)(?={_PATH_CHAR})|/?(?!{_PATH_CHAR}|/))"
    )
    return under.sub(lambda m: "" if m.group("into") else ".", text)


def scrub_paths(text: str) -> str:
    """``text`` with every absolute path in it replaced by ``REDACTED``.

    An absolute path is one that names a place on the machine the text was
    written on — ``/opt/...``, ``/tmp/...``, ``~/...``, ``file:///...`` — and a
    reader on another machine can do nothing with it but learn about this one.
    A relative path, a URL's host and path, and the text around a path are
    kept, so ``File "/x/y.py", line 3`` reads ``File "<redacted>", line 3``.
    """
    return _ABSOLUTE_PATH.sub(REDACTED, text)
