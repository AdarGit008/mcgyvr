"""Reading a rig through the door: what is measured before anything is judged."""

from __future__ import annotations

import base64
import importlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, ClassVar

import yaml

from tests import onedoor
from tests._helpers import required
from tests._paths import REPO

GATE_SCRIPTS = REPO / "src" / "mcgyvr" / "serving" / "gate-scripts"


HARNESS_PY = REPO / "src" / "mcgyvr" / "fleet" / "harness.py"


#: box2 as it is locked, and what its snapshot must print to reproduce it
#: (``fleet-setup/digests-box2.json``).
LOCKED_BOX2 = "rig-3333333333333333333333333333333333333333333333333333333333333333"


BOX2_SYSTEM = {"os_machine_id": "6d5d8f1f2bfa5f96", "kernel": "7.0.0-31-generic"}


UNIT_3B = "unt-" + "5" * 64


UNIT_7B = "unt-" + "7" * 64


C_3B = "3b" * 32


C_7B = "7b" * 32


C_STRAY = "5a" * 32


C_OTHER = "0e" * 32


RUN_ID = "run-20260915T120000-0a1b2c3d"


FLEET_NAME = "b-small"


def _vllm(port: int, container: str, room: int, kv: int) -> dict[str, Any]:
    return {
        "rig": "box2",
        "engine": "vllm",
        "address": f"http://box2:{port}",
        "model": f"Qwen/unit-{port}",
        "container": container,
        "width": 8,
        "window": 4096,
        "output_tokens": 2048,
        "request_timeout_s": 180,
        "room_mib": room,
        "kv_cache_memory_bytes": kv,
        "attention_backend": "FLASH_ATTN",
    }


FLEET: dict[str, Any] = {
    "units": {
        "box2_3b": {
            **_vllm(8001, "mcgyvr-box2-3b", 3573, 1207959552),
            "unit_id": UNIT_3B,
        },
        "box2_7b": {
            **_vllm(8002, "mcgyvr-box2-7b", 8099, 1879048192),
            "unit_id": UNIT_7B,
        },
    },
    "rigs": {"box2": {"rig_id": LOCKED_BOX2}},
    "fleets": {
        FLEET_NAME: {
            "layout": {"box2": [["box2_3b", "awake"], ["box2_7b", "awake"]]},
            "next": [],
        }
    },
}


EVIDENCE: dict[str, Any] = {
    "rigs": {"box2": {"card_mib": 12288}},
    "combinations": [
        {
            "rig": "box2",
            "slots": [["box2_3b", "awake"], ["box2_7b", "awake"]],
            "passed": True,
            "overhead_mib": 610.5,
            "restarts": {"box2_3b": 0, "box2_7b": 0},
            "warm_decode_tok_s": {"box2_3b": 126.7, "box2_7b": 68.3},
            "prefill_tok_s": {"box2_3b": 11500.0, "box2_7b": 12059.0},
            "attention_backend": {"box2_3b": "FLASH_ATTN", "box2_7b": "FLASH_ATTN"},
            "validated_at": "2026-09-13T21:44:00Z",
            "envelope": "evidence/read-sample",
        }
    ],
    "moves": [],
}


TOLERANCES = {
    "warm_decode_class_pct": {"vllm": 1.0, "llamacpp": 1.0, "cpu_experts": 48.0}
}


def go_live(tmp_path: Path) -> Path:
    """Promote the fleet into this test's HOME, name it live, return its journal."""
    from mcgyvr.fleet import lock

    home = Path(os.environ["HOME"])
    folder = home / ".mcgyvr" / "fleets" / FLEET_NAME
    folder.mkdir(parents=True)
    (folder / "fleet.yaml").write_text(yaml.safe_dump(FLEET), encoding="utf-8")
    journal = tmp_path / "journal"
    policy = {"ladder": ["box2_3b", "box2_7b"], "journal": {"dir": str(journal)}}
    (folder / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")
    lock.write(folder, FLEET, EVIDENCE, tolerances=TOLERANCES)
    (home / ".mcgyvr" / "live.json").write_text(
        json.dumps({"fleet": FLEET_NAME}), encoding="utf-8"
    )
    return journal / "fleet"


def metrics(running: int) -> str:
    return (
        f'vllm:num_requests_running{{model_name="m"}} {running}.0\n'
        'vllm:num_requests_waiting{model_name="m"} 0.0\n'
    )


def page(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def reading(
    root: Path,
    *,
    snapshot: dict[str, str] | None = None,
    containers: tuple[str, ...] | None = None,
    gpu: tuple[str, ...] | None = None,
    sleeping: tuple[str, ...] = ("8001,false", "8002,none"),
    status: tuple[str, ...] = (),
) -> None:
    """What the stub rig answers the reader with: its snapshot and the rest."""
    lines = onedoor.snapshot_lines("box2", **(BOX2_SYSTEM | (snapshot or {})))
    for row in (
        containers
        if containers is not None
        else (
            f"mcgyvr-box2-3b,{C_3B},mcgyvr,0",
            f"mcgyvr-box2-7b,{C_7B},mcgyvr,unread",
            f"mcgyvr-box2-stray,{C_STRAY},mcgyvr,0",
            f"someone-elses,{C_OTHER},-,0",
        )
    ):
        lines += f"container={row}\n"
    for row in (
        gpu
        if gpu is not None
        else (
            f"4242,3400,{C_3B},python3",
            f"4343,7800,{C_7B},python3",
            "5555,1024,none,python3_train.py",
        )
    ):
        lines += f"gpu_app={row}\n"
    for row in sleeping:
        lines += f"sleeping={row}\n"
    for row in status:
        lines += f"status={row}\n"
    (onedoor.stubs_dir(root) / "snapshot.txt").write_text(lines, encoding="utf-8")


def read_door(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(root / onedoor.DOOR_REL), "read"]
    argv += ["--host", "box2"]
    argv += ["--run-id", RUN_ID, *args]
    return subprocess.run(
        argv,
        cwd=root,
        env=onedoor.door_env(root),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def rows(journal: Path) -> list[dict[str, Any]]:
    if not journal.is_dir():
        return []
    return [
        json.loads(line)
        for path in sorted(journal.rglob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def unit_rows(journal: Path, unit_id: str) -> dict[str, dict[str, Any]]:
    return {
        r["field"]: r
        for r in rows(journal)
        if r.get("unit_id") == unit_id and "field" in r
    }


def rig_row(journal: Path) -> dict[str, Any]:
    found = [r for r in rows(journal) if "observed_rig_id" in r]
    assert len(found) == 1, rows(journal)
    return found[0]


UNIT = "unt-" + "7" * 64


def seen(field: str, observed: float, unit_id: str = UNIT) -> dict[str, Any]:
    return {"unit_id": unit_id, "field": field, "observed": observed}


class _Unit(BaseHTTPRequestHandler):
    seen: ClassVar[list[str]] = []

    def log_message(self, *_: Any) -> None:
        return

    def _send(self, body: str, kind: str = "application/json") -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        self.seen.append(f"GET {self.path}")
        if self.path == "/v1/models":
            self._send(json.dumps({"data": [{"id": "m"}]}))
        else:
            self._send(metrics(0), "text/plain")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length))
        self.seen.append(f"POST {self.path} {payload['max_tokens']}")
        prompt = 1960 if payload["max_tokens"] == 16 else 20
        self._send(
            json.dumps(
                {
                    "usage": {
                        "completion_tokens": payload["max_tokens"],
                        "prompt_tokens": prompt,
                    }
                }
            )
        )


LOAD = "8x4096"


def rig_text(
    *,
    card_3b: int = 3400,
    restarts_7b: str = "0",
    status: tuple[str, ...] = (f"8001,{page(metrics(0))}",),
    backend: tuple[str, ...] = ("8001,FLASH_ATTN", "8002,FLASH_ATTN"),
) -> str:
    """One reader's output for box2 with both units up."""
    lines = onedoor.snapshot_lines("box2", **BOX2_SYSTEM)
    lines += f"container=mcgyvr-box2-3b,{C_3B},mcgyvr,0\n"
    lines += f"container=mcgyvr-box2-7b,{C_7B},mcgyvr,{restarts_7b}\n"
    lines += f"gpu_app=4242,{card_3b},{C_3B},python3\n"
    lines += f"gpu_app=4343,7800,{C_7B},python3\n"
    lines += "sleeping=8001,false\nsleeping=8002,false\n"
    lines += "".join(f"status={row}\n" for row in status)
    lines += "".join(f"backend={row}\n" for row in backend)
    return lines


class Rig:
    """The harness on the rig: the lock's probe, and a load of the unit."""

    def __init__(
        self, load_mib: tuple[int, ...] = (3000, 3500, 3100), completed: int = 8
    ) -> None:
        self.load_mib = load_mib
        self.completed = completed
        self.specs: list[dict[str, Any]] = []

    def __call__(self, unit: str, spec: str) -> str:
        asked = json.loads(spec)
        self.specs.append(asked)
        if asked.get("mode") == "load":
            samples = [
                f"gpu_app=4242,{mib},{C_3B},python3\ngpu_app=4343,7800,{C_7B},python3\n"
                for mib in self.load_mib
            ]
            return json.dumps(
                {
                    "load": {
                        "prompt_tokens": 4032,
                        "max_tokens": 64,
                        "completed": self.completed,
                        "errors": [],
                        "started_at": "2026-09-15T12:00:05",
                        "finished_at": "2026-09-15T12:00:41",
                        "samples": samples,
                        "restarts_before": "0",
                        "restarts_after": "0",
                    }
                }
            )
        return json.dumps(
            {
                "figures": {"warm_decode_tok_s": 126.7, "prefill_tok_s": 11500.0},
                "after_page": metrics(0),
            }
        )


def record(text: str, rig: Rig, **more: Any) -> Any:
    from mcgyvr.fleet import read

    return read.record(
        "box2",
        *onedoor.split_reading(text),
        run_id=RUN_ID,
        probe=("box2_3b",),
        measure=rig,
        **more,
    )


def _load_rows(journal: Path) -> list[dict[str, Any]]:
    return [
        row
        for path in sorted(journal.rglob("*.jsonl"))
        for row in map(json.loads, path.read_text(encoding="utf-8").splitlines())
        if row.get("field") == "load_peak_mib"
    ]


RIG2 = "rig-" + "2" * 64


CMB = "cmb-" + "a" * 64


SWITCH = "flt-05 -> flt-02"


ALERT_RUN_ID = "run-20260911T120000-0a1b2c3d"


LEASE_ID = "lease-0a1b2c3d"


STAMP: dict[str, str] = {
    "fleet": "flt-05",
    "rig_id": RIG2,
    "combination_id": CMB,
    "unit_id": UNIT,
}


#: Placeholder locked values and tolerances, per unit or switch and parameter.
APPROVED: dict[str, dict[str, dict[str, Any]]] = {
    UNIT: {
        "warm_decode_tok_s": {"expected": 30.0, "tolerance": {"pct": 10.0}},
        "card_steady_mib": {"expected": 7000.0, "tolerance": {"abs": 32.0}},
        "card_peak_mib": {"expected": 7026.0, "tolerance": {"abs": 32.0}},
        "prefill_tok_s": {"expected": 440.0, "tolerance": {"pct": 5.0}},
        "l2_wake_s": {"expected": 0.25, "tolerance": {"s": 0.1}},
    },
    SWITCH: {"downtime_s": {"expected": 0.3, "tolerance": {"s": 1.0}}},
}


def _alerts() -> Any:
    return required(
        "judge observations against their locked values, pull a combination on a "
        "live alert, and clear it only on a re-committed validation",
        lambda: importlib.import_module("mcgyvr.fleet.alerts"),
    )


def check(
    alerts: Any,
    observations: Sequence[Mapping[str, Any]],
    journal: Path,
    *,
    stamp: Mapping[str, str] = STAMP,
    run_id: str = ALERT_RUN_ID,
    approved: Mapping[str, Any] = APPROVED,
) -> list[dict[str, Any]]:
    return list(
        alerts.check(
            observations,
            approved=approved,
            journal_dir=journal,
            stamp=stamp,
            run_id=run_id,
            lease_id=LEASE_ID,
        )
    )


def alert_rows(journal: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for path in journal.rglob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
