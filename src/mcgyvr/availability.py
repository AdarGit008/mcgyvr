""

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

#
#
#
#
PROBE_TIMEOUT_S = 2.0

#
#
#
#g.
_LIST_BODY_BYTES = 1 << 20

#
#
#
#
_LIST_PATH: dict[Protocol, str] = {
    Protocol.OPENAI: "/v1/models",
}

#
#ee
#
_CREDENTIAL_REFUSED = frozenset({401, 403})


@dataclass(frozen=True)
class AvailabilityVerdict:
    ""

    source: str
    live: bool
    reason: str
    how: str
    elapsed_s: float
    #
    #
    #
    #
    #
    #
    #
    models: tuple[str, ...] | None = None


ProbeFn = Callable[[Endpoint, float], AvailabilityVerdict]


class Availability:
    ""

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
        ""
        return dict(self._verdicts)

    def check(self, endpoint: Endpoint) -> AvailabilityVerdict:
        ""
        cached = self._verdicts.get(endpoint.source)
        if cached is not None:
            return cached
        verdict = self._probe(endpoint, self._timeout_s)
        self._verdicts[endpoint.source] = verdict
        return verdict

    def check_all(
        self, endpoints: Sequence[Endpoint]
    ) -> Mapping[str, AvailabilityVerdict]:
        ""
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
        ""
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
        ""
        return {
            source: verdict.reason
            for source, verdict in self.check_all(endpoints).items()
            if not verdict.live
        }


def probe_endpoint(
    endpoint: Endpoint, timeout_s: float = PROBE_TIMEOUT_S
) -> AvailabilityVerdict:
    ""
    path = _LIST_PATH[endpoint.protocol]
    url = endpoint.base_url.rstrip("/") + path
    started = time.monotonic()

    try:
        headers = {}
        key = endpoint.credential()
        if key:
            headers["Authorization"] = f"Bearer {key}"
    except PoolError as exc:
        #
        #
        #
        return _verdict(endpoint, False, str(exc), "credential unresolved", started)

    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = response.status
            #
            #
            #
            #
            #
            body = response.read(_LIST_BODY_BYTES)
    except urllib.error.HTTPError as exc:
        return _from_status(endpoint, exc.code, url, started)
    except OSError as exc:
        #
        #
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
    ""
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
    ""
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
    ""
    seen: dict[str, Endpoint] = {}
    for endpoint in endpoints:
        seen.setdefault(endpoint.source, endpoint)
    return tuple(seen.values())
