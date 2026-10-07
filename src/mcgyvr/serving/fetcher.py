#!/usr/bin/env python3
"""The weights fetcher, shipped to a rig over ssh as ``python3 -`` by ``serve fetch``.

Stdlib only, like the rig scan (:mod:`mcgyvr.serving.rigscan`): the rig has
no venv and no mcgyvr. The door's fetch step sends this file on stdin with
the job appended (:func:`mcgyvr.serving.fetchlist.payload`), so the job, and
a Hugging Face token in it, travel inside the ssh connection and never on a
command line or in a file.

For each file of the job, into the weights folder (``$MCGYVR_WEIGHTS``, else
``~/.cache/mcgyvr/weights``, the folder the rig scan measures):

* a file of that name already there whose sha256 is the job's is
  ``present`` and not fetched again; one whose sha256 is another is
  ``refused`` and left as it is, since mcgyvr did not put it there;
* otherwise the bytes go to ``<name>.part``, resumed with ``Range`` from
  whatever a ``.part`` already holds, and hashed as they land; at the
  stated size, a sha256 that matches is renamed into place (``fetched``, or
  ``resumed`` when a ``.part`` was carried on) and one that does not is
  deleted (``mismatch``): no file whose hash does not match is kept;
* a download that ends short keeps its ``.part`` for the next fetch
  (``incomplete``), and one the disk has no room for is ``refused`` before
  a byte is asked for.

The token goes only to the URL the job names, as an unredirected header:
the Hub redirects a download to a signed address elsewhere, and the token is
not sent there.

It prints one JSON document on stdout, ``{"weights_dir", "files": [row]}``,
and exits 0 when every file is present, fetched or resumed, 1 otherwise.
"""

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

#: The variable that moves the weights folder, as the rig scan reads it.
WEIGHTS_DIR_ENV = "MCGYVR_WEIGHTS"
#: What a file is called while it is being fetched.
PART = ".part"
#: How much of a download is read, written and hashed at a time.
CHUNK_BYTES = 8 << 20
#: How long one read of a download waits for bytes before the download is cut
#: and kept as a ``.part``.
TIMEOUT_S = 60.0

#: A row's ``state``: what became of the file.
PRESENT = "present"
FETCHED = "fetched"
RESUMED = "resumed"
INCOMPLETE = "incomplete"
MISMATCH = "mismatch"
REFUSED = "refused"
GOOD = frozenset({PRESENT, FETCHED, RESUMED})


def weights_dir() -> str:
    """The rig's weights folder, as :mod:`mcgyvr.serving.rigscan` names it."""
    override = os.environ.get(WEIGHTS_DIR_ENV)
    if override:
        return os.path.expanduser(override)
    return os.path.expanduser("~/.cache/mcgyvr/weights")


def _hash_into(path: str, hasher: Any) -> int:
    """Feed ``path`` to ``hasher``; return how many bytes it held."""
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
        # Unredirected: urllib carries a request's ordinary headers to the
        # address it is redirected to, and these it does not.
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(request, timeout=TIMEOUT_S)


def fetch_one(
    want: dict[str, Any], root: str, token_env: str, token: str | None
) -> dict[str, Any]:
    """Fetch one file of the job into ``root``; the row that says what happened."""
    name = str(want["name"])
    size = int(want["bytes"])
    sha256 = str(want["sha256"])
    dest = os.path.join(root, name)
    part = dest + PART
    row: dict[str, Any] = {"file": name, "to": dest, "bytes": size, "sha256": sha256}

    if os.path.lexists(dest):
        hasher = hashlib.sha256()
        try:
            # Hashed only at the size it should have: a file of another size
            # is not this one, however long it would take to read.
            held = os.path.getsize(dest) if os.path.isfile(dest) else -1
            held = _hash_into(dest, hasher) if held == size else held
        except OSError as exc:
            held = -1
            row["why"] = f"{dest} cannot be read: {exc}"
        if held == size and hasher.hexdigest() == sha256:
            row["state"] = PRESENT
            return row
        row["state"] = REFUSED
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
        row["state"] = REFUSED
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
            row["state"] = INCOMPLETE if have else REFUSED
            row["why"] = f"the Hub answered HTTP {exc.code} for {want['url']}"
            if exc.code in (401, 403):
                row["why"] += (
                    ": the repository is gated or private, or the token is not "
                    f"allowed it; put a token that is in ${token_env}"
                )
            return row
        except (OSError, http.client.HTTPException, ValueError) as exc:
            row["state"] = INCOMPLETE if have else REFUSED
            row["why"] = f"{want['url']} did not answer: {getattr(exc, 'reason', exc)}"
            return row
        with response:
            status = response.getcode()
            if have and status == 200:
                # The server ignored the range and sent the whole file.
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
    """Run the job; print the rows as one JSON document; 0 when all are good."""
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
