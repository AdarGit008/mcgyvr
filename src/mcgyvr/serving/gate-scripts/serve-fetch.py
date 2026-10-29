#!/usr/bin/env python3
# RUN_REWRITES: serve-fetch.json
# The `serve-fetch` gate: read the fetch list the door exported for this run,
# run the fetcher on the run's host over ssh, and record what landed there.
"""
Fetch a run's weight files onto its host, from this side of `ssh`.

The script is a gate started by the door, so it takes the fetch list
(`RUN_FETCH`), the target host (`RUN_HOST`), the export directory
(`RUN_OUT_DIR`) and the run id (`RUN_ID`) from the environment and refuses to
run without them. It parses and validates the list, resolves the hub endpoint
from `HF_ENDPOINT`, and prints every file with its pinned revision and size,
plus the total — with no size cap, so a large list is a slow run rather than a
refused one.

The host is not assumed to have mcgyvr installed: the fetcher, assembled with
the modules it imports, and a JSON job describing each file are piped to
`python3 -` on a POSIX host (`fetchlist.REMOTE_COMMAND`); a Windows rig gets
the program through PowerShell and the job on its stdin (`gatelib.ship`).
The fetcher's last stdout line is read as the JSON report of what happened to
each file; the rows are joined back to the wanted repo, revision and path by
filename, echoed, and written with the run's
settings to `<RUN_OUT_DIR>/serve-fetch.json`. The exit status is 0 only when
the fetcher exited 0 and every file ended in one of `fetcher.GOOD`'s states.
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
    from mcgyvr.serving import fetcher, fetchlist, gatelib

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
    # The payload travels on stdin: it carries the fetcher and the token,
    # which must not be readable in the host's process list (fetchlist.shipment).
    sent = fetchlist.shipment(
        gatelib.shipping_os(host),
        gatelib.rig_system(host),
        wants,
        hub,
        token_env,
        token,
    )
    try:
        # No timeout: the run ends when the files have been transferred,
        # however long that takes. A Linux rig's ssh is called as it always
        # was; a macOS or Windows rig's keeps ssh's keepalive on.
        if sent.keepalive:
            done = ssh(
                host, sent.command, timeout=None, input=sent.stdin, keepalive=True
            )
        else:
            done = ssh(host, sent.command, timeout=None, input=sent.stdin)
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
