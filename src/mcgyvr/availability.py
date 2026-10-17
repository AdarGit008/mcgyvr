"""Whether an endpoint can take a dispatch, asked before any work is sent.

Each endpoint is asked for its model list once. The status code decides live or
down, and where the list can be read it also says which weights the source holds
right now — a source can answer and still hold other weights than a rung names,
and llama.cpp answers a request naming weights it is not holding from the
weights it is, so such a reply would be another model's with nothing saying so.

A verdict is kept per source, so one source is probed once however many rungs
and roles sit on it, and `check_all` asks a whole config at once rather than one
timeout after another.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from mcgyvr.local_pool import Endpoint, PoolError, Protocol
from mcgyvr.redact import safe_url
from mcgyvr.weights import is_model

# Seconds one probe waits for the model list before the source is called
# silent. The probe asks a question, it does not dispatch, so the wait is short;
# `Availability` and `cooldown` take it as a parameter where a slow machine is
# expected.
PROBE_TIMEOUT_S = 2.0

# Most of a model-list body read from one probe. The list is wanted only for the
# ids in it, and a source that answers something enormous should not hold the
# probe open; a body cut short is not parsable JSON, so `_listed` answers
# `None` and the verdict rests on the status code alone.
_LIST_BODY_BYTES = 1 << 20

# Where each protocol states what it serves, appended to the endpoint's base
# URL. The list is optional, so an endpoint that does not answer this path is
# still read as reachable when its status code allows it.
_LIST_PATH: dict[Protocol, str] = {
    Protocol.OPENAI: "/v1/models",
}

# Statuses saying the source is up but will not take the credential as it is
# configured. Every dispatch to it would fail the same way, so it is called down
# rather than reachable.
_CREDENTIAL_REFUSED = frozenset({401, 403})


@dataclass(frozen=True)
class AvailabilityVerdict:
    """What one probe of one endpoint concluded.

    `live` is the answer a caller acts on: whether a dispatch may be sent at
    all. `reason` says why not, in words fit to show the person holding the
    config, and is empty for a live source. `how` records what the probe did to
    reach the answer, kept apart from `reason` so an audit shows a status code
    even where the reason is a paragraph of advice.
    """

    source: str
    live: bool
    reason: str
    how: str
    elapsed_s: float
    #: The model ids the endpoint listed, when the body could be read and held
    #: at least one. `None` when no list was read: the source is down, the body
    #: did not parse, or the status skipped the body. `not_serving` needs it to
    #: tell a source holding the wrong weights from one whose list says nothing,
    #: and only where a list was read can the absence of a model be held against
    #: the source.
    models: tuple[str, ...] | None = None


ProbeFn = Callable[[Endpoint, float], AvailabilityVerdict]


class Availability:
    """Probes endpoints over the network, remembering each source's verdict.

    A source is asked about once however many rungs and roles sit on it, so a
    config spread thin over a few machines costs those machines' probes and not
    one probe per name. The probe itself is injectable: `cooldown` and the
    tests pass their own and no socket is opened.
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
        self._verdicts: dict[str, AvailabilityVerdict] = {}

    @property
    def verdicts(self) -> Mapping[str, AvailabilityVerdict]:
        """The verdicts gathered so far, keyed by source name.

        A copy, so a caller may read it without disturbing the cache, and so
        asking for it probes nothing new.
        """
        return dict(self._verdicts)

    def check(self, endpoint: Endpoint) -> AvailabilityVerdict:
        """The verdict for `endpoint`, probing only the first time.

        The source name is the key, so a later call about a different endpoint
        on the same source is answered from the cache without a socket.
        """
        cached = self._verdicts.get(endpoint.source)
        if cached is not None:
            return cached
        verdict = self._probe(endpoint, self._timeout_s)
        self._verdicts[endpoint.source] = verdict
        return verdict

    def check_all(
        self, endpoints: Sequence[Endpoint]
    ) -> Mapping[str, AvailabilityVerdict]:
        """The verdict for each source among `endpoints`, keyed by source.

        Sources already answered are not asked again; the rest are probed at
        the same time, one worker each, so a set of silent sources costs one
        timeout rather than one apiece. The result covers the sources
        `endpoints` named, whatever their order.
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

    def not_serving(
        self, bound: Sequence[tuple[Endpoint, str]]
    ) -> Mapping[tuple[str, str], str]:
        """Why each `(endpoint, model)` pair would be answered by other weights.

        Keyed by `(source, model)`, for the pairs a live source is not holding.
        A pair is left out when the source serves the model under any name
        `is_model` accepts. Sources that are down, or whose model list could not
        be read, are left out too: their liveness is `unavailable`'s question,
        and a list that says nothing is no evidence that a model is missing.

        Each reason says what the source does hold and what to do about it,
        because such a dispatch would be taken and answered from the wrong
        weights with nothing reporting it.
        """
        wanted = _distinct([endpoint for endpoint, _ in bound])
        self.check_all(wanted)
        not_there: dict[tuple[str, str], str] = {}
        for endpoint, model in bound:
            verdict = self._verdicts.get(endpoint.source)
            if verdict is None or not verdict.live or not verdict.models:
                continue
            if any(is_model(served, model) for served in verdict.models):
                continue
            not_there[(endpoint.source, model)] = (
                f"source {endpoint.source!r} is serving "
                f"{', '.join(verdict.models)} and not {model!r}. The port "
                f"answers, so a dispatch would be taken — and llama.cpp answers "
                f"a request naming weights it is not holding from the weights it "
                f"is, so the reply would be the wrong model's with nothing "
                f"reporting it. Wake the card that serves {model!r}, or point "
                f"the rung at the model that is up"
            )
        return not_there

    def unavailable(self, endpoints: Sequence[Endpoint]) -> Mapping[str, str]:
        """The sources among `endpoints` that are not live, each mapped to why.

        A source the mapping leaves out is one a dispatch may be sent to.
        """
        return {
            source: verdict.reason
            for source, verdict in self.check_all(endpoints).items()
            if not verdict.live
        }


def probe_endpoint(
    endpoint: Endpoint, timeout_s: float = PROBE_TIMEOUT_S
) -> AvailabilityVerdict:
    """Ask `endpoint` what it serves and read the answer as a verdict.

    The model list is fetched over the network, so this is the only place in
    the module that opens a socket. A credential the endpoint needs and does not
    have is caught here rather than raised: every dispatch would fail the same
    way, so the source is down. Nothing answering within `timeout_s` is down
    too. Otherwise the status code decides, in `_from_status`, with the model
    ids passed along when the body could be read.
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
        # A key that is needed and missing raises here instead of being sent as
        # nothing: the source cannot be dispatched to at all, so the resolution
        # error is the reason and no request is made.
        return _verdict(endpoint, False, str(exc), "credential unresolved", started)

    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = response.status
            # Bounded read: the list is wanted for its ids, not its size, and
            # this is a probe rather than a dispatch. A body cut short does not
            # parse, so `_listed` answers `None` and the verdict stands on the
            # status code: the endpoint answered, which is the question asked.
            body = response.read(_LIST_BODY_BYTES)
    except urllib.error.HTTPError as exc:
        return _from_status(endpoint, exc.code, url, started)
    except OSError as exc:
        # Nothing answered: a refused connection, a name that does not resolve
        # and a socket timing out all arrive here, and none can take a
        # dispatch.
        return _verdict(
            endpoint,
            False,
            f"source {endpoint.source!r} did not answer at "
            f"{safe_url(endpoint.base_url)} "
            f"within {timeout_s:g}s ({exc})",
            f"GET {path} raised {type(exc).__name__} within {timeout_s:g}s",
            started,
        )

    return _from_status(endpoint, status, url, started, models=_listed(body))


def _listed(body: bytes) -> tuple[str, ...] | None:
    """The model ids in a model-list body, or `None` when there are none to read.

    `None` covers every way the body can fail to be a list: not JSON, not a
    JSON object, no `data` array, or an array carrying no string `id`. Rows that
    are malformed are skipped rather than failing the whole list. An empty
    result is also `None`, so a caller never reads "listed nothing" as evidence
    that a model is missing.
    """
    try:
        doc = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return None
    if not isinstance(doc, dict):
        return None
    rows = doc.get("data")
    if not isinstance(rows, list):
        return None
    ids = tuple(
        str(row["id"])
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    )
    return ids or None


def _from_status(
    endpoint: Endpoint,
    status: int,
    url: str,
    started: float,
    models: tuple[str, ...] | None = None,
) -> AvailabilityVerdict:
    """Turn the status code an endpoint answered with into a verdict.

    A refused credential and a server error both mean a dispatch would fail, so
    the source is down with a reason saying which. Any other refusal of the
    model list is not held against the source: the list is optional and a
    dispatch may still succeed, so it counts as reachable. Everything else is
    live, carrying the model ids when they were read.
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
            f"but refused the credential ({named}). Every dispatch to it would "
            f"fail the same way",
            f"GET {safe_url(url)} answered {status}",
            started,
        )
    if status >= 500:
        return _verdict(
            endpoint,
            False,
            f"source {endpoint.source!r} answered HTTP {status}: it is reachable "
            f"but reports it cannot serve",
            f"GET {safe_url(url)} answered {status}",
            started,
        )
    if status >= 400:
        return _verdict(
            endpoint,
            True,
            "",
            f"GET {safe_url(url)} answered {status}; read as reachable because the "
            f"model-list path is optional and a dispatch may still succeed",
            started,
        )
    return _verdict(
        endpoint,
        True,
        "",
        f"GET {safe_url(url)} answered {status}"
        + (f", serving {', '.join(models)}" if models else ""),
        started,
        models=models,
    )


def _verdict(
    endpoint: Endpoint,
    live: bool,
    reason: str,
    how: str,
    started: float,
    models: tuple[str, ...] | None = None,
) -> AvailabilityVerdict:
    return AvailabilityVerdict(
        source=endpoint.source,
        live=live,
        reason=reason,
        how=how,
        elapsed_s=time.monotonic() - started,
        models=models,
    )


def _distinct(endpoints: Sequence[Endpoint]) -> tuple[Endpoint, ...]:
    """One endpoint per source, in the order the sources are first named.

    A source is asked about once, so the first endpoint named for it is the one
    probed; the others differ only in what the rung does with the answer.
    """
    seen: dict[str, Endpoint] = {}
    for endpoint in endpoints:
        seen.setdefault(endpoint.source, endpoint)
    return tuple(seen.values())
