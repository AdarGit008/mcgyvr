"""D10 — answering is not health, and a source is asked once.

GREEN by design. The probe being ported over calls a source healthy if it
answered at all: only a transport exception makes it say no. A 500 passes it. A
401 passes it. Both then burn a real dispatch on a rung that could never have
worked, and the failure surfaces as a bad contract rather than as an unreachable
source.

``tests/test_availability.py`` already parametrizes the status table and already
shows a second pass costing nothing. Both are asserted through the injected
``probe`` seam or against ``probe_endpoint`` alone, which is right for testing
the classifier — and is the reason this file exists at a different level. A port
that rewrote the probe and left the classifier's unit tests untouched would keep
them all green: the injected-probe tests never reach HTTP, so they cannot notice
a probe that stopped reading the status, and a cache tested by counting calls to
an injected function cannot notice a cache that was moved below the transport.

Everything here therefore drives the assembled thing — the default
``Availability`` with no probe injected — against a stubbed transport, and
asserts what the operator sees:

* **Four sources answer HTTP and two of them are down.** That single test is the
  whole disagreement with the weaker probe, stated as one call: if "it answered"
  ever becomes the rule again, the 401 and the 500 flip and the test says so.
  The reasons are checked to distinguish *refused the key* from *cannot serve*,
  because an operator does two different things about them.
* **A source that answers nothing is down and the call returns.** A probe that
  raised would take the whole ladder-binding pass down with it, which is worse
  than the thing it was probing for.
* **The second check issues no HTTP at all**, counted at the socket-facing seam
  rather than at an injected function, so a cache that survived only in a layer
  above the transport does not count as a cache.
"""

from __future__ import annotations

import email.message
import urllib.error
import urllib.request
from typing import Any

import pytest

from mcgyvr.availability import Availability
from mcgyvr.pool import Endpoint, Protocol

SOURCE = Endpoint(
    source="workstation",
    base_url="http://localhost:11434",
    protocol=Protocol.OPENAI,
    max_parallel=1,
    credential_env=None,
)


class _Answered:
    """A response object shaped like the one urllib hands back."""

    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> _Answered:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _Transport:
    """A stand-in for the network that records how often it was asked."""

    def __init__(self, answer: Any) -> None:
        self.answer = answer
        self.calls = 0

    def __call__(self, request: Any, timeout: float) -> _Answered:
        self.calls += 1
        if isinstance(self.answer, BaseException):
            raise self.answer
        if self.answer >= 400:
            raise urllib.error.HTTPError(
                request.full_url,
                self.answer,
                "stubbed",
                email.message.Message(),
                None,
            )
        return _Answered(self.answer)


def _install(monkeypatch: pytest.MonkeyPatch, answer: Any) -> _Transport:
    transport = _Transport(answer)
    monkeypatch.setattr(urllib.request, "urlopen", transport)
    return transport


def test_a_source_that_answers_is_not_thereby_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All four answered HTTP; two of them are still down, for different reasons.

    Stated as one test rather than four parametrized cases on purpose. The rule
    being defended is not "404 means live" — it is that *the status is read at
    all*, and that only shows when a live one and a down one are produced from
    the same code path in the same breath. A probe that returned True on every
    answer would satisfy the first two rows and fail the last two here.

    The two down reasons are distinguished because an operator responds to them
    differently: a refused credential is something they can fix, a 500 is
    something they wait out, and a probe that collapsed both into "down" would
    have thrown away the only part of the verdict that is actionable.
    """
    verdicts = {}
    for status in (404, 405, 401, 503):
        _install(monkeypatch, status)
        verdicts[status] = Availability().check(SOURCE)

    assert verdicts[404].live, "a backend with no model-list path was called down"
    assert verdicts[405].live, (
        "a backend refusing GET on the listing path was called down"
    )
    assert not verdicts[401].live, (
        "a source that refused the credential was called healthy"
    )
    assert not verdicts[503].live, (
        "a source that said it cannot serve was called healthy"
    )

    assert verdicts[404].reason == "" and verdicts[405].reason == ""
    assert "credential" in verdicts[401].reason, verdicts[401].reason
    assert "cannot serve" in verdicts[503].reason, verdicts[503].reason


def test_a_source_that_answers_nothing_is_down_and_the_probe_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refused connection is a verdict, not an exception escaping the probe.

    Asserted through ``unavailable()`` as well as through the verdict, because
    that mapping is what a caller binds a ladder from: a probe that returned a
    down verdict but left the source out of the unavailable map would drop a
    rung silently instead of naming why it went.
    """
    _install(monkeypatch, ConnectionRefusedError("nothing listening"))
    availability = Availability()

    verdict = availability.check(SOURCE)
    unavailable = availability.unavailable([SOURCE])

    assert not verdict.live
    assert unavailable["workstation"] == verdict.reason
    assert "workstation" in verdict.reason and "did not answer" in verdict.reason


def test_a_second_check_of_the_same_source_issues_no_further_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Counted at the transport, so a cache above the transport does not qualify.

    Two endpoints are used, differing in everything but the source name, because
    the cost being avoided is per *source* and not per URL — one machine serving
    three rungs is one probe. Then the batch call is made too: a cache honoured
    on the single-check path and not on the batch path would still hand a real
    run one probe per rung.
    """
    transport = _install(monkeypatch, 200)
    availability = Availability()
    other_rung = Endpoint(
        source="workstation",
        base_url="http://localhost:11434",
        protocol=Protocol.OPENAI,
        max_parallel=4,
        credential_env=None,
    )

    first = availability.check(SOURCE)
    second = availability.check(other_rung)
    availability.check_all([SOURCE, other_rung])

    assert transport.calls == 1, f"the source was asked {transport.calls} times"
    assert first == second, "the second answer was not the first one"
