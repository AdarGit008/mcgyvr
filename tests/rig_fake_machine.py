"""The real rig agent on an invented machine, for the tests that run a real hub.

``python -m tests.rig_fake_machine rig ...`` is :func:`mcgyvr.cli.main` with
three seams replaced, and nothing else:

* :func:`mcgyvr.rig.hardware.read` reads :class:`Machine`'s cards, all of
  one vendor and one size;
* :func:`mcgyvr.rig.inventory.read` holds :class:`Machine`'s models, with
  the metadata a GGUF scan would read and no file under them;
* :class:`mcgyvr.sandbox.pooled.Pool` is :class:`EngineDocker`, the session
  tests' :class:`tests.rig_pool_fakes.FakeDocker` and, on the loopback port a
  session's tunnel publishes for the head's API, an :class:`Engine` that
  answers the way llama-server's HTTP API does.

The agent's websocket, its sessions, the head's health check and warm-up and
the relay to the head are its own: they reach the engine over loopback HTTP.
A machine made without ``multi_session`` drops that one feature from the
agent's hello, so it stands for an agent from before the feature.

It runs as a child of a test, from the repository root (``tests`` is
imported from there), and reads its machine from :data:`MACHINE_ENV`.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from tests import rig_pool_fakes as fakes

#: The variable that carries a :class:`Machine` to the child, as JSON.
MACHINE_ENV = "MCGYVR_TEST_FAKE_MACHINE"

#: The port the head's API listens on inside its session.
HEAD_API_PORT = 8080


@dataclass(frozen=True)
class Model:
    name: str
    gib: float
    layers: int


@dataclass(frozen=True)
class Machine:
    """What the faked seams read: its id, its cards and the models it holds."""

    machine_id: str
    cards: int
    models: tuple[Model, ...]
    vram_mb: int = 8192
    multi_session: bool = True

    def env(self) -> dict[str, str]:
        body = {
            "machine_id": self.machine_id,
            "cards": self.cards,
            "models": [[m.name, m.gib, m.layers] for m in self.models],
            "vram_mb": self.vram_mb,
            "multi_session": self.multi_session,
        }
        return {MACHINE_ENV: json.dumps(body)}

    @classmethod
    def from_env(cls) -> Machine:
        body = json.loads(os.environ[MACHINE_ENV])
        return cls(
            machine_id=body["machine_id"],
            cards=body["cards"],
            models=tuple(Model(n, g, layers) for n, g, layers in body["models"]),
            vram_mb=body["vram_mb"],
            multi_session=body["multi_session"],
        )


def report(machine: Machine) -> Any:
    from mcgyvr.rig import hardware, protocol

    return hardware.Report(
        machine_id=machine.machine_id,
        ram_total_mb=65536,
        ram_free_mb=60000,
        cards=tuple(
            protocol.CardReport(
                index=i,
                name="Card A",
                vram_total_mb=machine.vram_mb,
                vram_free_mb=machine.vram_mb - 200,
            )
            for i in range(machine.cards)
        ),
        notes=(),
        sources=tuple(("nvidia", i) for i in range(machine.cards)),
    )


def inventory(machine: Machine, folder: str | None) -> Any:
    from mcgyvr.rig import inventory as inventory_module
    from mcgyvr.rig import protocol

    if folder is None:
        return inventory_module.Inventory(folder=None)
    return inventory_module.Inventory(
        folder=Path(folder),
        models=tuple(
            protocol.ModelInfo(
                name=m.name,
                size_bytes=int(m.gib * (1 << 30)),
                arch="llama",
                n_layers=m.layers,
                n_ctx_train=32768,
                n_embd=2048,
                n_head=16,
                n_head_kv=4,
                kv_bytes_per_token=m.layers * 4096,
            )
            for m in machine.models
        ),
        files={m.name: m.name for m in machine.models},
    )


class _EngineServer(ThreadingHTTPServer):
    #: The model and the ``--gpus`` the session's head was started with.
    model: str | None = None
    gpus: tuple[str, ...] = ()


class _EngineHandler(BaseHTTPRequestHandler):
    server: _EngineServer

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send(self, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        self._send({"status": "ok"})

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        said = f"{self.server.model} on {' '.join(self.server.gpus)}"
        self._send(
            {
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "model": self.server.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": said},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 5,
                    "total_tokens": 8,
                },
            }
        )


class Engine:
    """A stand-in llama-server on one loopback port. A chat is answered with
    the model and the ``--gpus`` its head was started with."""

    def __init__(self, port: int) -> None:
        self.server = _EngineServer(("127.0.0.1", port), _EngineHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def _values(argv: Sequence[str], option: str) -> list[str]:
    return [argv[i + 1] for i, word in enumerate(argv[:-1]) if word == option]


@dataclass
class EngineDocker(fakes.FakeDocker):
    """:class:`~tests.rig_pool_fakes.FakeDocker`, with an :class:`Engine` on
    each port a tunnel publishes for the head's API, told its head's model
    and cards when the head starts."""

    engines: dict[str, Engine] = field(default_factory=dict)

    def start(self, argv: Sequence[str]) -> None:
        super().start(argv)
        name = argv[list(argv).index("--name") + 1]
        for spec in _values(argv, "--publish"):
            if spec.endswith(f":{HEAD_API_PORT}/tcp"):
                self.engines[name] = Engine(int(spec.split(":")[1]))
        if name.endswith("-head"):
            engine = self.engines.get(name.removesuffix("-head") + "-tunnel")
            if engine is not None:
                models = _values(argv, "-m")
                engine.server.model = models[0] if models else None
                engine.server.gpus = tuple(_values(argv, "--gpus"))

    def remove(self, names: Sequence[str]) -> None:
        for name in names:
            engine = self.engines.pop(name, None)
            if engine is not None:
                engine.close()
        super().remove(names)


def main(argv: Sequence[str]) -> int:
    from mcgyvr.cli import main as cli_main
    from mcgyvr.rig import hardware, session
    from mcgyvr.rig import inventory as inventory_module
    from mcgyvr.sandbox import pooled

    machine = Machine.from_env()
    hardware.read = lambda **_: report(machine)
    inventory_module.read = lambda folder, **_: inventory(machine, folder)
    pooled.Pool = EngineDocker  # type: ignore[misc,assignment]
    if not machine.multi_session:
        # one feature fewer: the tuple's declared length does not hold
        session.FEATURES = tuple(  # type: ignore[assignment]
            f for f in session.FEATURES if f != session.MULTI_SESSION_FEATURE
        )
    return cli_main(list(argv))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
