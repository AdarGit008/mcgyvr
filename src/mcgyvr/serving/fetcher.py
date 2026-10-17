#
""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from typing import Any

#
WEIGHTS_DIR_ENV = "MCGYVR_WEIGHTS"
#
PART = ".part"
#
CHUNK_BYTES = 8 << 20
#
#
TIMEOUT_S = 60.0

#
PRESENT = "present"
FETCHED = "fetched"
RESUMED = "resumed"
INCOMPLETE = "incomplete"
MISMATCH = "mismatch"
NOT_FETCHED = "refused"
GOOD = frozenset({PRESENT, FETCHED, RESUMED})


def weights_dir() -> str:
    ""
    override = os.environ.get(WEIGHTS_DIR_ENV)
    if override:
        return os.path.expanduser(override)
    return os.path.expanduser("~/.cache/mcgyvr/weights")


def _hash_into(path: str, hasher: Any) -> int:
    ""
    held = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(CHUNK_BYTES)
            if not chunk:
                return held
            hasher.update(chunk)
            held += len(chunk)


def _ask(url: str, start: int, token: str | None) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "mcgyvr-fetch"})
    if start:
        request.add_header("Range", f"bytes={start}-")
    if token:
        #
        #
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(request, timeout=TIMEOUT_S)


def fetch_one(
    want: dict[str, Any], root: str, token_env: str, token: str | None
) -> dict[str, Any]:
    ""
    name = str(want["name"])
    size = int(want["bytes"])
    sha256 = str(want["sha256"])
    dest = os.path.join(root, name)
    part = dest + PART
    row: dict[str, Any] = {"file": name, "to": dest, "bytes": size, "sha256": sha256}

    if os.path.lexists(dest):
        hasher = hashlib.sha256()
        try:
            #
            #
            held = os.path.getsize(dest) if os.path.isfile(dest) else -1
            held = _hash_into(dest, hasher) if held == size else held
        except OSError as exc:
            held = -1
            row["why"] = f"{dest} cannot be read: {exc}"
        if held == size and hasher.hexdigest() == sha256:
            row["state"] = PRESENT
            return row
        row["state"] = NOT_FETCHED
        row.setdefault(
            "why",
            f"{dest} is there and is not this file (its sha256 or size differs); "
            "mcgyvr did not put it there, so it is left as it is. Move it away "
            "and fetch again",
        )
        return row

    have = os.path.getsize(part) if os.path.isfile(part) else 0
    if have > size:
        os.remove(part)
        have = 0
    free = shutil.disk_usage(root).free
    if free < size - have:
        row["state"] = NOT_FETCHED
        row["why"] = (
            f"the disk holding {root} has {free} bytes free and this file needs "
            f"{size - have} more; nothing was fetched"
        )
        return row

    hasher = hashlib.sha256()
    carried = _hash_into(part, hasher) if have else 0
    row["resumed_from"] = carried
    if have < size:
        try:
            response = _ask(str(want["url"]), have, token)
        except urllib.error.HTTPError as exc:
            row["state"] = INCOMPLETE if have else NOT_FETCHED
            row["why"] = f"the Hub answered HTTP {exc.code} for {want['url']}"
            if exc.code in (401, 403):
                row["why"] += (
                    ": the repository is gated or private, or the token is not "
                    f"allowed it; put a token that is in ${token_env}"
                )
            return row
        except (OSError, http.client.HTTPException, ValueError) as exc:
            row["state"] = INCOMPLETE if have else NOT_FETCHED
            row["why"] = f"{want['url']} did not answer: {getattr(exc, 'reason', exc)}"
            return row
        with response:
            status = response.getcode()
            if have and status == 200:
                #
                hasher = hashlib.sha256()
                have = 0
                row["resumed_from"] = 0
            elif have and status != 206:
                row["state"] = INCOMPLETE
                row["why"] = f"the Hub answered HTTP {status} to a resumed download"
                return row
            try:
                with open(part, "ab" if have else "wb") as out:
                    while have <= size:
                        chunk = response.read(CHUNK_BYTES)
                        if not chunk:
                            break
                        out.write(chunk)
                        hasher.update(chunk)
                        have += len(chunk)
                    out.flush()
                    os.fsync(out.fileno())
            except (OSError, http.client.HTTPException, ValueError) as exc:
                row["cut"] = f"{getattr(exc, 'reason', exc)}"
    have = os.path.getsize(part)
    if have < size:
        row["state"] = INCOMPLETE
        row["why"] = (
            f"the download ended at {have} of {size} bytes; {part} is kept and "
            "the next fetch resumes it"
        )
        return row
    digest = hasher.hexdigest()
    if have != size or digest != sha256:
        os.remove(part)
        row["state"] = MISMATCH
        row["why"] = (
            f"the bytes fetched ({have}) hash to sha256 {digest}, not the "
            f"{sha256} the Hub states for {size} bytes; nothing is kept"
        )
        return row
    os.replace(part, dest)
    row["state"] = RESUMED if carried else FETCHED
    return row


def main(job_text: str) -> int:
    ""
    job = json.loads(job_text)
    root = weights_dir()
    os.makedirs(root, exist_ok=True)
    token = job.get("token") or None
    token_env = str(job.get("token_env") or "HF_TOKEN")
    rows = []
    for want in job["files"]:
        print(f"fetch: {want['name']} ({want['bytes']} bytes)", file=sys.stderr)
        rows.append(fetch_one(want, root, token_env, token))
    print(json.dumps({"weights_dir": root, "files": rows}))
    return 0 if all(row["state"] in GOOD for row in rows) else 1
