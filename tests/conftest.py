"""Fixtures shared by the tests: a home of their own, and no way off the machine.

Every test runs in a fresh home; resolving a name that is not this machine is
refused, the runner's status read is stubbed, and the door's read is refused.
A test that asks for ``home`` also gets a home of its own under its
``tmp_path``. What these fixtures read comes from the package and these tests;
what they write goes into temporary folders (a synthetic session transcript in
each fresh home). The tests hold the shared fixtures to reading nothing
outside the package and the tests in
``tests/test_what_every_test_shares_opens_nothing_outside_the_package_and_the_tests.py``.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

import tests.livejournal as lj


@pytest.fixture(autouse=True)
def _own_home_and_session(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every test runs in a HOME of its own, as the session ``claude-pytest``.

    ``mcgyvr run`` journals under ``~/.local/state`` by default and files every
    row under the session that typed it (:mod:`mcgyvr.session`); this test
    process itself runs inside a developer's session, with a real HOME. Left
    alone, a test that drives ``run`` would write into the developer's state
    dir as the developer's own session. So HOME is a fresh directory, the
    session variables the process inherited are cleared, and one synthetic
    Claude session — a transcript that exists, so the resolver is satisfied
    the honest way — stands in. A test about what happens with *no* session
    clears it again (``tests/livejournal.clean_env``). The directory is not
    ``tmp_path``: a test that indexes or lists its own ``tmp_path`` must not
    find a home in it.
    """
    home = tmp_path_factory.mktemp("home")
    project = home / ".claude" / "projects" / "-pytest"
    project.mkdir(parents=True, exist_ok=True)
    (project / "pytest.jsonl").write_text('{"type": "session"}\n', encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    # A developer's shell may export where mcgyvr's config, its config and
    # data folders and the door's run root are, and the tags a run's rows
    # carry; a test that inherited one would load that developer's config or
    # settings, file a fixture's files or run under their folders, or tag its
    # rows as theirs. XDG_STATE_HOME places the data folder when MCGYVR_DATA
    # does not.
    for name in (
        "PI_SESSION_FILE",
        "CLAUDE_CONFIG_DIR",
        "MCGYVR_CONFIG",
        "MCGYVR_RUN_ROOT",
        "MCGYVR_HOME",
        "MCGYVR_DATA",
        "MCGYVR_RUN_TAGS",
        "XDG_STATE_HOME",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "pytest")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A HOME of the test's own, with a synthetic Claude session in it."""
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


#: The only names a test may resolve: this machine, under the spellings a
#: loopback server binds and connects to. Everything else is somebody's rig.
_LOOPBACK = frozenset(
    {
        "",
        "0.0.0.0",
        "127.0.0.1",
        "::",
        "::1",
        "localhost",
        "localhost.localdomain",
    }
)

#: Addresses the internet guarantees route nowhere: RFC 5737's three IPv4
#: documentation blocks and RFC 3849's IPv6 one. A test that wants a *real*
#: transport failure has to reach a socket, and these are the addresses where
#: reaching one costs nobody anything — ``tests/test_runner.py`` dials
#: ``http://192.0.2.1:9`` for exactly that reason. They are the only way to
#: open a socket at something that is not this machine.
_ROUTES_NOWHERE = (
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("2001:db8::/32"),
)


def _is_this_machine_or_nowhere(named: str) -> bool:
    """Whether this name may be resolved: loopback, or an address that is dead
    by standard. Anything else is a machine somebody owns."""
    if named.lower() in _LOOPBACK:
        return True
    try:
        address = ipaddress.ip_address(named)
    except ValueError:
        return False
    return address.is_loopback or any(
        address in block
        for block in _ROUTES_NOWHERE
        if address.version == block.version
    )


class ReachedForAMachineError(RuntimeError):
    """A test asked the resolver for a name that is not this machine."""


@pytest.fixture(autouse=True)
def _no_test_resolves_a_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test may **name** a rig. It may not **resolve** one.

    Fixtures name serving hosts by hostname, and a developer's network may
    well answer to such a name. A test that resolved one would send a request
    to a real machine, so a test naming a host is non-hermetic unless something
    prevents it.

    ``tests/test_one_door.py`` guards *spawns* — a test that reaches a machine
    through ``ssh`` — and a name is not a spawn. :func:`_offline_probes` stubs
    the runner's status read by name, which is the same shape of guard one
    layer up and misses every other way out: :mod:`mcgyvr.availability`,
    :mod:`mcgyvr.detect` and :mod:`mcgyvr.runner` each open their own
    ``urllib.request.urlopen``.

    So the guard goes where all of them meet. Resolution itself is refused for
    every name that is not this machine, which catches the socket whoever opens
    it and whatever library they opened it with. It is a **deny-list of the
    whole world** rather than of known hosts on purpose: a guard listing the
    hosts someone knows is a guard the next host is not in, and a hermetic
    suite has no business asking a resolver anything.

    Two ways through, and both are narrow. A test that wants a real transport
    failure uses an address that is dead by standard (:data:`_ROUTES_NOWHERE`),
    which is the only way to open a socket at something that is not this
    machine. And a test that genuinely means to reach a network patches the
    seam back itself — its own ``monkeypatch`` applies later than this one and
    wins, the same escape :func:`_offline_probes` leaves open.

    **What it does not cover**, stated so nobody reads it as more than it is: a
    subprocess resolves in its own interpreter, where this fixture is not.
    ``tests/test_one_door.py`` is the guard on that side, and it is a guard on
    what may spawn rather than on what a spawned thing may reach.
    """
    resolve = socket.getaddrinfo

    def refuse(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        named = "" if host is None else str(host)
        # A URL's userinfo reaches the resolver attached to the host — urllib
        # hands `user:sk-...@127.0.0.1` through whole — so the decision is taken
        # on the machine and the message quotes the machine. This is a sink like
        # any other, and no sink of this project's interpolates a credential
        # (`tests/test_pattern_e_boundaries.py`).
        machine = named.rpartition("@")[2]
        if _is_this_machine_or_nowhere(machine):
            return resolve(host, port, *args, **kwargs)
        raise ReachedForAMachineError(
            f"this test asked the resolver for {machine!r}, which is not this "
            f"machine. A test may name a rig and may not reach one — if it "
            f"means to open a socket, stub the seam it opens it through; if "
            f"it means to reach the network, it has to patch "
            f"`socket.getaddrinfo` back itself and say why"
        )

    monkeypatch.setattr(socket, "getaddrinfo", refuse)


@pytest.fixture(autouse=True)
def _offline_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reaches a serving endpoint unless it says so.

    Stubbed centrally rather than per test, because the property wanted is "the
    suite is offline", and a per-test discipline is one someone forgets. A test
    that wants to control this seam patches it itself afterwards and wins,
    since its ``monkeypatch`` applies later than this one.
    """
    # The runner reads a keyless unit's status page (`/slots` or `/metrics`)
    # before and after every dispatch, to record what the unit had in flight.
    # A test that stubs the dispatch's `_post_json` has stubbed the request,
    # not those reads, so the reads are offline here too.
    import mcgyvr.runner as dispatch_runner

    # BOTH guards, because they catch different failures. Importing above fixes
    # "the module was not loaded yet". `raising=True` here fixes "the module is
    # loaded and the function was renamed" — with `raising=False` a rename would
    # leave the real fetcher live and this fixture would go on reporting that
    # the suite is offline. Two ways to silently become a no-op, two guards.
    monkeypatch.setattr(
        dispatch_runner, "_get_text", lambda *a, **k: None, raising=True
    )


@pytest.fixture(autouse=True)
def _model_knowledge_is_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test looks a model up online unless it says so.

    The model knowledge's refresh asks huggingface.co and the leaderboards
    unless it is asked offline or ``HF_HUB_OFFLINE`` says not to
    (:func:`mcgyvr.knowledge.online.offline_asked`). The suite says it for
    every test, the way :func:`_offline_probes` stubs the status reads, so a
    test of something else never waits on, or asks, the internet. A test of
    the online half clears the variable and injects a transport of its own
    (``tests/knowledge_online.py``); :func:`_no_test_resolves_a_machine` still
    refuses a real one.
    """
    from mcgyvr.knowledge import online

    monkeypatch.setenv(online.OFFLINE_ENV, "1")


@pytest.fixture(autouse=True)
def _no_test_opens_the_doors_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test may not open ``python -m mcgyvr.serving.run read`` against a rig.

    Live admission and ``mcgyvr fleet probe`` read each rig of the live fleet
    through the door (:func:`mcgyvr.fleet.read.spawn_read`), and the door's ssh
    reaches the named machines for real. :func:`_no_test_resolves_a_machine` cannot
    see it: the door is a subprocess, which resolves in its own interpreter. So
    the one place a command spawns it is replaced for every test, and a test
    that means to read a rig substitutes it again with a stand-in of its own.
    """
    from mcgyvr.fleet import read

    def refused(host: str, run_id: str, probe: Sequence[str] = ()) -> int:
        raise ReachedForAMachineError(
            f"a test opened the door's read of {host}; substitute "
            "mcgyvr.fleet.read.spawn_read with a stand-in"
        )

    monkeypatch.setattr(read, "spawn_read", refused)
