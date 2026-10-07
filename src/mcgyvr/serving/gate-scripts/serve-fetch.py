#!/usr/bin/env python3
# RUN_REWRITES: serve-fetch.json
"""The door's serve step, fetch: download weights on the rig, held to their sha256.

Reads the fetch list the door read and held to a hash before any gate
(RUN_FETCH, :mod:`mcgyvr.serving.fetchlist`), says how many files and how
many bytes in all before a byte moves (no cap; owner, 2026-10-07), and ships
the fetcher (:mod:`mcgyvr.serving.fetcher`) to the rig through the ssh shim
with its job on stdin. The fetcher resumes from a ``.part``, renames a file
into the weights folder only when its sha256 matches, and deletes one that
does not.

A Hugging Face token is read here from the variable the door names
(RUN_FETCH_TOKEN_ENV) and goes only into that stdin. It is never printed and
never filed: serve-fetch.json carries what became of each file and nothing
of the token.

A file that did not end present, fetched or resumed is exit 1: a result, not
a refusal. A download that ended short keeps its ``.part``, and the next fetch
resumes it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from mcgyvr.serving.gatelib import door_required, need, ssh


def main() -> int:
    door_required("serve-fetch")
    from mcgyvr.serving import fetcher, fetchlist

    host = need("RUN_HOST")
    out = Path(need("RUN_OUT_DIR")) / "serve-fetch.json"
    try:
        wants = fetchlist.parse(need("RUN_FETCH"))
        hub = fetchlist.endpoint(os.environ)
    except fetchlist.FetchListError as exc:
        print(f"serve-fetch: REFUSED — {exc}", file=sys.stderr)
        return 2
    token_env = need("RUN_FETCH_TOKEN_ENV")
    token = os.environ.get(token_env) or None
    total = fetchlist.total_bytes(wants)
    print(
        f"serve-fetch: {len(wants)} file(s), {total} bytes in all "
        f"({total / 1e9:.2f} GB), to the weights folder on {host}; no size cap"
    )
    for want in wants:
        print(
            f"serve-fetch:   {want.repo}@{want.revision[:12]} {want.file} "
            f"{want.bytes} bytes"
        )
    try:
        done = ssh(
            host,
            fetchlist.REMOTE_COMMAND,
            # Held to no fixed bound: a download takes as long as its bytes do.
            # The fetcher's own reads time out (fetcher.TIMEOUT_S), so a
            # stalled one ends and keeps its .part.
            timeout=None,
            input=fetchlist.payload(wants, hub, token_env, token),
        )
    except subprocess.TimeoutExpired:  # pragma: no cover - no bound is set
        return 1
    if done.stderr:
        sys.stderr.write(done.stderr)
    lines = done.stdout.strip().splitlines()
    try:
        said = json.loads(lines[-1]) if lines else None
    except ValueError:
        said = None
    if not isinstance(said, dict) or not isinstance(said.get("files"), list):
        print(
            f"serve-fetch: the fetcher on {host} printed no result this reads "
            f"(exit {done.returncode}); what landed is unknown",
            file=sys.stderr,
        )
        rows: list[dict[str, object]] = []
        weights_dir = None
    else:
        rows = said["files"]
        weights_dir = said.get("weights_dir")
    by_name = {want.name: want for want in wants}
    for row in rows:
        asked = by_name.get(str(row.get("file")))
        if asked is not None:
            row.update(repo=asked.repo, revision=asked.revision, path=asked.file)
        why = f" — {row['why']}" if row.get("why") else ""
        print(f"serve-fetch: {row.get('file')} {row.get('state')}{why}")
    record = {
        "run_id": need("RUN_ID"),
        "host": host,
        "mode": "fetch",
        "hub": hub,
        "token_env": token_env,
        "token_given": token is not None,
        "weights_dir": weights_dir,
        "total_bytes": total,
        "fetcher_exit": done.returncode,
        "files": rows,
    }
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    good = len(rows) == len(wants) and all(
        row.get("state") in fetcher.GOOD for row in rows
    )
    return 0 if good and done.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
