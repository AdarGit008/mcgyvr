"""A stand-in for a pooled head's llama-server: it reaches its rpc devices, then waits.

Written out as the engine program a native session test spawns. It writes its
argv and the names of its environment to ``head-said.json`` in the folder above
its model's (a JSON file; the head is given no variable a test could name it by),
connects to each ``host:port`` its ``--rpc`` names, sends ``ping`` and keeps
what came back, writes that too, and then sleeps until it is ended, as a
server would serve.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time


def main() -> int:
    args = sys.argv[1:]
    said: dict[str, object] = {"argv": args, "env": sorted(os.environ), "rpc": {}}
    model = args[args.index("-m") + 1] if "-m" in args else ""
    target = (
        os.path.join(os.path.dirname(os.path.dirname(model)), "head-said.json")
        if model
        else ""
    )
    if "--rpc" in args:
        for device in args[args.index("--rpc") + 1].split(","):
            host, _, port = device.rpartition(":")
            try:
                with socket.create_connection((host, int(port)), timeout=5) as conn:
                    conn.sendall(b"ping")
                    conn.shutdown(socket.SHUT_WR)
                    got = conn.recv(64)
            except OSError as exc:
                got = f"failed: {exc}".encode()
            rpc = said["rpc"]
            assert isinstance(rpc, dict)
            rpc[device] = got.decode("utf-8", "replace")
    if target:
        with open(target, "w", encoding="utf-8") as out:
            json.dump(said, out)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
