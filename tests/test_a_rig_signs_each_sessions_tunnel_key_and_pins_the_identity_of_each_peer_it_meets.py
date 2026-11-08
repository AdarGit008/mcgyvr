"""A rig signs each session's tunnel key, and pins the identity of each peer it meets.

The hub is the directory a rig learns its peers' WireGuard keys from, so a hub
that lied could put a key of its own between two rigs. Each rig therefore keeps
a long-lived Ed25519 identity key (made at join or first run, kept private like
the rig token), names it in its hello, and signs the tunnel key it answers each
session with; a peer checks that signature and pins the identity key per rig
id. A changed key, a tunnel key the identity did not sign, or a key the hub
left out for a peer once pinned is refused before any tunnel is planned; a peer
from before identity keys (none named, none pinned) is taken as it always was.
The first contact is still the hub's word: that is what the fingerprints are
for.
"""

from __future__ import annotations

import base64
import json
import multiprocessing
import os
import stat
import sys
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mcgyvr import hubwire
from mcgyvr.rig import credentials, identity, protocol, sessionwire
from tests import rig_pool_fakes as fakes
from tests import rig_schema
from tests.rig_pool_fakes import make_pool

PEER_ID = "rig-peer"


def _identity() -> identity.Identity:
    return identity.Identity(Ed25519PrivateKey.generate())


def _signed_peer(
    peer: identity.Identity, *, session_id: str = "s1", **changes: Any
) -> dict[str, Any]:
    body = fakes.tunnel_up_body(session_id=session_id)
    entry = body["peers"][0]
    entry[hubwire.IDENTITY_KEY_FIELD] = peer.public_key
    entry[hubwire.SESSION_KEY_SIG_FIELD] = peer.sign_session_key(
        session_id, fakes.PEER_KEY
    )
    entry.update(changes)
    return body


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "mcgyvr-home"
    monkeypatch.setenv("MCGYVR_HOME", str(folder))
    return folder


# --- the identity key and what it signs -------------------------------------------


def test_the_identity_key_is_made_once_and_kept_private_beside_the_token(
    home: Path,
) -> None:
    assert identity.load() is None
    made = identity.ensure()
    kept = home / identity.IDENTITY_FILE
    assert kept.parent == credentials.path().parent
    if sys.platform != "win32":
        assert stat.S_IMODE(kept.stat().st_mode) == 0o600
    again = identity.ensure()
    assert again.public_key == made.public_key
    assert hubwire.IDENTITY_KEY.fullmatch(made.public_key)
    assert made.fingerprint == hubwire.identity_fingerprint(made.public_key)


#: How many times two first runs race for the identity key.
RACES = 20


def _first_runs(barrier: Any, keys: Any) -> None:
    """One of two rigs' first runs, `RACES` times: each starts at the barrier
    with the parent, which clears the key file between them."""
    for _ in range(RACES):
        barrier.wait()
        keys.put(identity.ensure().public_key)
        barrier.wait()


def test_two_first_runs_at_once_keep_one_identity_key(home: Path) -> None:
    """``rig join`` and a service's ``rig run`` both making the first key: both
    must hold the one kept, or the hub binds a key the rig no longer has."""
    spawn = multiprocessing.get_context("spawn")
    barrier, keys = spawn.Barrier(3, timeout=60), spawn.Queue()
    runs = [spawn.Process(target=_first_runs, args=(barrier, keys)) for _ in "ab"]
    for run in runs:
        run.start()
    try:
        for race in range(RACES):
            (home / identity.IDENTITY_FILE).unlink(missing_ok=True)
            barrier.wait()
            held = {keys.get(timeout=60), keys.get(timeout=60)}
            barrier.wait()
            on_disk = identity.load()
            assert on_disk is not None
            assert held == {on_disk.public_key}, f"race {race}: two keys held"
            staged = [p.name for p in home.iterdir() if "identity" in p.name]
            assert staged == [identity.IDENTITY_FILE], "a staged key was left"
    except BaseException:
        barrier.abort()  # a failed race leaves no run waiting for the next
        raise
    finally:
        for run in runs:
            run.join(timeout=60)
            if run.is_alive():
                run.kill()
    assert [run.exitcode for run in runs] == [0, 0]


@pytest.mark.skipif(sys.platform == "win32", reason="no POSIX modes on Windows")
def test_an_identity_file_others_can_read_is_refused(home: Path) -> None:
    identity.ensure()
    os.chmod(home / identity.IDENTITY_FILE, 0o644)
    with pytest.raises(credentials.CredentialsError, match="read or written by others"):
        identity.load()


def test_an_identity_file_not_as_written_is_refused(home: Path) -> None:
    identity.ensure()
    credentials.write_private(home / identity.IDENTITY_FILE, '{"v": 1}\n')
    with pytest.raises(credentials.CredentialsError, match="not as mcgyvr writes"):
        identity.load()


def test_a_signature_holds_only_for_its_session_and_its_tunnel_key() -> None:
    rig = _identity()
    sig = rig.sign_session_key("s1", fakes.KEY)
    assert hubwire.IDENTITY_SIG.fullmatch(sig)

    def holds(key: str, signature: str, session_id: str, public_key: str) -> bool:
        return identity.verify_session_key(
            key, signature, session_id=session_id, public_key=public_key
        )

    assert holds(rig.public_key, sig, "s1", fakes.KEY)
    assert not holds(rig.public_key, sig, "s2", fakes.KEY)
    assert not holds(rig.public_key, sig, "s1", fakes.PEER_KEY)
    assert not holds(_identity().public_key, sig, "s1", fakes.KEY)
    raw = bytearray(base64.b64decode(sig))
    raw[0] ^= 1
    tampered = base64.b64encode(bytes(raw)).decode()
    assert not holds(rig.public_key, tampered, "s1", fakes.KEY)
    assert not holds(rig.public_key, "not a signature", "s1", fakes.KEY)


def test_a_fingerprint_is_sixteen_base32_characters_in_four_groups() -> None:
    fingerprint = hubwire.identity_fingerprint(_identity().public_key)
    groups = fingerprint.split("-")
    assert [len(g) for g in groups] == [4, 4, 4, 4]
    assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in "".join(groups))
    with pytest.raises(ValueError, match=hubwire.IDENTITY_KEY_FIELD):
        hubwire.identity_fingerprint("not a key")


def test_the_signed_bytes_name_the_context_the_session_and_the_key() -> None:
    message = hubwire.session_key_message("s1", fakes.KEY)
    assert message == hubwire.SESSION_KEY_CONTEXT + f"s1\x00{fakes.KEY}\x00".encode()
    with pytest.raises(ValueError, match="session_id"):
        hubwire.session_key_message("s\x001", fakes.KEY)


# --- the wire: hello, session_prepared, tunnel_up -----------------------------------


def test_a_hello_names_the_identity_key_in_the_wires_field() -> None:
    key = _identity().public_key
    frame = json.loads(
        protocol.hello(
            "h1",
            machine_id="machine-one",
            agent_version="1.0.0",
            ram_total_mb=1024,
            ram_free_mb=None,
            cards=(),
            identity_key=key,
        )
    )
    assert frame["body"][hubwire.IDENTITY_KEY_FIELD] == key
    rig_schema.validate(frame, rig_schema.load(), "#/$defs/AgentMessage")
    old = json.loads(
        protocol.hello(
            "h1",
            machine_id="machine-one",
            agent_version="1.0.0",
            ram_total_mb=1024,
            ram_free_mb=None,
            cards=(),
        )
    )
    assert hubwire.IDENTITY_KEY_FIELD not in old["body"]


def test_a_prepared_session_carries_the_identity_signature_over_its_key(
    tmp_path: Path,
) -> None:
    rig = _identity()
    pool = make_pool(tmp_path, rig_identity=rig)
    try:
        answer = fakes.prepared(pool)
    finally:
        pool.sessions.close()
    body = answer["body"]
    rig_schema.validate(answer, rig_schema.load(), "#/$defs/AgentMessage")
    assert identity.verify_session_key(
        rig.public_key,
        body[hubwire.SESSION_KEY_SIG_FIELD],
        session_id="s1",
        public_key=body["public_key"],
    )


def test_a_rig_without_an_identity_prepares_as_it_always_did(tmp_path: Path) -> None:
    pool = make_pool(tmp_path)
    try:
        answer = fakes.prepared(pool)
    finally:
        pool.sessions.close()
    assert hubwire.SESSION_KEY_SIG_FIELD not in answer["body"]


def test_a_tunnel_up_peer_reads_its_identity_key_and_signature() -> None:
    peer = _identity()
    envelope = protocol.decode(fakes.frame("tunnel_up", "t1", **_signed_peer(peer)))
    read = sessionwire.read_tunnel_up(envelope).peers[0]
    assert read.identity_key == peer.public_key
    assert read.public_key_sig == peer.sign_session_key("s1", fakes.PEER_KEY)
    old = sessionwire.read_tunnel_up(
        protocol.decode(fakes.frame("tunnel_up", "t1", **fakes.tunnel_up_body()))
    ).peers[0]
    assert old.identity_key is None and old.public_key_sig is None


# --- pinning, refusing, rotating -----------------------------------------------------


def _refusal(tmp_path: Path, pins: identity.Pins, body: dict[str, Any]) -> Any:
    pool = make_pool(tmp_path, rig_identity=_identity(), pins=pins)
    try:
        fakes.prepared(pool)
        return pool.ask("tunnel_up", "t1", **body)
    finally:
        pool.sessions.close()


def _taken(tmp_path: Path, pins: identity.Pins, body: dict[str, Any]) -> list[str]:
    "Take the tunnel_up `body`, and return what the rig logged."
    pool = make_pool(tmp_path, rig_identity=_identity(), pins=pins)
    try:
        fakes.prepared(pool)
        assert pool.up("t1", **body)["type"] == "tunnel_report"
    finally:
        pool.sessions.close()
    return pool.logged


def test_a_peer_met_first_is_pinned_and_taken_again_with_the_same_key(
    tmp_path: Path,
) -> None:
    pins = identity.Pins(tmp_path / "pins.json")
    peer = _identity()
    _taken(tmp_path / "one", pins, _signed_peer(peer))
    assert pins.all() == {PEER_ID: peer.public_key}
    if sys.platform != "win32":
        assert stat.S_IMODE(pins.path.stat().st_mode) == 0o600
    _taken(tmp_path / "two", pins, _signed_peer(peer))


def test_a_peer_whose_identity_key_changed_is_refused_and_named(
    tmp_path: Path,
) -> None:
    pins = identity.Pins(tmp_path / "pins.json")
    first, other = _identity(), _identity()
    pins.pin(PEER_ID, first.public_key)
    refused = _refusal(tmp_path, pins, _signed_peer(other))
    assert refused is not None and refused["type"] == "error"
    assert refused["body"]["code"] == sessionwire.SessionCode.TUNNEL_FAILED
    message = refused["body"]["message"]
    assert first.fingerprint in message and other.fingerprint in message
    assert f"mcgyvr rig peers --forget {PEER_ID}" in message
    assert pins.pinned(PEER_ID) == first.public_key


def test_a_tunnel_key_the_identity_did_not_sign_is_refused(tmp_path: Path) -> None:
    pins = identity.Pins(tmp_path / "pins.json")
    peer = _identity()
    forged = _identity().sign_session_key("s1", fakes.PEER_KEY)
    body = _signed_peer(peer, **{hubwire.SESSION_KEY_SIG_FIELD: forged})
    refused = _refusal(tmp_path / "forged", pins, body)
    assert refused is not None and "not signed" in refused["body"]["message"]
    unsigned = _signed_peer(peer)
    del unsigned["peers"][0][hubwire.SESSION_KEY_SIG_FIELD]
    refused = _refusal(tmp_path / "unsigned", pins, unsigned)
    assert refused is not None and "not signed" in refused["body"]["message"]
    assert pins.all() == {}


def test_a_pinned_peer_the_hub_names_no_key_for_is_refused(tmp_path: Path) -> None:
    pins = identity.Pins(tmp_path / "pins.json")
    pins.pin(PEER_ID, _identity().public_key)
    refused = _refusal(tmp_path, pins, fakes.tunnel_up_body())
    assert refused is not None and "sends none" in refused["body"]["message"]


def test_a_peer_from_before_identity_keys_is_taken_and_nothing_pinned(
    tmp_path: Path,
) -> None:
    pins = identity.Pins(tmp_path / "pins.json")
    logged = _taken(tmp_path, pins, fakes.tunnel_up_body())
    assert pins.all() == {}
    # taken, but not without a word: the log says this peer went unchecked
    unchecked = [line for line in logged if "sent no identity key" in line]
    assert unchecked == [
        f"session s1: peer {PEER_ID} sent no identity key (an agent from before "
        "identity keys, or a hub that left it out); taken unpinned"
    ]


def test_a_rotated_peer_is_taken_once_its_pin_is_forgotten(tmp_path: Path) -> None:
    pins = identity.Pins(tmp_path / "pins.json")
    old, new = _identity(), _identity()
    pins.pin(PEER_ID, old.public_key)
    assert _refusal(tmp_path / "before", pins, _signed_peer(new)) is not None
    assert pins.forget(PEER_ID)
    assert not pins.forget(PEER_ID)
    _taken(tmp_path / "after", pins, _signed_peer(new))
    assert pins.pinned(PEER_ID) == new.public_key


def test_pins_states_and_a_full_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pins = identity.Pins(tmp_path / "pins.json")
    key, other = _identity().public_key, _identity().public_key
    assert pins.state("a", key) == "new"
    assert pins.pin("a", key)
    assert pins.state("a", key) == "known"
    assert pins.state("a", other) == "changed"
    monkeypatch.setattr(identity, "MAX_PINS", 1)
    assert not pins.pin("b", key)
    assert pins.all() == {"a": key}


def test_a_pins_file_not_as_written_is_refused(tmp_path: Path) -> None:
    pins = identity.Pins(tmp_path / "pins.json")
    credentials.write_private(pins.path, '{"v": 1, "peers": {"a": "no key"}}\n')
    with pytest.raises(credentials.CredentialsError, match="not as mcgyvr writes"):
        pins.all()
    credentials.write_private(pins.path, "[]\n")
    with pytest.raises(credentials.CredentialsError, match="not as mcgyvr writes"):
        pins.all()


# --- what the owner sees --------------------------------------------------------------


def _cli(*argv: str) -> int:
    from mcgyvr.cli import main

    return main(list(argv))


def test_rig_peers_lists_the_pins_by_fingerprint_and_forgets_one(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _cli("rig", "peers") == 0
    assert "no peer pinned yet" in capsys.readouterr().out
    peer = _identity()
    identity.Pins().pin(PEER_ID, peer.public_key)
    assert _cli("rig", "peers") == 0
    assert f"{PEER_ID}  {peer.fingerprint}" in capsys.readouterr().out
    assert _cli("rig", "peers", "--forget", PEER_ID) == 0
    assert f"forgot peer {PEER_ID}" in capsys.readouterr().out
    assert identity.Pins().all() == {}


def test_rig_status_prints_this_rigs_fingerprint(
    home: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import hardware

    def unread() -> Any:
        raise hardware.HardwareError("not read in this test")

    monkeypatch.setattr(hardware, "read", unread)
    credentials.save(credentials.Credentials(hub="https://hub.example", token="t0k"))
    assert _cli("rig", "status") == 0
    assert "identity: none yet" in capsys.readouterr().out
    made = identity.ensure()
    assert _cli("rig", "status") == 0
    assert f"identity: {made.fingerprint}" in capsys.readouterr().out


def test_pins_that_cannot_be_written_refuse_the_tunnel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pins = identity.Pins(tmp_path / "pins.json")

    def full(self: identity.Pins, peers: dict[str, str]) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(identity.Pins, "_write", full)
    refused = _refusal(tmp_path, pins, _signed_peer(_identity()))
    assert refused is not None
    assert "cannot be written: No space left on device" in refused["body"]["message"]
