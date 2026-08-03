"""Is anything actually there — per-source liveness, priced at one timeout a run.

:mod:`mcgyvr.pool` resolves the ladder *structurally*: a rung whose source names
a credential the environment does not hold is unusable, and that is knowable
without touching the network. This module answers the other half, which is #22's:
a source that is declared, credentialled and simply **down**.

**Two kinds of source, and they fail in different ways.** A source is an endpoint
and a wire protocol, so the same code reaches both — but reading the results
without keeping them apart is how a classification here goes wrong:

* A **local backend** is a server on hardware the user controls — Ollama,
  llama-server, vLLM, LM Studio, TGI. Typically keyless, on ``localhost`` or a
  LAN address. Its characteristic failures are *the process is not running*
  (connection refused, which returns instantly) and *the machine is off or
  asleep* (no route or no SYN-ACK, which costs the whole timeout). It is also the
  kind that produces the awkward **404**: a small server may implement
  ``/v1/chat/completions`` and never implement ``/v1/models``.
* A **hosted provider** is somebody else's API behind a key. Its characteristic
  failures are *the key is wrong, expired or revoked* (401/403), *the provider is
  having an outage* (5xx), and *this machine has no working internet*
  (timeout). It essentially never 404s at the model listing, because publishing
  one is table stakes for a commercial API.

The distinction is descriptive, not a type: nothing here branches on it, because
nothing reliably tells them apart — a local server can require a key, and a
self-hosted vLLM can sit behind a public hostname. What it does is explain why
the classification below is asymmetric. **The 401 arm is there for hosted
providers and the 404 arm is there for local backends**, and each would look
like an over-reaction if only the other kind existed.

It is also why :attr:`~mcgyvr.pool.Endpoint.credential_env` is reported rather
than assumed: the reason text names the variable when there is one and says that
none is configured when there is not, so the message is actionable for whichever
kind it turns out to be.

Distinct from :mod:`mcgyvr.detect`, which is install-time and local-only: it
sweeps *candidate* default ports (11434, 8080, 8000, 1234, 3000) to find out what
this machine happens to be running. This module probes the sources a config
actually *declares*, local or hosted, and does it per run.

The shape of the problem is a cost problem, not a detection problem. Finding out
that a host is not answering is easy; finding it out once is the work. A ladder
escalates — a task that fails on the cheap rung is retried on the next — so a
dead source that is discovered at dispatch time is discovered again on every
attempt, and each discovery costs a connect timeout. Three rungs on one dead host
is three timeouts for one fact. So:

* **A verdict is cached for the life of an** :class:`Availability`. One instance
  per run; a source is probed at most once, however many rungs it serves and
  however many times they are asked for. The cache has no expiry on purpose — a
  run is short, and a source that comes back mid-run being missed is a better
  failure than a re-probe storm at every escalation.
* **A batch is probed concurrently**, so the wall clock for *n* dead sources is
  one timeout rather than *n*. This is the same trick :mod:`mcgyvr.detect` plays
  at install time, for the same reason.
* **The timeout is short and is not the dispatch timeout.**
  :data:`PROBE_TIMEOUT_S` is seconds where
  :data:`~mcgyvr.runner.GENERATE_TIMEOUT_S` is two minutes. They measure
  different things: a local 7B taking ninety seconds to answer a capped
  generation is healthy, while a host taking ninety seconds to accept a TCP
  connection is not. Reusing the dispatch timeout here would make "is anything
  there" cost as much as asking it something.

**A probe is a question about the source, never a generation.** It reads the
protocol's model-list path, which is free, immediate and side-effect-free. It
deliberately does *not* send a completion to see whether one comes back: that
costs tokens and seconds, and it conflates two failures a caller has to tell
apart — a host that is down and a model that is not loaded. Whether a *model* is
present is :meth:`mcgyvr.detect.Backend.has_model`'s question, asked at install
time against what the backend reports holding.

**Any HTTP answer proves something is listening; the question is whether a
dispatch would work.** That distinction decides the whole classification, and it
is why this is not simply "2xx is up":

* **Transport failure** — refused, DNS failure, timeout — is down. Nothing is
  listening, or nothing is listening fast enough to be worth a dispatch. Both
  kinds land here; only the wall clock differs, since a refused connection to a
  local port is instant where an unreachable host costs the whole budget.
* **401 and 403 are down.** *Chiefly the hosted-provider case*, and the one worth
  stating: the source *is* answering, so a naive reachability check would call it
  live and hand every rung on it to a dispatch that fails identically. A key that
  is wrong, expired or revoked does not improve with retries. Note this is a
  different fault from the one :func:`mcgyvr.pool.source_map` already catches
  structurally — there the variable is *unset*, here it is set and rejected.
* **5xx is down.** The server is there and is telling us it cannot serve. A
  provider outage, most often.
* **404 and 405 are LIVE**, the classification most likely to look like a bug and
  the one that matters most. *Chiefly the local-backend case*: the model-list
  path is optional, and a small OpenAI-compatible server may serve
  ``/v1/chat/completions`` perfectly well while never implementing
  ``/v1/models``. Reading that as down would skip a *working* source — a false
  negative that silently shortens the ladder, which is strictly worse than the
  wasted attempt it would be trying to save. Anything that answered HTTP without
  refusing us on credentials is treated as reachable.

**What this does not do.** It does not retry: one probe, one verdict, and a
source that was down when the run started stays down for that run. It does not
bound concurrency — that is #23's semaphore, which acquires at the same seam. It
does not decide *which* rung a contract goes to, only which rungs are on the
ladder at all; escalation is #24's.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from mcgyvr.pool import Endpoint, PoolError, Protocol

# Short by design, and three orders of magnitude below the dispatch timeout: this
# bounds "did anything accept a connection and answer", not "did a model finish
# thinking". A local host that cannot answer a model list in this long is not
# going to serve a generation.
PROBE_TIMEOUT_S = 2.0

# The free, side-effect-free listing each protocol offers. Chosen over a
# generation for the reason in the module docstring, and over a bare TCP connect
# because a connect proves a socket is open, not that an HTTP server is behind
# it.
_LIST_PATH: dict[Protocol, str] = {
    Protocol.OLLAMA: "/api/tags",
    Protocol.OPENAI: "/v1/models",
}

# Statuses that mean "answering, but a dispatch would fail the same way every
# time". Everything else that answered HTTP at all is read as reachable — see
# the docstring on why 404 must not be in here.
_CREDENTIAL_REFUSED = frozenset({401, 403})


@dataclass(frozen=True)
class Verdict:
    """What one probe found, and how it found it.

    ``reason`` is written to be read by whoever sees a shortened ladder, because
    it becomes :attr:`mcgyvr.pool.Skipped.reason` verbatim. ``how`` follows
    :mod:`mcgyvr.detect`'s rule that a detected fact carries its provenance: a
    verdict with no account of how it was reached is indistinguishable from a
    guess, and this one shortens a ladder.
    """

    source: str
    live: bool
    reason: str
    how: str
    elapsed_s: float


ProbeFn = Callable[[Endpoint, float], Verdict]


class Availability:
    """Per-source liveness for one run, probed at most once per source.

    Construct one per run and pass it to :func:`mcgyvr.pool.source_map`. Holding
    it for longer is the one thing that breaks it: the cache never expires, so a
    long-lived instance would keep reporting a verdict from whenever it first
    looked.

    ``probe`` exists so the classification can be tested without a network and so
    a caller with its own transport can supply one; the default is
    :func:`probe_endpoint`.
    """

    def __init__(
        self,
        timeout_s: float = PROBE_TIMEOUT_S,
        probe: ProbeFn | None = None,
    ) -> None:
        if timeout_s <= 0:
            raise ValueError(f"timeout_s must be positive, got {timeout_s}")
        self._timeout_s = timeout_s
        self._probe = probe or probe_endpoint
        self._verdicts: dict[str, Verdict] = {}

    @property
    def verdicts(self) -> Mapping[str, Verdict]:
        """Every verdict reached so far, by source name."""
        return dict(self._verdicts)

    def check(self, endpoint: Endpoint) -> Verdict:
        """The verdict for this endpoint's source, probing only if unseen."""
        cached = self._verdicts.get(endpoint.source)
        if cached is not None:
            return cached
        verdict = self._probe(endpoint, self._timeout_s)
        self._verdicts[endpoint.source] = verdict
        return verdict

    def check_all(self, endpoints: Sequence[Endpoint]) -> Mapping[str, Verdict]:
        """Probe every unseen source at once; return the verdict for each.

        Concurrent because the cost being managed is wall clock: ``n`` dead
        sources probed in sequence is ``n`` timeouts, and probed together is one.
        Sources already in the cache are not re-probed, so calling this twice in
        a run costs nothing the second time.
        """
        wanted = _distinct(endpoints)
        fresh = [e for e in wanted if e.source not in self._verdicts]
        if fresh:
            with ThreadPoolExecutor(max_workers=len(fresh)) as pool:
                for verdict in pool.map(
                    lambda e: self._probe(e, self._timeout_s), fresh
                ):
                    self._verdicts[verdict.source] = verdict
        return {e.source: self._verdicts[e.source] for e in wanted}

    def unavailable(self, endpoints: Sequence[Endpoint]) -> Mapping[str, str]:
        """Which of these sources cannot serve, and why — the pool's seam.

        Deliberately the narrowest thing :func:`mcgyvr.pool.source_map` could
        need: a mapping of source name to reason, holding only the sources that
        are down. :mod:`mcgyvr.pool` therefore learns nothing about probes,
        verdicts or HTTP, and this module stays the only place that knows the
        network exists.
        """
        return {
            source: verdict.reason
            for source, verdict in self.check_all(endpoints).items()
            if not verdict.live
        }


def probe_endpoint(endpoint: Endpoint, timeout_s: float = PROBE_TIMEOUT_S) -> Verdict:
    """Ask one endpoint whether it is there. Never raises.

    Every outcome is a :class:`Verdict`, including the ones that would ordinarily
    be exceptions: a probe that raised would have to be wrapped at every call
    site, and the whole point is that an unreachable source is an ordinary state
    of the world rather than an error in the program.
    """
    path = _LIST_PATH[endpoint.protocol]
    url = endpoint.base_url.rstrip("/") + path
    started = time.monotonic()

    try:
        headers = {}
        key = endpoint.credential()
        if key:
            headers["Authorization"] = f"Bearer {key}"
    except PoolError as exc:
        # The credential vanished between the structural pass and here. Not
        # reachability, but the rung is just as unusable and saying so beats
        # probing with no key and reporting a 401.
        return _verdict(endpoint, False, str(exc), "credential unresolved", started)

    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        return _from_status(endpoint, exc.code, url, started)
    except OSError as exc:
        # URLError and the socket timeout are both OSError, and to a caller they
        # mean one thing: nothing usable answered inside the budget.
        return _verdict(
            endpoint,
            False,
            f"source {endpoint.source!r} did not answer at {endpoint.base_url} "
            f"within {timeout_s:g}s ({exc})",
            f"GET {path} raised {type(exc).__name__} within {timeout_s:g}s",
            started,
        )

    return _from_status(endpoint, status, url, started)


def _from_status(endpoint: Endpoint, status: int, url: str, started: float) -> Verdict:
    """Read an HTTP status as a liveness verdict.

    The asymmetry is deliberate and is argued in the module docstring: a
    credential refusal and a server error are down, and *everything else that
    answered* is live — including 404, because the model-list path is optional
    and a source that does not offer it may still serve generations.
    """
    if status in _CREDENTIAL_REFUSED:
        named = (
            f"${endpoint.credential_env}"
            if endpoint.credential_env
            else "no credential is configured"
        )
        return _verdict(
            endpoint,
            False,
            f"source {endpoint.source!r} answered HTTP {status}: it is reachable "
            f"but refused the credential ({named}). Every rung on it would fail "
            f"the same way",
            f"GET {url} answered {status}",
            started,
        )
    if status >= 500:
        return _verdict(
            endpoint,
            False,
            f"source {endpoint.source!r} answered HTTP {status}: it is reachable "
            f"but reports it cannot serve",
            f"GET {url} answered {status}",
            started,
        )
    if status >= 400:
        return _verdict(
            endpoint,
            True,
            "",
            f"GET {url} answered {status}; read as reachable because the "
            f"model-list path is optional and a dispatch may still succeed",
            started,
        )
    return _verdict(endpoint, True, "", f"GET {url} answered {status}", started)


def _verdict(
    endpoint: Endpoint, live: bool, reason: str, how: str, started: float
) -> Verdict:
    return Verdict(
        source=endpoint.source,
        live=live,
        reason=reason,
        how=how,
        elapsed_s=time.monotonic() - started,
    )


def _distinct(endpoints: Sequence[Endpoint]) -> tuple[Endpoint, ...]:
    """One endpoint per source name, first occurrence winning, order kept.

    A source serving four rungs is one host and one probe. Ordering is preserved
    so a report reads in ladder order rather than in whatever order a set
    iterated.
    """
    seen: dict[str, Endpoint] = {}
    for endpoint in endpoints:
        seen.setdefault(endpoint.source, endpoint)
    return tuple(seen.values())
