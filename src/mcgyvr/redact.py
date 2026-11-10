"""What is safe to quote to an operator, and to another user.

Two shapes of credential are removed here. The first is the userinfo of a URL,
the ``user:token@`` part that a model endpoint's address tends to carry.
``safe_url`` redacts a single URL by parsing it into its parts and rebuilding it
without the userinfo, so an address can still name its host in a message.
``scrub`` redacts the same thing by pattern in free text — a prompt, a reply, an
exception's message, an environment value — where the URL is a fragment of a
larger string and there is nothing to parse. The second is a bare token a model
may echo into that same text: every provider shape of the one shared credential
vocabulary (``credential_shapes.VALUE_SHAPES`` — ``sk-``, ``ghp_``, an AWS id
and the rest), a pasted private key taken whole from its header to its footer,
and a ``Bearer`` authorization token, which carries no prefix of its own and so
is spelled here rather than in the shared module. ``scrub`` blanks each with
``REDACTED`` too, so a key a model quoted back — its body as well as its header —
does not survive into a journal blob, a failure note or a command's environment.
``safe_url`` stays userinfo-only; a bare token is free text's concern, not a
parsed URL's.

``safe_url`` does not alter a URL with no userinfo, and ``scrub`` does not alter
text that holds no credential at all, so a caller can compare the result with
its argument to ask whether a credential was present — the sandbox does exactly
that to drop an environment value or to flag a login file.

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

from mcgyvr.credential_shapes import VALUE_SHAPES, scan_pattern

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

#: A ``Bearer`` authorization token in free text: the scheme word, a run of
#: spaces or tabs — never a newline, so a match cannot swallow the next line —
#: then the token's base64url/JWT run (``.`` and ``~+/=-`` among its characters).
#: The HTTP auth scheme is case-insensitive (``curl`` examples often lower-case
#: it), so the match is too. Unlike the provider shapes a Bearer token has no
#: prefix of its own — only this word marks it — so it is not in the shared
#: vocabulary (the gate and the config loader do not want it) and is spelled
#: here, redact's alone. The word and its spacing are captured and kept, only
#: the token blanked, so ``Bearer <redacted>`` still reads as a header.
_BEARER = re.compile(r"\b(Bearer)([ \t]+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE)

#: A pasted private key, header to footer. ``scan_pattern`` is the gate's
#: single-line form and matches the ``-----BEGIN ... -----`` header alone, which
#: would leave the base64 body in the text; this block pass takes the header
#: through the matching ``-----END ... -----`` line, or to the end of the text
#: when the footer was cut, so no key material survives. The header spelling is
#: the one shared shape (reused, not re-written); the footer and the
#: end-of-text fallback are redact's own.
_PRIVATE_KEY_HEADER = next(s.body for s in VALUE_SHAPES if s.code == "private-key")
_PRIVATE_KEY_BLOCK = re.compile(
    _PRIVATE_KEY_HEADER
    + r"[\s\S]*?(?:-----END (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----|\Z)"
)

#: Every other provider credential shape of the one shared vocabulary
#: (:data:`credential_shapes.VALUE_SHAPES`, the private-key header left out since
#: the block pass above covers it), folded into one alternation compiled once —
#: a single search over the text instead of one per shape, which roughly halves
#: the cost on a large blob. Each shape keeps the gate's anchoring
#: (``scan_pattern``: ``\b`` around a word-bounded token), reused here, not
#: re-spelled; the shapes carry no capture groups, so the alternation is flat.
_TOKEN_ALTERNATION = re.compile(
    "|".join(scan_pattern(s).pattern for s in VALUE_SHAPES if s.code != "private-key")
)


def scrub(text: str) -> str:
    """``text`` with every credential in it replaced by ``REDACTED``.

    By pattern, because the credential is a fragment of a larger string: the
    userinfo of every URL; a ``Bearer`` token (its word and spacing kept, its
    value blanked); a pasted private key from header to footer; then every
    provider token shape of the shared vocabulary (``sk-``, ``ghp_``, an AWS id
    and the rest) in one folded pass. Everything else — the rest of each URL,
    the text around a token — is passed through, so the string keeps its shape
    and stays readable. Text that holds no credential comes back unchanged,
    which is how callers test for one: a value this had to alter is a value
    holding a secret.
    """
    cleaned = _URL_WITH_USERINFO.sub(rf"\1{REDACTED}@", text)
    cleaned = _BEARER.sub(rf"\1\2{REDACTED}", cleaned)
    cleaned = _PRIVATE_KEY_BLOCK.sub(REDACTED, cleaned)
    cleaned = _TOKEN_ALTERNATION.sub(REDACTED, cleaned)
    return cleaned


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
