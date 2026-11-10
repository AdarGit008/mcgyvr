"""The API key of a unit that listens beyond its own machine (`expose: lan`).

A docker unit listens on 127.0.0.1 unless its unit states `expose: lan`; one
that does listens on every interface, and so asks every request for a key that
mcgyvr makes for it. The key lives in a file of its own under the data folder,
``unit-keys/<address>-<port>.env``, named for the address the unit answers at
(one address is one process), at mode 0600 in a folder created at 0700. It is
an env file: the compose service names it under `env_file`, and `docker
compose` reads it where it runs, on this machine, also when the daemon is a
rig's reached over ssh; so the key is never written into a compose file or
into `fleet.yaml`. It carries the key under the name each engine reads it from
(`ENV_NAMES`), and the server takes it from there.

mcgyvr's own clients of that address read the same file (:func:`for_address`)
and send the key as a bearer token: a dispatch, a status poll, setup's
discovery, the fleet sampler's read, the door's probes and the rig agent's
relay. Each sends it to that address alone. A client elsewhere is given it by
`mcgyvr fleet key <unit>`. The file is written and read by
:func:`mcgyvr.atomic.write_private` and :func:`mcgyvr.atomic.read_private`: at
0600, never through a link, refused when another user owns it or others may
read or write it.
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from mcgyvr import atomic
from mcgyvr.fleet import roots

#: The folder under the data folder that holds every unit's key file.
KEYS_DIR = "unit-keys"
#: The variables the key is handed to the server under: llama-server reads
#: `LLAMA_API_KEY` (its `--api-key`), vLLM's server `VLLM_API_KEY`.
LLAMA_ENV = "LLAMA_API_KEY"
VLLM_ENV = "VLLM_API_KEY"
ENV_NAMES = (LLAMA_ENV, VLLM_ENV)
#: A key as `new_key` makes it: 43 characters of URL-safe base64, 256 bits.
KEY = re.compile(r"[A-Za-z0-9_-]{43}")
#: A key file is two short lines; anything longer is not one `ensure` wrote.
MAX_KEY_FILE_BYTES = 512
#: How a key file is made anew, said by every refusal of one.
_AGAIN = "run `mcgyvr emit` again, which makes a new key"


class UnitKeyError(Exception):
    "A key file that cannot be trusted or read, named with what to do about it."


def path(host: str, port: int) -> Path:
    """Where the key of the unit at `host:port` is kept, the host spelled as its
    container's name spells it (:func:`mcgyvr.serving.safe_host`, which refuses
    a host no file can be named after with UnitError)."""
    from mcgyvr.serving import safe_host

    return roots.data_home() / KEYS_DIR / f"{safe_host(host)}-{int(port)}.env"


def _text(key: str) -> str:
    return "".join(f"{name}={key}\n" for name in ENV_NAMES)


def load(host: str, port: int) -> str | None:
    """The key of the unit at `host:port`, or None when it has none (:func:`read`)."""
    return read(path(host, port))


def read(target: Path) -> str | None:
    """The key a key file holds, or None when there is no such file.

    The file is read by :func:`mcgyvr.atomic.read_private`, and must hold one
    line per name in `ENV_NAMES`, every one with the same key; anything else
    raises UnitKeyError naming the file.
    """
    try:
        raw = atomic.read_private(
            target, MAX_KEY_FILE_BYTES, again=_AGAIN, leaked=f"remove it and {_AGAIN}"
        )
    except atomic.PrivateFileError as exc:
        raise UnitKeyError(str(exc)) from exc
    if raw is None:
        return None
    unreadable = UnitKeyError(
        f"{target} is not a key file as `mcgyvr emit` writes it; remove it and {_AGAIN}"
    )
    if len(raw) > MAX_KEY_FILE_BYTES:
        raise unreadable
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeError as exc:
        raise unreadable from exc
    pairs = dict(line.partition("=")[::2] for line in lines if line)
    keys = {pairs.get(name) for name in ENV_NAMES}
    if len(keys) != 1 or set(pairs) != set(ENV_NAMES):
        raise unreadable
    key = keys.pop()
    if key is None or not KEY.fullmatch(key):
        raise unreadable
    return key


def new_key() -> str:
    """A fresh key, as every key mcgyvr hands a llama-server or vLLM is made
    (:data:`KEY`): a unit's by :func:`ensure`, a pooled native head's for one
    session (:meth:`mcgyvr.rig.userwg.NativeHost.head_key`)."""
    return secrets.token_urlsafe(32)


def ensure(host: str, port: int) -> tuple[Path, bool]:
    """The key file of the unit at `host:port`, made when there is none.

    Answers the file and whether it was made just now. A file that is there is
    kept as it is, so a unit keeps its key from one emit to the next and its
    clients go on sending the one they have; a file that is there and cannot be
    trusted raises UnitKeyError rather than being replaced.
    """
    target = path(host, port)
    if read(target) is not None:
        return target, False
    try:
        atomic.write_private(target, _text(new_key()))
    except atomic.PrivateFileError as exc:
        raise UnitKeyError(str(exc)) from exc
    return target, True


def for_address(address: str) -> str | None:
    """The key mcgyvr keeps for the unit answering at `address`, or None.

    None for an address no key is kept for, and for one that names no host or
    no usable port: such an address is refused where it is read as a unit's,
    and it has nothing to send here. A key file that cannot be trusted raises
    UnitKeyError, so a client never goes on without the key it needs.
    """
    from mcgyvr.serving import UnitError, host_of, port_of

    try:
        target = path(host_of(address), port_of(address))
    except (UnitError, ValueError):
        return None
    return read(target)
