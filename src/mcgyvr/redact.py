"""One definition of "safe to quote", for the strings that reach an operator.

A URL is the project's only structure that can carry a credential inside a
value that is otherwise fine to print. ``https://user:key@host`` appears in
transport errors, probe verdicts, telemetry rows and ``mcgyvr sources``, and
each of those is a sink an operator reads, pastes into an issue, or ships to a
log collector.

:func:`~mcgyvr.config._refuse_userinfo` stops such a URL entering the config at
all, which is the fix that scales: a value that cannot exist cannot be printed.
This module is the second line, for the paths a URL can reach without passing
through the loader — a caller constructing an :class:`~mcgyvr.pool.Endpoint`
directly, a test, a future direct-mode API. Two lines rather than one because
the first is a validator in another module, and a docstring in *this* one that
claims "no message interpolates a credential" should be true of the code under
it rather than of a check three imports away.

Lives at the top level, beside :mod:`mcgyvr.lines`, and for the same reason:
the alternative to one definition is several, and B4 was two definitions of
"line" disagreeing.
"""

from __future__ import annotations

import re
import urllib.parse

#: What a redacted userinfo section is replaced with. Kept recognisable rather
#: than blanked: an operator debugging a 401 needs to see that the URL carried
#: credentials at all, which is often the answer.
REDACTED = "<redacted>"


def safe_url(url: str) -> str:
    """``url`` with any userinfo replaced, ready to put in a message.

    Returns the input unchanged when there is nothing to redact, which is every
    URL the config will load — so this costs a parse on the error path and
    changes nothing an operator normally reads.
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


#: A URL with userinfo, anywhere inside a longer string. Deliberately narrow:
#: this runs over exception text an operator needs to read, and a scrubber that
#: guessed at credential shapes would eat the diagnostic it was meant to
#: preserve. The one shape it does know is the one the project can actually
#: produce — a credentialed URL travelling inside a message.
_URL_WITH_USERINFO = re.compile(r"\b([a-zA-Z][a-zA-Z0-9+.-]*://)([^\s/@]+)@")


def scrub(text: str) -> str:
    """``text`` with any credentialed URL inside it redacted.

    For sinks that quote a string they did not build — telemetry's
    ``error_detail`` is the case this exists for, where the value is an
    arbitrary exception's ``str()`` and the module writing it cannot know what
    produced it. Every deliberate quoting of a URL should use :func:`safe_url`
    on the URL itself instead; this is what catches the ones that did not.
    """
    return _URL_WITH_USERINFO.sub(rf"\1{REDACTED}@", text)
