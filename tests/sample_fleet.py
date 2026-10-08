"""An invented rig, a staged setup of one fleet on it, and the door's reads of it.

The fixture the sample-and-stamp tests share. Nothing reaches a machine: the
rig is invented (``rig-a``, an example CPU and card), its reader output is
canned text, and the harness on it is a stand-in. The read rows a sample is
judged from are filed by the product's own :func:`mcgyvr.fleet.read.record`,
exactly as ``python -m mcgyvr.serving.run read --fleet F --probe U --load WxN``
files them under the staged setup's journal.
"""

from __future__ import annotations

import base64
import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RIG = "rig-a"
FLEET = "coding-rig-a"
#: The fleet the strong rung's swap is stamped as, beside :data:`FLEET`.
STRONG_FLEET = "coding-rig-a-strong"
UNIT = "rig-a-coder-s-8081"
STRONG = "rig-a-coder-l-8082"
UNIT_ID = "unt-" + "a" * 64
STRONG_ID = "unt-" + "b" * 64
CONTAINER = "mcgyvr-rig-a-coder-s-8081"
CONTAINER_ID = "c0ffee000001"
STRONG_CONTAINER = "mcgyvr-rig-a-coder-l-8082"
STRONG_CONTAINER_ID = "c0ffee000002"
#: Two reads of the sample, a minute apart: before the task, and after it.
READS = ("run-20261005T100000-0000000a", "run-20261005T100100-0000000b")
#: Two reads of the strong fleet, once the swap woke its strong rung.
STRONG_READS = ("run-20261005T100200-0000000c", "run-20261005T100300-0000000d")
#: The day the sample's last read was taken, which the stamp is dated by.
SAMPLE_DAY = "2026-10-05"
LOAD = "4x8192"

#: One ``rig-snapshot.sh`` reading of the invented rig.
SNAPSHOT: dict[str, str] = {
    "hostname": RIG,
    "cpu_model": "Example_CPU_8_core",
    "cpu_max_mhz": "4000",
    "ram_mt_s": "3200",
    "pl1_uw": "65000000",
    "pl2_uw": "0",
    "gpu_name": "Example_GPU_12GB",
    "gpu_vram_mib": "12288",
    "gpu_cc": "8.6",
    "gpu_slot": "0000:01:00.0",
    "os_machine_id": "machine-of-rig-a",
    "kernel": "6.0.0-example",
    "driver": "500.00",
    "docker": "27.0.0",
    "gpu_reserve_mib": "310",
}


def rig_id(snapshot: dict[str, str] | None = None) -> str:
    from mcgyvr.fleet import ids

    return ids.rig_id(SNAPSHOT if snapshot is None else snapshot)


def unit(
    name: str = UNIT,
    unit_id: str = UNIT_ID,
    port: int = 8081,
    container: str = CONTAINER,
    room_mib: int = 6000,
    role: str | None = None,
) -> dict[str, Any]:
    block = {
        "rig": RIG,
        "unit_id": unit_id,
        "engine": "llama.cpp",
        "address": f"http://{RIG}:{port}",
        "model": "example/Coder-S-GGUF",
        "width": 4,
        "window": 8192,
        "output_tokens": 1024,
        "request_timeout_s": 180.0,
        "room_mib": room_mib,
        "container": container,
    }
    if role is not None:
        block["role"] = role
    return block


def fleet_doc(*, asleep: bool = False) -> dict[str, Any]:
    """The staged ``fleet.yaml``: one rung awake, and with ``asleep`` a strong
    rung that sleeps until needed beside it."""
    units = {UNIT: unit()}
    slots: list[Any] = [[UNIT, "awake"]]
    if asleep:
        units[STRONG] = unit(STRONG, STRONG_ID, 8082, STRONG_CONTAINER, room_mib=5000)
        slots.append([STRONG, "asleep"])
    return {
        "profile": "dev",
        "units": units,
        "rigs": {RIG: {"rig_id": rig_id()}},
        "fleets": {FLEET: {"layout": {RIG: slots}, "next": []}},
    }


def swap_doc() -> dict[str, Any]:
    """The staged ``fleet.yaml`` of a swap (owner, Round 8): the fast rung
    awake in :data:`FLEET`, the strong rung -- ``role: sleeps-until-needed`` --
    awake in its slot in :data:`STRONG_FLEET`, each fleet in the other's
    ``next``."""
    return {
        "profile": "dev",
        "units": {
            UNIT: unit(role="always-on"),
            STRONG: unit(
                STRONG,
                STRONG_ID,
                8082,
                STRONG_CONTAINER,
                room_mib=5000,
                role="sleeps-until-needed",
            ),
        },
        "rigs": {RIG: {"rig_id": rig_id()}},
        "fleets": {
            FLEET: {"layout": {RIG: [[UNIT, "awake"]]}, "next": [STRONG_FLEET]},
            STRONG_FLEET: {"layout": {RIG: [[STRONG, "awake"]]}, "next": [FLEET]},
        },
    }


def policy_doc(tmp_path: Path, use_case: str = "coding") -> dict[str, Any]:
    return {
        "use_case": use_case,
        "ladder": [UNIT],
        "journal": {"dir": str(tmp_path / "journal")},
    }


def swap_policy(tmp_path: Path) -> dict[str, Any]:
    """The policy of :func:`swap_doc`: its ladder climbs to the strong rung."""
    return {**policy_doc(tmp_path), "ladder": [UNIT, STRONG]}


def staged(
    tmp_path: Path,
    *,
    fleet: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> Path:
    """The staged setup a sample runs on: ``fleet.yaml`` and ``policy.yaml``."""
    folder = tmp_path / "staged"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "fleet.yaml").write_text(
        yaml.safe_dump(fleet_doc() if fleet is None else fleet, sort_keys=False),
        encoding="utf-8",
    )
    (folder / "policy.yaml").write_text(
        yaml.safe_dump(
            policy_doc(tmp_path) if policy is None else policy, sort_keys=False
        ),
        encoding="utf-8",
    )
    return folder


def rig_file(cards: tuple[int, ...] = (12288,)) -> Path:
    """Write the invented rig's file under the config folder, as setup's scan does."""
    from mcgyvr.serving import rigfile

    return rigfile.write(
        rigfile.Rig(
            rig=RIG,
            read_at="2026-10-05T09:59:00Z",
            hostname=RIG,
            machine_id=SNAPSHOT["os_machine_id"],
            cards=tuple(
                rigfile.Card(index=index, name="Example GPU 12GB", total_mib=mib)
                for index, mib in enumerate(cards)
            ),
            ram_total_gb=64.0,
            disk_path="/",
            disk_free_gb=500.0,
            docker=SNAPSHOT["docker"],
        )
    )


def slots_page(busy: bool = False) -> str:
    return json.dumps([{"id": 0, "is_processing": busy}])


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def reader_text(
    *,
    card_mib: int = 5400,
    restarts: str = "0",
    snapshot: dict[str, str] | None = None,
    strong: bool = False,
    strong_only: bool = False,
) -> str:
    """What the reader prints for the invented rig with the fast rung up, or
    with ``strong_only`` the strong rung alone, swapped in."""
    values = SNAPSHOT if snapshot is None else snapshot
    lines = "".join(f"{key}={value}\n" for key, value in values.items())
    if strong_only:
        lines += f"container={STRONG_CONTAINER},{STRONG_CONTAINER_ID},mcgyvr,{restarts}\n"
        lines += f"gpu_app=4343,{card_mib},{STRONG_CONTAINER_ID},llama-server\n"
        lines += f"status=8082,{_b64(slots_page())}\n"
        return lines
    lines += f"container={CONTAINER},{CONTAINER_ID},mcgyvr,{restarts}\n"
    lines += f"gpu_app=4242,{card_mib},{CONTAINER_ID},llama-server\n"
    lines += f"status=8081,{_b64(slots_page())}\n"
    if strong:
        lines += f"container={STRONG_CONTAINER},{STRONG_CONTAINER_ID},mcgyvr,0\n"
        lines += f"status=8082,{_b64(slots_page())}\n"
    return lines


@dataclass
class Harness:
    """The lock's harness on the rig, as a stand-in: a probe and a load."""

    warm: float = 41.5
    prefill: float = 900.0
    load_mib: tuple[int, ...] = (5300, 5600, 5450)
    fails: str | None = None
    container_id: str = CONTAINER_ID
    specs: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, name: str, spec: str) -> str:
        asked = json.loads(spec)
        self.specs.append(asked)
        if self.fails is not None:
            return json.dumps({"error": self.fails})
        if asked.get("mode") == "load":
            return json.dumps(
                {
                    "load": {
                        "prompt_tokens": 8000,
                        "max_tokens": 64,
                        "completed": 4,
                        "errors": [],
                        "started_at": "2026-10-05T10:00:05",
                        "finished_at": "2026-10-05T10:00:40",
                        "samples": [
                            f"gpu_app=4242,{mib},{self.container_id},llama-server\n"
                            for mib in self.load_mib
                        ],
                        "restarts_before": "0",
                        "restarts_after": "0",
                        "after_page": slots_page(),
                    }
                }
            )
        return json.dumps(
            {
                "figures": {
                    "warm_decode_tok_s": self.warm,
                    "prefill_tok_s": self.prefill,
                },
                "after_page": slots_page(),
            }
        )


def read(
    setup: Path,
    run_id: str,
    *,
    text: str | None = None,
    harness: Harness | None = None,
    load: str | None = LOAD,
    probe: tuple[str, ...] = (UNIT,),
    fleet: str = FLEET,
) -> Any:
    """One door read of the invented rig under the staged setup, filed."""
    from mcgyvr.fleet import read as door_read

    return door_read.record(
        RIG,
        reader_text() if text is None else text,
        run_id=run_id,
        profile="live",
        probe=probe,
        measure=Harness() if harness is None else harness,
        load=load,
        fleet_name=fleet,
        setup=setup,
    )


def strong_harness() -> Harness:
    """The harness on the strong rung: its load peaks inside its room."""
    return Harness(
        warm=12.5, prefill=300.0, load_mib=(4500, 4700), container_id=STRONG_CONTAINER_ID
    )


def read_strong(setup: Path, run_id: str, *, load: str | None = LOAD) -> Any:
    """One door read of the strong fleet, its strong rung probed."""
    return read(
        setup,
        run_id,
        text=reader_text(card_mib=4600, strong_only=True),
        harness=strong_harness(),
        load=load,
        probe=(STRONG,),
        fleet=STRONG_FLEET,
    )


def edited(doc: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(doc)
