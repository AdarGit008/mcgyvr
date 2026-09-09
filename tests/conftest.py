"""Fixtures shared across the tests that touch the instrument declaration.

``tools/instruments.json`` is read by five modules and none of them is a
package, so each reaches it by path through the same ``sys.modules`` slot. This
file loads it **first** — a conftest is imported before any test module — so
every rig imported later binds *this* module object, and a fixture that patches
it here is a fixture the rigs can see. Without that ordering guarantee a test
would be patching a second copy of the declaration and wondering why the guard
still fired.
"""

from __future__ import annotations

import importlib.util
import ipaddress
import json
import socket
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent


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
    # A developer's shell may export where mcgyvr's config and the door's run
    # root are; a test that inherited either would load that developer's
    # config, or file a fixture's run under their evidence tree.
    for name in (
        "PI_SESSION_FILE",
        "CLAUDE_CONFIG_DIR",
        "MCGYVR_CONFIG",
        "MCGYVR_RUN_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "pytest")


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
#: ``http://192.0.2.1:9`` for exactly that reason, and says so. The suite
#: already used them by convention; this makes the convention the only way
#: through.
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

    ``srv1`` and ``srv2`` are real machines on this developer's Tailnet, and the
    suite is full of fixtures that name them — the protected sleep/wake specs
    carry ``http://srv2:8001`` because that is what the live ladder is. On
    2026-09-09, while a residency probe was being built, **one run of this suite
    issued a read-only** ``GET /v1/models`` **at srv2.** Nothing was written and
    nothing was started, and the code was backed out the same day; the hazard is
    not the code that was backed out. It is that any test naming a rig by
    hostname is non-hermetic and nothing prevented it.

    ``tests/test_one_door.py`` guards *spawns* — a test that reaches a rig
    through ``ssh`` — and a name is not a spawn. :func:`_offline_probes` stubs
    the two ``tools/bench`` fetchers by name, which is the same shape of guard
    one layer up and misses every other way out: :mod:`mcgyvr.availability`,
    :mod:`mcgyvr.detect` and :mod:`mcgyvr.runner` each open their own
    ``urllib.request.urlopen``.

    So the guard goes where all of them meet. Resolution itself is refused for
    every name that is not this machine, which catches the socket whoever opens
    it and whatever library they opened it with. It is a **deny-list of the
    whole world** rather than of the two rigs on purpose: a guard listing
    ``srv1`` and ``srv2`` is a guard the third rig is not in, and a hermetic
    suite has no business asking a resolver anything.

    Two ways through, and both are narrow. A test that wants a real transport
    failure uses an address that is dead by standard (:data:`_ROUTES_NOWHERE`),
    which is the convention the suite already had and is now the only way to
    open a socket at something that is not this machine. And a test that
    genuinely means to reach a network patches the seam back itself — its own
    ``monkeypatch`` applies later than this one and wins, the same escape
    :func:`_offline_probes` leaves open. There is no test of the second kind
    today.

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
        # (`test_pattern_e_boundaries`, which is what caught it here).
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


def _load_instruments() -> types.ModuleType:
    cached = sys.modules.get("instruments")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "instruments", REPO / "tools" / "instruments.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


instruments = _load_instruments()


@pytest.fixture
def live_instruments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[types.ModuleType]:
    """The real declaration with every set un-retired and drawn from by nobody.

    #240 retired all five local sets, which is most of what the rigs can be
    pointed at — so the machinery that has nothing to do with retirement (run
    identity, resume refusal, the cap a run records) would have no live set to
    exercise itself on. This gives it one, by editing the flags rather than the
    sets: the tests then read as "with a live declaration, resuming onto
    another worker is still refused", and the refusal under the real
    declaration stays a fact about the data instead of a fact about the code.
    """
    doc = json.loads((REPO / "tools" / "instruments.json").read_text(encoding="utf-8"))
    for entry in doc["sets"]:
        entry["retired"] = None
        entry["trainable"] = False
    declaration = tmp_path / "instruments.json"
    declaration.write_text(json.dumps(doc), encoding="utf-8")
    # Two halves, and both are needed. The attribute covers every consumer that
    # already holds this module; the ``sys.modules`` entry covers the ones that
    # load a rig *inside* the test body — the by-path shims take whatever is in
    # the slot, and other test modules put their own copy there at collection
    # time. Patching only the attribute leaves those reading the real
    # declaration and wondering why the guard still fired.
    monkeypatch.setitem(sys.modules, "instruments", instruments)
    monkeypatch.setattr(instruments, "DECLARATION", declaration)
    instruments.declared.cache_clear()
    try:
        yield instruments
    finally:
        instruments.declared.cache_clear()


def _load_by_path(slot: str, path: Path) -> types.ModuleType:
    """A tools module through its shared ``sys.modules`` slot, loading if absent.

    `tools/` is not a package, so every rig reaches its siblings by path through
    one slot; this uses the same slot so a fixture patches the object the rigs
    actually hold.
    """
    cached = sys.modules.get(slot)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(slot, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[slot] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _offline_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reaches a serving endpoint unless it says so.

    Since #286 both rigs' ``record_run`` writes the `observed` block, which
    probes the endpoint — so every existing test that records a run began making
    real outbound requests, silently. Measured: ~344 attempts across two
    previously-offline suites, 80 of them to a fixture host whose URL carries a
    credential, passing only because that host does not resolve here. Behind a
    wildcard resolver the credential leaves the machine; behind a firewall that
    drops rather than refuses, one test takes minutes.

    Stubbed centrally rather than per test, because the property wanted is "the
    suite is offline", and a per-test discipline is one someone forgets. A test
    that wants to control these seams patches them itself afterwards and wins,
    since its ``monkeypatch`` applies later than this one.

    Both JSON fetchers and the text fetcher: `/metrics` is Prometheus text and
    goes through a separate function by design, and patching only the first two
    left every capture making a live call while reading as offline.
    """
    # LOADED, not looked-up. Returning early when the modules were not yet in
    # `sys.modules` made the guarantee "you are offline, unless something loads
    # the capture module after I looked" — and `contract.observed()` does load
    # it lazily, the first time anything calls `scrub`. A protection that
    # silently does not apply is the shape of half the defects this lane found,
    # so the modules are imported here rather than hoped for.
    identity = _load_by_path("bench_identity", REPO / "tools" / "bench" / "identity.py")
    observed = _load_by_path("bench_observed", REPO / "tools" / "bench" / "observed.py")
    # BOTH guards, because they catch different failures. Importing above fixes
    # "the module was not loaded yet". `raising=True` here fixes "the module is
    # loaded and the function was renamed" — with `raising=False` a rename would
    # leave the real fetcher live and this fixture would go on reporting that
    # the suite is offline. Two ways to silently become a no-op, two guards.
    for module, name in (
        (identity, "_get_json"),
        (identity, "_post_json"),
        (observed, "_get_text"),
    ):
        monkeypatch.setattr(module, name, lambda *a, **k: None, raising=True)
