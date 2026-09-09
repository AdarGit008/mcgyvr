"""The suite can say ``srv2``. It cannot ask anyone where ``srv2`` is.

``srv1`` and ``srv2`` resolve over Tailscale on the machine this suite is
developed on, and the fixtures name them because that is what the live ladder
is. On 2026-09-09 one run of this suite issued a read-only ``GET /v1/models`` at
srv2 while a residency probe was being built — nothing written, nothing started,
the code backed out the same day. What the revert did not fix is that no guard
existed: ``tests/test_one_door.py`` scans for *spawns*, and a hostname in a
fixture is not a spawn.

``conftest._no_test_resolves_a_machine`` closes it at the resolver, which is
where every way out meets — ``urllib``, ``http.client``, ``socket``, and any
library that ends up in one of them. This file is what keeps the guard honest:
a guard nobody tests is a guard that can become a no-op by a rename, which is
the failure ``_offline_probes`` states in its own docstring and the one
``test_one_door`` found twice on 2026-09-09.
"""

from __future__ import annotations

import socket
import urllib.request

import pytest

from tests.conftest import ReachedForAMachineError

#: The rig the protected sleep/wake specs name, and the endpoint that was
#: actually reached on 2026-09-09.
A_RIG = "srv2"
WHAT_WAS_REACHED = "http://srv2:8001/v1/models"


def test_a_rig_hostname_does_not_resolve() -> None:
    with pytest.raises(ReachedForAMachineError, match=A_RIG):
        socket.getaddrinfo(A_RIG, 8001)


def test_the_request_that_was_actually_made_cannot_be_made() -> None:
    """Through ``urlopen``, because that is what reached srv2 — and it must fail
    loudly rather than as a connection error. ``availability`` and ``detect``
    both read a refused connection as "not serving", so a guard that raised
    ``URLError`` would leave the test passing and the socket unopened by luck.
    """
    with pytest.raises(ReachedForAMachineError):
        urllib.request.urlopen(WHAT_WAS_REACHED, timeout=1)


def test_a_name_nobody_has_is_refused_too() -> None:
    """A deny-list of the whole world, not of the two rigs: a guard listing
    ``srv1`` and ``srv2`` is a guard the third rig is not in."""
    with pytest.raises(ReachedForAMachineError):
        socket.getaddrinfo("some-rig-nobody-has-bought-yet", 80)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_this_machine_still_resolves(host: str) -> None:
    """The guard must not cost a test its own loopback server."""
    assert socket.getaddrinfo(host, 0)


def test_an_address_that_is_dead_by_standard_is_still_reachable() -> None:
    """The suite's existing way of asking for a real transport failure.

    ``test_runner.test_an_unreachable_endpoint_is_a_transport_error`` dials
    ``http://192.0.2.1:9`` because RFC 5737 promises it routes nowhere, and that
    test asserts against a real socket rather than a stub. The guard has to let
    it through, and letting exactly these blocks through is what turns a
    convention into the only door.
    """
    assert socket.getaddrinfo("192.0.2.1", 9, 0, socket.SOCK_STREAM)
    assert socket.getaddrinfo("203.0.113.9", 0)


def test_an_address_that_routes_somewhere_is_refused() -> None:
    """A literal is not an exemption: the blocks above are allowed because they
    are dead, not because they are numbers."""
    with pytest.raises(ReachedForAMachineError):
        socket.getaddrinfo("8.8.8.8", 53)


def test_the_refusal_does_not_quote_a_credential() -> None:
    """This message is a sink, and no sink of this project's quotes a key.

    ``urllib`` hands the resolver the userinfo still attached to the host, so
    the name this fixture is asked about can carry a credential — which is how
    ``test_pattern_e_boundaries`` caught the first draft of the guard writing
    one into its own refusal.
    """
    secret = "sk-canary-3d81f"

    with pytest.raises(ReachedForAMachineError) as refusal:
        socket.getaddrinfo(f"user:{secret}@{A_RIG}", 8001)

    assert secret not in str(refusal.value)
    assert A_RIG in str(refusal.value)


def test_a_credentialed_loopback_url_is_still_this_machine() -> None:
    """And the same stripping decides the other way round.

    What a socket would reach is whatever follows the ``@``, so a credentialed
    loopback URL is loopback and this fixture stands aside. The resolver then
    refuses the name on its own — ``user:...@127.0.0.1`` is not a hostname —
    which is what ``test_pattern_e_boundaries`` drives its real transport
    failure with, and the guard must not have changed it into something else.
    """
    with pytest.raises(socket.gaierror):
        socket.getaddrinfo("user:sk-canary-3d81f@127.0.0.1", 1)


def test_a_test_that_means_to_control_the_seam_still_can(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The escape is the one ``_offline_probes`` leaves open: a test's own
    ``monkeypatch`` applies later than the fixture's and wins, so a test that
    needs a canned answer — or a real resolver, having said why — takes the seam
    back. Stated here so that whoever needs it finds it rather than deleting the
    fixture. Nothing leaves the machine: the replacement is a stub.
    """
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [("canned",)])

    assert socket.getaddrinfo(A_RIG, 8001) == [("canned",)]
