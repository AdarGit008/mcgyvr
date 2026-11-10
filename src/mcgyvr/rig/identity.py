"""This rig's identity key, and the identity keys of the peers it has met.

A rig keeps one long-lived Ed25519 keypair (:class:`Identity`), made the first
time it joins or runs and kept beside the rig token in the mcgyvr home folder
(:data:`IDENTITY_FILE`), private to its owner as the token is
(:func:`mcgyvr.rig.credentials.write_private`). It outlives ``rig leave``: it
names the machine, not one join. The public half goes to the hub in every
``hello`` (:data:`mcgyvr.hubwire.IDENTITY_KEY_FIELD`), and the private half
signs the WireGuard key the rig answers each session with
(:func:`mcgyvr.hubwire.session_key_message`).

The hub hands every peer of a session that identity key and that signature
beside the peer's tunnel key. A rig checks the signature, and pins the identity
key of each peer it meets, by the peer's rig id, in :data:`PEERS_FILE`
(:class:`Pins`); :func:`vet_peer` refuses a peer whose key changed, whose tunnel
key is not signed by it, or whose identity key the hub left out once it was
pinned.

What this does and does not protect: a hub that hands out a peer key of its own
is caught for every peer this rig has met before. It is not caught on the first
contact: the hub is still the directory a first identity key comes from. The
key's fingerprint (:func:`mcgyvr.hubwire.identity_fingerprint`) is what people
compare out of band: ``mcgyvr rig status`` prints this rig's, ``mcgyvr rig
peers`` the ones pinned, and the hub shows each rig's on its rig page and in a
session's members.
"""

from __future__ import annotations

import base64
import binascii
import errno
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from mcgyvr import atomic, hubwire
from mcgyvr.fleet import roots
from mcgyvr.rig import credentials
from mcgyvr.rig.credentials import CredentialsError

#: The identity key's file inside the mcgyvr home folder, beside the token's.
IDENTITY_FILE = "rig-identity.json"
#: The pinned peers' file, beside it.
PEERS_FILE = "rig-peers.json"
#: An identity file is under a hundred bytes; anything longer is not one this wrote.
MAX_IDENTITY_BYTES = 1024
#: How many peers are pinned at most; a peer met once the file holds this many
#: is checked but not pinned, and the rig says so.
MAX_PINS = 4096
#: A pins file is under 100 bytes a peer; anything past this is not one this wrote.
MAX_PINS_BYTES = MAX_PINS * 256
#: The version the files are written at.
FILE_VERSION = 1
#: How a peer's identity key stands against the pins: never met, met with this
#: key, or met with another one.
PinState = Literal["new", "known", "changed"]

_AGAIN = "run `mcgyvr rig run` to make a new one"
_LEAKED = (
    "rotate the rig's identity key on the hub's rig page and tell the owners of "
    "the rigs it pooled with"
)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


@dataclass(frozen=True)
class Identity:
    """This rig's identity keypair: the private half signs, the public half
    (:attr:`public_key`, base64) is what peers pin."""

    private: Ed25519PrivateKey

    @property
    def public_key(self) -> str:
        "The public half, as :data:`mcgyvr.hubwire.IDENTITY_KEY` writes it."
        raw = self.private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return _b64(raw)

    @property
    def fingerprint(self) -> str:
        "The public half's fingerprint, for people to compare."
        return hubwire.identity_fingerprint(self.public_key)

    def sign_session_key(self, session_id: str, public_key: str) -> str:
        """The signature, base64, over the tunnel key `public_key` this rig
        answers session `session_id` with."""
        message = hubwire.session_key_message(session_id, public_key)
        return _b64(self.private.sign(message))


def verify_session_key(
    identity_key: str, signature: str, *, session_id: str, public_key: str
) -> bool:
    """Whether `signature` is `identity_key`'s over the tunnel key `public_key`
    of session `session_id`. A key or a signature not in shape is False."""
    if not hubwire.IDENTITY_SIG.fullmatch(signature):
        return False
    try:
        key = Ed25519PublicKey.from_public_bytes(
            hubwire.identity_key_bytes(identity_key)
        )
        key.verify(
            base64.b64decode(signature, validate=True),
            hubwire.session_key_message(session_id, public_key),
        )
    except (ValueError, binascii.Error, InvalidSignature):
        return False
    return True


def path() -> Path:
    "The identity key's file, in the same folder as the rig token's."
    return roots.home() / IDENTITY_FILE


def load() -> Identity | None:
    """This rig's identity, or None when it has none yet.

    The file is read as the token file is
    (:func:`mcgyvr.rig.credentials.read_private`); one that is not as
    :func:`create` writes it raises CredentialsError.
    """
    target = path()
    raw = credentials.read_private(
        target, MAX_IDENTITY_BYTES, again=_AGAIN, leaked=_LEAKED
    )
    if raw is None:
        return None
    unreadable = CredentialsError(
        f"{target} is not as mcgyvr writes it; remove it, run `mcgyvr rig run` to "
        "make a new identity key, and rotate the rig's identity key on the hub's "
        "rig page"
    )
    if len(raw) > MAX_IDENTITY_BYTES:
        raise unreadable
    try:
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict) or data.get("v") != FILE_VERSION:
            raise unreadable
        seed = data.get("private_key")
        if not isinstance(seed, str):
            raise unreadable
        private = Ed25519PrivateKey.from_private_bytes(
            base64.b64decode(seed, validate=True)
        )
    except (UnicodeError, ValueError, RecursionError, binascii.Error) as exc:
        raise unreadable from exc
    return Identity(private)


#: The errors a folder gives for a hard link it cannot hold.
_NO_LINKS = frozenset({errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EXDEV})


def create() -> Identity:
    """Make a new identity keypair and keep it, unless another process kept
    one first: then that one is returned, so two first runs (``rig join`` and
    a service's ``rig run``, say) end up holding one key, the one the hub
    binds.

    The key is written to a file of its own and then linked into place, which
    fails when the file is already there; a folder that holds no hard links
    has the file renamed into place instead (:func:`mcgyvr.atomic.replace`),
    as the token's is.
    """
    private = Ed25519PrivateKey.generate()
    seed = private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    data = json.dumps({"v": FILE_VERSION, "private_key": _b64(seed)})
    target = path()
    staging = target.with_name(f".{target.name}.{secrets.token_hex(8)}")
    credentials.write_private(staging, data + "\n")
    try:
        os.link(staging, target)
    except FileExistsError:
        kept = load()
        if kept is None:
            raise CredentialsError(
                f"{target} was made and removed while this rig made its identity "
                "key; run `mcgyvr rig run` again"
            ) from None
        return kept
    except OSError as exc:
        if exc.errno not in _NO_LINKS:
            raise
        atomic.replace(staging, target)
    finally:
        staging.unlink(missing_ok=True)
    return Identity(private)


def ensure() -> Identity:
    """This rig's identity, made now if it has none: a rig that joined before
    identity keys gets one the first time its agent runs. Two runs at once
    get the same one (:func:`create`)."""
    return load() or create()


class Pins:
    """The identity keys of the peers this rig has met, by rig id, in
    :data:`PEERS_FILE` (or `target`). Each call reads the file again, so a
    peer forgotten from the command line counts at once."""

    def __init__(self, target: Path | None = None) -> None:
        self._target = target

    @property
    def path(self) -> Path:
        "The pins file."
        return self._target or roots.home() / PEERS_FILE

    def all(self) -> dict[str, str]:
        "Every pinned peer: rig id to identity key."
        target = self.path
        raw = credentials.read_private(
            target,
            MAX_PINS_BYTES,
            again="the peers met again are pinned anew",
            leaked=(
                "nothing in it is secret, but whoever could write it could have "
                "changed a pinned key: compare them with `mcgyvr rig peers`"
            ),
        )
        if raw is None:
            return {}
        unreadable = CredentialsError(
            f"{target} is not as mcgyvr writes it; remove it (the peers met "
            "again are pinned anew)"
        )
        if len(raw) > MAX_PINS_BYTES:
            raise unreadable
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise unreadable from exc
        if not isinstance(data, dict) or data.get("v") != FILE_VERSION:
            raise unreadable
        peers = data.get("peers")
        if not isinstance(peers, dict):
            raise unreadable
        for rig_id, key in peers.items():
            if not isinstance(key, str) or not hubwire.IDENTITY_KEY.fullmatch(key):
                raise unreadable
            if not isinstance(rig_id, str) or not rig_id:
                raise unreadable
        return dict(peers)

    def _write(self, peers: dict[str, str]) -> None:
        data = json.dumps({"v": FILE_VERSION, "peers": peers}, sort_keys=True)
        credentials.write_private(self.path, data + "\n")

    def pinned(self, rig_id: str) -> str | None:
        "The identity key pinned for `rig_id`, or None."
        return self.all().get(rig_id)

    def state(self, rig_id: str, identity_key: str) -> PinState:
        "How `identity_key` stands against the key pinned for `rig_id`."
        pinned = self.pinned(rig_id)
        if pinned is None:
            return "new"
        return "known" if pinned == identity_key else "changed"

    def pin(self, rig_id: str, identity_key: str) -> bool:
        """Pin `identity_key` for `rig_id` if it has none yet; False when the
        file is full (:data:`MAX_PINS`) and the peer was not pinned."""
        return rig_id not in self.pin_all({rig_id: identity_key})

    def pin_all(self, keys: dict[str, str]) -> set[str]:
        """Pin each of `keys` (rig id to identity key) that has none yet, in
        one write, and return the rig ids left unpinned because the file is
        full (:data:`MAX_PINS`)."""
        peers = self.all()
        before = len(peers)
        left = set()
        for rig_id, key in keys.items():
            if rig_id in peers:
                continue
            if len(peers) >= MAX_PINS:
                left.add(rig_id)
                continue
            peers[rig_id] = key
        if len(peers) > before:
            self._write(peers)
        return left

    def forget(self, rig_id: str) -> bool:
        "Drop the pin of `rig_id`, and say whether there was one."
        peers = self.all()
        if peers.pop(rig_id, None) is None:
            return False
        self._write(peers)
        return True


def vet_peer(
    *,
    rig_id: str,
    public_key: str,
    identity_key: str | None,
    signature: str | None,
    session_id: str,
    pinned: str | None,
) -> str | None:
    """Why the peer `rig_id` of session `session_id` is refused, or None to
    take it.

    A peer that carries an identity key must have signed its tunnel key
    `public_key` with it (`signature`), and must carry the key `pinned` for it,
    if one is. A peer that carries none is taken as an agent from before
    identity keys, unless one is pinned for it: then the hub left it out.
    """
    if identity_key is None:
        if pinned is None:
            return None
        return (
            f"peer {rig_id} was met with identity key "
            f"{hubwire.identity_fingerprint(pinned)}, and the hub now sends none "
            "for it"
        )
    if signature is None or not verify_session_key(
        identity_key, signature, session_id=session_id, public_key=public_key
    ):
        return (
            f"peer {rig_id}'s tunnel key is not signed by its identity key "
            f"{hubwire.identity_fingerprint(identity_key)}"
        )
    if pinned is not None and pinned != identity_key:
        return (
            f"peer {rig_id}'s identity key changed from "
            f"{hubwire.identity_fingerprint(pinned)} to "
            f"{hubwire.identity_fingerprint(identity_key)}; if its owner rotated "
            "it, compare the new fingerprint with them, then run "
            f"`mcgyvr rig peers --forget {rig_id}`"
        )
    return None
