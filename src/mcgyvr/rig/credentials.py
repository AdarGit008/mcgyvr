""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from mcgyvr import atomic
from mcgyvr.fleet import roots

#
CREDENTIALS_FILE = "rig-credentials.json"
#
MAX_CREDENTIALS_BYTES = 4096
#
#
TOKEN = re.compile(r"[A-Za-z0-9_-]{1,256}")
#
_TOKEN_ID = re.compile(r"(mh[a-z]_[0-9a-f]{16})_.+")


class CredentialsError(Exception):
    ""


@dataclass(frozen=True, kw_only=True)
class Credentials:
    ""

    hub: str
    token: str


def path() -> Path:
    ""
    return roots.home() / CREDENTIALS_FILE


def shown(token: str) -> str:
    ""
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
    ""
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
    ""
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
    ""
    target = path()
    if not target.exists() and not target.is_symlink():
        return False
    target.unlink()
    return True
