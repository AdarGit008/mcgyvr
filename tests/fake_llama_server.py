"""A stand-in for llama-server: answers ``/v1/models`` and ``/health`` on ``--port``.

Run as a program (the native launcher's tests write it out as
``llama-server``). It prints the line llama.cpp's Metal backend prints at
start-up, then serves until it is ended. ``FAKE_MODE=crash`` exits 3 at once;
``crash-once`` does so only while ``$FAKE_MARKER`` does not exist yet, and
makes it.
"""

from __future__ import annotations

import http.server
import json
import os
import sys

METAL = "ggml_metal_init: recommendedMaxWorkingSetSize  = 22906.50 MB\n"


def main() -> int:
    args = sys.argv[1:]
    port = int(args[args.index("--port") + 1])
    mode = os.environ.get("FAKE_MODE", "serve")
    marker = os.environ.get("FAKE_MARKER", "")
    if mode == "crash" or (mode == "crash-once" and not os.path.exists(marker)):
        if marker:
            open(marker, "w").close()
        sys.stderr.write("fake llama-server: crashing as told\n")
        return 3
    sys.stderr.write(METAL)
    sys.stderr.flush()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body: object
            if self.path == "/v1/models":
                body = {"data": [{"id": "fake-model"}]}
            elif self.path == "/health":
                body = {"status": "ok"}
            else:
                self.send_response(404)
                self.end_headers()
                return
            raw = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *a: object) -> None:
            return

    http.server.HTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
