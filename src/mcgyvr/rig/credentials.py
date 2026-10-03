"""Where the rig token is kept, and how: its owner's alone, apart from the config.

A config never holds a secret; it names the environment variable that does
(``api_key_env``). A rig token cannot live only in a variable: the hub shows
it once, at ``mcgyvr rig join``, and the agent needs it again after every
restart and reboot. So it is kept in one file of its own,
``$MCGYVR_HOME/rig-credentials.json`` (:func:`path`), beside the config and
never in it, with the hub it belongs to:

* written whole or not at all — a staging file, then a rename;
* at mode 0600 whatever the umask, in a config folder created at 0700 when
  it does not exist (an existing folder keeps its mode);
* read only when it is still that: a link, a file another user owns, a file
  the group or others could read or write, or one that is not what this
  module writes is refused with what to do, and never read past.

What is shown of a token anywhere is :func:`shown`: the hub's public token id,
never the secret after it.
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.fleet import roots

#: The file's name in the config folder.
CREDENTIALS_FILE = "rig-credentials.json"
#: The largest file this module reads back; what it writes is far smaller.
MAX_CREDENTIALS_BYTES = 4096
#: A token is sent in an HTTP header, so it is held to characters that cannot
#: break one; the hub's own tokens are of these.
TOKEN = re.compile(r"[A-Za-z0-9_-]{1,256}")
#: The public part of a hub token: its kind and its id.
_TOKEN_ID = re.compile(r"(mh[a-z]_[0-9a-f]{16})_.+")


class CredentialsError(Exception):
    """The kept file is there but is not safe or not readable as written."""


@dataclass(frozen=True, kw_only=True)
class Credentials:
    """A rig token and the hub it was issued by, as ``mcgyvr rig join`` was
    given it."""

    hub: str
    token: str


def path() -> Path:
    """``$MCGYVR_HOME/rig-credentials.json`` (default ``~/.mcgyvr``)."""
    return roots.home() / CREDENTIALS_FILE


def shown(token: str) -> str:
    """What may be shown of ``token``: its public id, or only its length."""
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
    """Keep ``credentials``, replacing what was kept; the path it is kept at."""
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
    staging = folder / f".{CREDENTIALS_FILE}.part"
    staging.unlink(missing_ok=True)
    data = json.dumps({"hub": credentials.hub, "token": credentials.token})
    fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, target)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    return target


def load() -> Credentials | None:
    """What is kept, ``None`` when nothing is, or :class:`CredentialsError`."""
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
    """Forget the kept token; whether there was one."""
    target = path()
    if not target.exists() and not target.is_symlink():
        return False
    target.unlink()
    return True
