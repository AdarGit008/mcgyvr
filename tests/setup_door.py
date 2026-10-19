"""An invented rig behind the door, and an interactive setup that reaches it.

The fixture the setup-flow tests share. Every door call of ``mcgyvr setup``
goes through :func:`mcgyvr.wake.spawn_door`, the one seam a product caller
opens the door by, and here it is :class:`FakeRig`: it keeps which containers
are up, and answers a ``read`` by filing rows with the product's own
:func:`mcgyvr.fleet.read.record`, from canned reader text and a stand-in
harness. The steps that would read a real machine (the rig read, the plan, the
sizing and the emit) are substituted by :func:`interactive`; ``initialize``,
the sampler, the stamp, the lock, the promotion and ``live.json`` are the
product's own. Nothing reaches a machine.
"""

from __future__ import annotations

import argparse
import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests import onedoor
from tests import sample_fleet as fx

RIG = "rig-s"
MODEL = "example-org/Coder-S-GGUF"
WINDOW = 8192
ROOM_MIB = 6000
CARD_MIB = 12288
SNAPSHOT: dict[str, str] = {**fx.SNAPSHOT, "hostname": RIG}
WARM = 41.5


def reading() -> dict[str, Any]:
    """The one reader's document of the invented rig, as setup's read takes it."""
    doc: dict[str, Any] = dict(onedoor.machine_reading(SNAPSHOT))
    doc["gpus"] = [
        {
            "index": card["index"],
            "name": card["name"],
            "vram": {
                "total_mib": card["total_mib"],
                "used_mib": card["used_mib"],
                "free_mib": card["free_mib"],
            },
        }
        for card in doc["cards"]
    ]
    doc.setdefault("memory", {"total_gb": 64.0, "available_gb": 60.0})
    doc.setdefault("disk", {"path": "/", "free_gb": 500.0})
    doc["docker"] = SNAPSHOT["docker"]
    doc["snapshot"] = dict(SNAPSHOT)
    return doc


def _container_id(name: str) -> str:
    return (name.encode("utf-8").hex() * 4)[:12]


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


@dataclass
class FakeRig:
    """The rig behind the door: containers up, reads filed.

    With ``gate_1`` a ``serve up`` first passes the door's own gate 1 check
    (:func:`gate_1`), and a refusal there is the door's exit status: the
    containers stay down.
    """

    gate_1: bool = False
    gate_1_said: list[tuple[str, int]] = field(default_factory=list)
    serve_fails: bool = False
    read_fails: bool = False
    warm: float = WARM
    calls: list[tuple[Any, ...]] = field(default_factory=list)
    configs: list[str | None] = field(default_factory=list)
    up: set[str] = field(default_factory=set)

    def __call__(self, argv: Any, **kwargs: Any) -> int:
        from mcgyvr.serving.gatelib import DOOR_MODULE

        args = [str(a) for a in argv]
        env = dict(kwargs.get("env") or {})
        self.configs.append(env.get("MCGYVR_CONFIG"))
        verb = args[args.index(DOOR_MODULE) + 1 :]
        if verb[0] == "serve":
            return self._serve(verb[1], verb[2:], env)
        assert verb[0] == "read", args
        return self._read(verb[1:], Path(env["MCGYVR_CONFIG"]))

    def _serve(self, direction: str, rest: list[str], env: dict[str, str]) -> int:
        parser = argparse.ArgumentParser()
        for flag in ("--mode", "--host", "--compose", "--suffix"):
            parser.add_argument(flag)
        parser.add_argument("--unit", action="append", default=[])
        opts = parser.parse_args(rest)
        compose = Path(opts.compose)
        self.calls.append(("serve", direction, opts.host, compose.name, *opts.unit))
        if self.serve_fails:
            return 1
        if self.gate_1 and direction == "up":
            held, status = gate_1(env, opts.host, compose, opts.unit)
            self.gate_1_said.append((held, status))
            if status:
                return status
        services = yaml.safe_load(compose.read_text(encoding="utf-8"))["services"]
        named = set(opts.unit) or {s["container_name"] for s in services.values()}
        if direction in ("up", "wake"):
            self.up |= named
        else:
            self.up -= named
        return 0

    def _read(self, rest: list[str], setup: Path) -> int:
        from mcgyvr.fleet import read

        parser = argparse.ArgumentParser()
        for flag in ("--host", "--fleet", "--run-id", "--load"):
            parser.add_argument(flag)
        parser.add_argument("--probe", nargs="+", default=[])
        opts = parser.parse_args(rest)
        self.calls.append(("read", opts.host, opts.fleet, tuple(opts.probe), opts.load))
        if self.read_fails:
            return 1
        doc = yaml.safe_load((setup / "fleet.yaml").read_text(encoding="utf-8"))
        read.record(
            opts.host,
            *onedoor.split_reading(self._reader(doc, opts.fleet, opts.host)),
            run_id=opts.run_id,
            probe=tuple(opts.probe),
            measure=self._measure(doc),
            load=opts.load,
            fleet_name=opts.fleet,
            setup=setup,
        )
        return 0

    def _reader(self, doc: dict[str, Any], fleet: str, rig: str) -> str:
        lines = "".join(f"{k}={v}\n" for k, v in SNAPSHOT.items())
        for slot in doc["fleets"][fleet]["layout"][rig]:
            unit = doc["units"][slot[0]]
            if unit["container"] not in self.up:
                continue
            cid = _container_id(unit["container"])
            port = int(
                unit["address"].rstrip("/").removesuffix("/v1").rsplit(":", 1)[1]
            )
            lines += f"container={unit['container']},{cid},mcgyvr,0\n"
            lines += f"gpu_app=4{port},{unit['room_mib'] - 600},{cid},llama-server\n"
            lines += f"status={port},{_b64(fx.slots_page())}\n"
        return lines

    def _measure(self, doc: dict[str, Any]) -> Any:
        def measure(name: str, spec: str) -> str:
            unit = doc["units"][name]
            cid = _container_id(unit["container"])
            peak = unit["room_mib"] - 400
            if json.loads(spec).get("mode") == "load":
                return json.dumps(
                    {
                        "load": {
                            "prompt_tokens": 100,
                            "max_tokens": 64,
                            "completed": 1,
                            "errors": [],
                            "started_at": "2026-10-05T10:00:05",
                            "finished_at": "2026-10-05T10:00:40",
                            "samples": [f"gpu_app=1,{peak},{cid},llama-server\n"],
                            "restarts_before": "0",
                            "restarts_after": "0",
                            "after_page": fx.slots_page(),
                        }
                    }
                )
            return json.dumps(
                {
                    "figures": {"warm_decode_tok_s": self.warm, "prefill_tok_s": 800.0},
                    "after_page": fx.slots_page(),
                }
            )

        return measure


def gate_1(
    env: dict[str, str], host: str, compose: Path, units: list[str]
) -> tuple[str, int]:
    """The door's gate 1 on a ``serve up`` of ``compose`` on ``host``, in this
    process: ``live`` when the run was held to the live lock, and ``0``
    admitted or the status it refused with.

    Under the variables the door sets (``src/mcgyvr/serving/run.py``): the
    containers the launch spec declares, and the ``--unit`` ones alone when
    named.
    """
    import os
    from unittest import mock

    from tests._helpers import by_path
    from tests._paths import REPO

    gate = by_path(
        "gate_01_config",
        REPO / "src" / "mcgyvr" / "serving" / "gate-scripts" / "01-config.py",
    )
    door = {
        **os.environ,
        **env,
        "RUN_HOST": host,
        "RUN_SERVE": "up",
        "RUN_SERVE_EXPECTED": " ".join(
            service["container_name"]
            for service in yaml.safe_load(compose.read_text(encoding="utf-8"))[
                "services"
            ].values()
        ),
        "RUN_SERVE_ONLY": " ".join(sorted(set(units))),
    }
    with mock.patch.dict(os.environ, door, clear=True):
        try:
            source = gate.config()
            gate.refuse_unless_the_fleet_lock_names("up", source)
            from mcgyvr.fleet.roots import runs_live

            held = source == "none" or runs_live(Path(source))
        except SystemExit as refused:
            return "refused", int(refused.code or 1)
    return ("live" if held else "not held"), 0


def accepted(argv: list[str], *, outcome: str = "accepted") -> int:
    """``mcgyvr run`` answered with a result file: ``outcome`` on the first rung."""
    where = Path(argv[argv.index("--result") + 1])
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(
        json.dumps(
            {
                "outcome": outcome,
                "rung": "llama-server",
                "detail": "" if outcome == "accepted" else "2 of 2 failed",
                "attempts": [],
            }
        ),
        encoding="utf-8",
    )
    return 0 if outcome == "accepted" else 1


def _emit(path: Path, ctx: int) -> None:
    """What ``mcgyvr emit`` leaves: a launch spec per rig, stamped back into
    ``fleet.yaml`` as each unit's container and launch."""
    from mcgyvr.serving import spec_name

    fleet_path = path / "fleet.yaml"
    doc = yaml.safe_load(fleet_path.read_text(encoding="utf-8"))
    services: dict[str, Any] = {}
    for name, unit in doc["units"].items():
        if "rig" not in unit:
            continue
        container = f"mcgyvr-{unit['rig']}-{name}"
        unit.setdefault("container", container)
        unit.setdefault("image", "example/llama:tag")
        unit.setdefault("launch", {"argv": ["--ctx-size", str(ctx)], "env": {}})
        services[name] = {"container_name": container, "image": "example/llama:tag"}
    fleet_path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    (path / spec_name(RIG)).write_text(
        yaml.safe_dump({"services": services}), encoding="utf-8"
    )


def interactive(
    monkeypatch: pytest.MonkeyPatch,
    rig: FakeRig,
    answers: dict[str, bool],
    *,
    typed: dict[str, str] | None = None,
) -> list[str]:
    """Substitute every step of the interactive setup that reads a machine,
    open the door onto ``rig``, and answer each confirm by the first key of
    ``answers`` its question holds, and each typed question by the first key
    of ``typed`` it holds (Enter, the empty answer, when none does). The
    questions asked, in order."""
    from mcgyvr import cli, wake
    from mcgyvr.scan import Scan
    from mcgyvr.serving import rigfile

    asked: list[str] = []

    def scan_rigs(rigs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        doc = reading()
        rigfile.save(RIG, doc)
        return {RIG: Scan.from_json(json.dumps(doc))}, {RIG: doc}

    def confirm(question: str, prompt: Any = None) -> bool:
        asked.append(question)
        return next((yes for key, yes in answers.items() if key in question), False)

    def ask(question: str, prompt: Any = None) -> str:
        asked.append(question)
        return next(
            (said for key, said in (typed or {}).items() if key in question), ""
        )

    plan = {
        RIG: {
            "placement": {
                "model_id": MODEL,
                "quant": "Q4_K_M",
                "engine": "llama.cpp",
                "context_length": WINDOW,
            }
        }
    }
    monkeypatch.setattr(cli.commands.setup, "_stdin_isatty", lambda: True)
    monkeypatch.setattr(
        cli.commands.setup, "_ask_setup_rigs", lambda prompt=None: (RIG,)
    )
    monkeypatch.setattr(cli.commands.setup, "_setup_scan_rigs", scan_rigs)
    monkeypatch.setattr(
        cli.commands.setup, "_setup_placements", lambda rigs, scans, use_case: plan
    )
    monkeypatch.setattr(
        cli.commands.setup, "_setup_downloads", lambda plans, scans, prompt=None: ()
    )
    monkeypatch.setattr(
        cli.commands.setup,
        "_setup_rooms",
        lambda path, ctx: {
            name: ROOM_MIB
            for name, unit in yaml.safe_load(
                (path / "fleet.yaml").read_text(encoding="utf-8")
            )["units"].items()
            if "rig" in unit
        },
    )
    monkeypatch.setattr(cli.commands.setup, "_setup_emit", _emit)
    monkeypatch.setattr(cli.commands.setup, "_confirm", confirm)
    monkeypatch.setattr(cli.commands.setup, "_ask", ask)
    monkeypatch.setattr(wake, "spawn_door", rig)
    monkeypatch.setattr(cli.commands.setup, "_setup_run_contract", accepted)
    # The PATH-append offer runs only after a real successful setup; the
    # flow tests answer the prompts they care about, so keep it from touching
    # the real login shell rc file.
    monkeypatch.setattr(cli.commands.setup, "_offer_path_append", lambda: None)
    return asked
