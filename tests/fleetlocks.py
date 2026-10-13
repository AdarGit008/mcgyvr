"""A fleet's lock: what writes one, what reads one, and what a promotion carries."""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.doors import UNITS
from tests.red_port.conftest import required

RIG2 = "rig-" + "2" * 64


U3B = "unt-" + "3" * 64


U7B = "unt-" + "7" * 64


#: srv2's room slots, in order: slot 0 the 7B, slot 1 the 3B.
FLT05: list[Any] = [["srv2_7b", "awake"], ["srv2_3b", "asleep"]]


FLT02: list[Any] = [["srv2_7b", "awake"], ["srv2_3b", "awake"]]


FLEET: dict[str, Any] = {
    "rigs": {"srv2": {"rig_id": RIG2}},
    "units": {
        "srv2_7b": {
            "rig": "srv2",
            "unit_id": U7B,
            "engine": "vllm",
            "address": "http://srv2:8002",
            "room_mib": 6800,
            "kv_cache_memory_bytes": 2_147_483_648,
            "attention_backend": "FLASH_ATTN",
            "width": 8,
            "window": 4096,
            "output_tokens": 1024,
            "request_timeout_s": 180.0,
        },
        "srv2_3b": {
            "rig": "srv2",
            "unit_id": U3B,
            "engine": "vllm",
            "address": "http://srv2:8001",
            "room_mib": 2800,
            "kv_cache_memory_bytes": 452_984_832,
            "attention_backend": "FLASH_ATTN",
            "width": 8,
            "window": 4096,
            "output_tokens": 1024,
            "request_timeout_s": 180.0,
        },
        "cloud": {"address": "https://api.example.invalid/v1"},
    },
    "fleets": {
        "flt-05": {"layout": {"srv2": FLT05}, "next": ["flt-02"]},
        "flt-02": {"layout": {"srv2": FLT02}, "next": ["flt-05"]},
    },
}


EVIDENCE: dict[str, Any] = {
    "rigs": {"srv2": {"card_mib": 12000}},
    "combinations": [
        {
            "rig": "srv2",
            "slots": FLT05,
            "passed": True,
            "overhead_mib": 600,
            "restarts": {"srv2_7b": 0, "srv2_3b": 0},
            "warm_decode_tok_s": {"srv2_7b": 58.0},
            "baseline_tok_s": {"srv2_7b": 58.4},
            "prefill_tok_s": {"srv2_7b": 1450.0},
            "attention_backend": {"srv2_7b": "FLASH_ATTN", "srv2_3b": "FLASH_ATTN"},
            "validated_at": "2026-09-11T10:00:00Z",
            "envelope": "records/evidence/2026-09-11-fleet-srv2/flt-05",
        },
        {
            "rig": "srv2",
            "slots": FLT02,
            "passed": True,
            "overhead_mib": 600,
            "restarts": {"srv2_7b": 0, "srv2_3b": 0},
            "warm_decode_tok_s": {"srv2_7b": 57.0, "srv2_3b": 105.0},
            "baseline_tok_s": {"srv2_7b": 57.4, "srv2_3b": 106.0},
            "prefill_tok_s": {"srv2_7b": 1420.0, "srv2_3b": 3100.0},
            "attention_backend": {"srv2_7b": "FLASH_ATTN", "srv2_3b": "FLASH_ATTN"},
            "validated_at": "2026-09-11T10:30:00Z",
            "envelope": "records/evidence/2026-09-11-fleet-srv2/flt-02",
        },
    ],
    "moves": [
        {
            "rig": "srv2",
            "from": FLT05,
            "to": FLT02,
            "passed": True,
            "downtime_s": 0.3,
            "wake_s": {"srv2_3b": 0.25},
        },
        {
            "rig": "srv2",
            "from": FLT02,
            "to": FLT05,
            "passed": True,
            "downtime_s": 0.5,
            "wake_s": {},
        },
    ],
}


POLICY: dict[str, Any] = {"ladder": ["srv2_3b", "srv2_7b", "cloud"]}


#: Placeholder tolerances: the rule is pinned here, the values are measured.
TOLERANCES: dict[str, Any] = {
    "warm_decode_class_pct": {"vllm": 3.0, "llamacpp": 5.0, "cpu_experts": 5.0}
}


def _lock() -> Any:
    return required(
        "write the fleet lock from passing dev runs, refusing what it cannot pin",
        lambda: importlib.import_module("mcgyvr.fleet.lock"),
    )


def write(
    lock: Any,
    root: Path,
    fleet: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> Any:
    return lock.write(
        root,
        FLEET if fleet is None else fleet,
        EVIDENCE if evidence is None else evidence,
        policy=POLICY if policy is None else policy,
        tolerances=TOLERANCES,
    )


def edited(original: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(original)


def combination_files(root: Path) -> list[Path]:
    return sorted((root / "records" / "fleet" / "rigs" / RIG2).glob("cmb-*.json"))


#: The fixture's two llama.cpp units on srv1, as the lock names them.
SLOTS: list[Any] = [["a", "awake"], ["b", "awake"]]


SRV1_FLEET: dict[str, Any] = {
    "rigs": {"srv1": {"rig_id": "rig-" + "1" * 64}},
    "units": {
        name: {
            "rig": "srv1",
            "unit_id": "unt-" + digit * 64,
            "engine": "llama.cpp",
            "address": f"http://srv1:{8001 + index}",
            "container": container,
            "image": "llamacpp:b10644-L3",
            "command": ["--model", "/models/x.gguf", "--port", str(8001 + index)],
            "room_mib": 2000,
            "width": 1,
            "window": 4096,
            "output_tokens": 512,
            "request_timeout_s": 120.0,
        }
        for index, (name, digit, container) in enumerate(
            (("a", "a", UNITS[0]), ("b", "b", UNITS[1]))
        )
    },
    "fleets": {"flt-01": {"layout": {"srv1": SLOTS}, "next": []}},
}


SRV1_EVIDENCE: dict[str, Any] = {
    "rigs": {"srv1": {"card_mib": 6144, "overhead_mib": 400}},
    "combinations": [
        {
            "rig": "srv1",
            "slots": SLOTS,
            "passed": True,
            "overhead_mib": 400,
            "restarts": {"a": 0, "b": 0},
            "warm_decode_tok_s": {"a": 20.0, "b": 20.0},
            "baseline_tok_s": {"a": 20.5, "b": 20.5},
            "card_peak_mib": {"a": 2000, "b": 2000},
            "prefill_tok_s": {"a": 1450.0, "b": 1450.0},
            "validated_at": "2026-09-11T10:00:00Z",
            "envelope": "records/evidence/2026-09-11-fleet-srv1/flt-01",
        }
    ],
    "moves": [],
}


#: The lock fixture's fleet, every unit naming a model so a folder loads.
MODELLED: dict[str, Any] = copy.deepcopy(FLEET)


#: The dev policy a setup directory holds: a ladder over every unit, and one
#: other key that promotion copies as it is.
SETUP_POLICY: dict[str, Any] = {"ladder": list(POLICY["ladder"]), "fanout": "idle"}


def _flow_lock() -> Any:
    return importlib.import_module("mcgyvr.fleet.lock")


def home() -> Path:
    return Path.home() / ".mcgyvr"


def fleets() -> Path:
    return home() / "fleets"


def live_json() -> Path:
    return home() / "live.json"


def name_live(fleet: str) -> None:
    live_json().parent.mkdir(parents=True, exist_ok=True)
    live_json().write_text(
        json.dumps({"fleet": fleet, "since": "2026-09-15T00:00:00+00:00"}),
        encoding="utf-8",
    )


def tree(root: Path) -> dict[str, bytes]:
    """Every file under ``root``, by relative path, with its bytes."""
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def listing(root: Path) -> list[str]:
    """Every file and directory under ``root``, empty ones included."""
    if not root.exists():
        return []
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


def dev_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    locked_fleet: dict[str, Any] = MODELLED,
    file_fleet: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """A dev root holding a lock of ``locked_fleet``, and a setup directory."""
    dev = tmp_path / "dev"
    _flow_lock().write(
        dev, locked_fleet, EVIDENCE, policy=POLICY, tolerances=TOLERANCES
    )
    monkeypatch.setenv("MCGYVR_RUN_ROOT", str(dev))
    setup = tmp_path / "setup"
    setup.mkdir()
    (setup / "fleet.yaml").write_text(
        yaml.safe_dump(
            {"profile": "dev", **(locked_fleet if file_fleet is None else file_fleet)},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (setup / "policy.yaml").write_text(
        yaml.safe_dump(SETUP_POLICY, sort_keys=False), encoding="utf-8"
    )
    return dev, setup


def cli(*argv: str) -> int:
    from mcgyvr.cli import main

    try:
        return main(list(argv))
    except SystemExit as exited:
        pytest.fail(
            f"mcgyvr must be able to: `mcgyvr {' '.join(argv)}`\n"
            f"  argparse exited {exited.code}",
            pytrace=False,
        )


#: The fixture lock's date, which promote tags each folder with.
LOCK_DATE = "2026-09-11"


def flt05_records() -> tuple[str, str]:
    from mcgyvr.fleet.layout import combination_id

    cmb = combination_id(RIG2, [(U7B, "awake"), (U3B, "asleep")])
    return "records/fleet/flt-05.json", f"records/fleet/rigs/{RIG2}/{cmb}.json"


def locked(
    root: Path,
    fleet: dict[str, Any] = FLEET,
    evidence: dict[str, Any] = EVIDENCE,
) -> Path:
    lock = required(
        "write the fleet lock from passing dev runs, refusing what it cannot pin",
        lambda: importlib.import_module("mcgyvr.fleet.lock"),
    )
    lock.write(root, fleet, evidence, policy=POLICY, tolerances=TOLERANCES)
    return root


def observed(
    units: dict[str, str] | None = None,
    *,
    rig_id: str = RIG2,
    foreign: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "srv2": {
            "rig_id": rig_id,
            "units": {U7B: "awake", U3B: "asleep"} if units is None else units,
            "foreign": foreign or [],
        }
    }


FLEET_YAML = """\
units:
  srv2_7b:
    rig: srv2
    unit_id: unt-7777777777777777777777777777777777777777777777777777777777777777
    engine: vllm
    address: http://srv2:8002
    model: Qwen/Qwen2.5-Coder-7B-Instruct-AWQ
    room_mib: 6800
    kv_cache_memory_bytes: 2147483648
    attention_backend: FLASH_ATTN
    width: 8
    window: 4096
    output_tokens: 1024
    request_timeout_s: 180
rigs:
  srv2:
    rig_id: rig-2222222222222222222222222222222222222222222222222222222222222222
fleets:
  flt-05:
    layout: {srv2: [[srv2_7b, awake]]}
    next: []
"""


YAML_EVIDENCE = {
    "rigs": {"srv2": {"card_mib": 12000}},
    "combinations": [
        {
            "rig": "srv2",
            "slots": [["srv2_7b", "awake"]],
            "passed": True,
            "overhead_mib": 600,
            "restarts": {"srv2_7b": 0},
            "warm_decode_tok_s": {"srv2_7b": 58.0},
            "baseline_tok_s": {"srv2_7b": 58.4},
            "prefill_tok_s": {"srv2_7b": 1450.0},
            "attention_backend": {"srv2_7b": "FLASH_ATTN"},
            "validated_at": "2026-09-11T10:00:00Z",
        }
    ],
    "moves": [],
}
