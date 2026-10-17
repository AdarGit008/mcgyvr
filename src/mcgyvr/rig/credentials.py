"""The rig token this machine keeps: where it lives, and how it is written and read.

A rig token is a secret the hub shows once and the agent needs after every
restart, so it is kept in a file of its own in the mcgyvr home folder, at mode
0600 whatever the umask, in a folder created at 0700. `save` writes it whole or
not at all and `load` refuses a file that is a link, of another user, readable
or writable by others, or not the shape `save` writes -- each refusal says what
to do instead. What is shown of a token is its public id, never the secret.
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from mcgyvr import atomic
from mcgyvr.fleet import roots

# The name of the token file inside the mcgyvr home folder.
CREDENTIALS_FILE = "rig-credentials.json"
# A token file is a few hundred bytes; anything longer is not one `save` wrote.
MAX_CREDENTIALS_BYTES = 4096
# What a token may hold: the characters a request header carries, 1 to 256 of them.
# A token with anything else could not be sent whole, so `_check` refuses it.
TOKEN = re.compile(r"[A-Za-z0-9_-]{1,256}")
# A token as a hub shows it: a public id `mh<letter>_<16 hex digits>` before the secret.
_TOKEN_ID = re.compile(r"(mh[a-z]_[0-9a-f]{16})_.+")


class CredentialsError(Exception):
    "A token file that cannot be trusted, named with what to do about it."


@dataclass(frozen=True, kw_only=True)
class Credentials:
    "What one join gives this machine: the hub's address and the token it was given."

    hub: str
    token: str


def path() -> Path:
    "The token file, in the same folder the config is looked for."
    return roots.home() / CREDENTIALS_FILE


def shown(token: str) -> str:
    "What a token may be printed as: its public id, or else only how long it is."
    match = _TOKEN_ID.fullmatch(token)
    if match:
        return f"{match.group(1)}_…"
    return f"a token of {len(token)} characters"


def _check(credentials: Credentials) -> None:
    if not TOKEN.fullmatch(credentials.token):
        raise ValueError(
            "the rig token holds a character a request header cannot carry; "
            "paste it exactly as the hub showed it"
        )
    if not credentials.hub or len(credentials.hub) > 2048:
        raise ValueError("the hub address is empty or too long")


def save(credentials: Credentials) -> Path:
    """Write the token file for `credentials`, and say where it went.

    The values are checked first, raising ValueError if either cannot be used.
    The home folder is created at 0700 only when it is missing; one that exists
    keeps its own mode. A link in the file's place raises CredentialsError
    rather than being written through. `atomic.write` puts the JSON in place in
    one step, at 0600, fsynced.
    """
    _check(credentials)
    target = path()
    folder = target.parent
    if not folder.exists():
        folder.mkdir(mode=0o700, parents=True)
        os.chmod(folder, 0o700)
    if target.is_symlink():
        raise CredentialsError(
            f"{target} is a link; remove it, and keep no link in its place"
        )
    data = json.dumps({"hub": credentials.hub, "token": credentials.token})
    atomic.write(target, data + "\n", private=True, fsync=True)
    return target


def load() -> Credentials | None:
    """Read the token file back, or None when this machine has none.

    The file is opened without following a link and then judged by what is
    actually open, not by the path: it must be a plain file of this user with no
    group or other bits, no longer than `MAX_CREDENTIALS_BYTES`, holding the
    JSON object `save` writes. Anything else raises CredentialsError saying what
    to do; a file that is absent is not an error.
    """
    target = path()
    try:
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CredentialsError(
            f"{target} cannot be opened ({exc.strerror}); it must be a plain file, "
            "not a link"
        ) from exc
    with os.fdopen(fd, "rb") as handle:
        facts = os.fstat(handle.fileno())
        if not stat.S_ISREG(facts.st_mode):
            raise CredentialsError(f"{target} is not a plain file; remove it")
        if facts.st_uid != os.getuid():
            raise CredentialsError(
                f"{target} belongs to another user; remove it and join again"
            )
        if stat.S_IMODE(facts.st_mode) & 0o077:
            raise CredentialsError(
                f"{target} can be read or written by others; run `chmod 600 "
                f"{target}`, and if anyone else could have read it, rotate the "
                "rig's token on the hub and join again"
            )
        raw = handle.read(MAX_CREDENTIALS_BYTES + 1)
    unreadable = CredentialsError(
        f"{target} is not as `mcgyvr rig join` writes it; remove it with "
        "`mcgyvr rig leave` and join again"
    )
    if len(raw) > MAX_CREDENTIALS_BYTES:
        raise unreadable
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise unreadable from exc
    if not isinstance(data, dict):
        raise unreadable
    hub, token = data.get("hub"), data.get("token")
    if not isinstance(hub, str) or not isinstance(token, str):
        raise unreadable
    kept = Credentials(hub=hub, token=token)
    try:
        _check(kept)
    except ValueError as exc:
        raise unreadable from exc
    return kept


def remove() -> bool:
    "Delete the token file, and say whether there was one -- a link counts as one."
    target = path()
    if not target.exists() and not target.is_symlink():
        return False
    target.unlink()
    return True
