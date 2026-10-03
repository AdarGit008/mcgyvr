"""An invented fleet of two rigs and a unit that spans both, for the span tests.

Every machine here is invented: two rigs, ``box-a.example`` and
``box-b.example``, ids that are not any rig's, addresses in the documentation
range, and rooms that are round numbers chosen so a boundary is easy to read.
Nothing here is a reading of a machine, and no number is a rule: the tests that
use it pin the arithmetic (a room is a sum, a card must fit its figure), not the
values.

The fleet has three units:

* ``big_model`` has its head on A and spans A's cards 0 and 1 and B's card 0;
* ``remote_head`` has its head on B and spans B's card 0 and A's card 1, so a
  head that sorts after its worker is covered too;
* ``small`` is a plain unit on A that spans nothing.
"""

from __future__ import annotations

import copy
from typing import Any

A = "box-a.example"
B = "box-b.example"
RIG_A = "rig-" + "a" * 64
RIG_B = "rig-" + "b" * 64
BIG_ID = "unt-" + "1" * 64
REMOTE_ID = "unt-" + "2" * 64
SMALL_ID = "unt-" + "3" * 64

BIG = "big_model"
REMOTE = "remote_head"
SMALL = "small"

#: The room each shard of ``big_model`` needs: 3000 + 2500 on A, 2000 on B.
BIG_ROOM_A = 5500
BIG_ROOM_B = 2000
SMALL_ROOM = 1500
OVERHEAD = 600

TOLERANCES: dict[str, Any] = {
    "warm_decode_class_pct": {
        "vllm": 3.0,
        "llamacpp": 5.0,
        "cpu_experts": 5.0,
        "mtp": 5.0,
    }
}


def _unit(rig: str, unit_id: str, port: int, **more: Any) -> dict[str, Any]:
    return {
        "rig": rig,
        "unit_id": unit_id,
        "engine": "llama.cpp",
        "address": f"http://{rig}:{port}",
        "model": "example-model",
        "width": 2,
        "window": 4096,
        "output_tokens": 512,
        "request_timeout_s": 180,
        **more,
    }


def fleet() -> dict[str, Any]:
    """A fresh copy of the fleet: two layouts, ``whole`` and ``resting``."""
    return {
        "profile": "dev",
        "rigs": {A: {"rig_id": RIG_A}, B: {"rig_id": RIG_B}},
        "units": {
            BIG: _unit(
                A,
                BIG_ID,
                8080,
                launch={
                    "shards": [
                        {"rig": A, "gpu": 0, "room_mib": 3000},
                        {"rig": A, "gpu": 1, "room_mib": 2500},
                        {
                            "rig": B,
                            "gpu": 0,
                            "room_mib": BIG_ROOM_B,
                            "bind": "192.0.2.20",
                        },
                    ]
                },
            ),
            REMOTE: _unit(
                B,
                REMOTE_ID,
                8081,
                launch={
                    "shards": [
                        {"rig": B, "gpu": 0, "room_mib": 1000},
                        {"rig": A, "gpu": 1, "room_mib": 1000, "bind": "192.0.2.10"},
                    ]
                },
            ),
            SMALL: _unit(A, SMALL_ID, 8082, room_mib=SMALL_ROOM),
        },
        "fleets": {
            "whole": {
                "layout": {
                    A: [[BIG, "awake"], [SMALL, "awake"]],
                    B: [[BIG, "awake"]],
                },
                "next": [],
            },
            "resting": {
                "layout": {
                    A: [[BIG, "asleep"], [SMALL, "awake"]],
                    B: [[BIG, "asleep"]],
                },
                "next": [],
            },
        },
    }


def with_small_on_a_card(fleet_: dict[str, Any], gpu: int = 1) -> dict[str, Any]:
    """``small`` pinned to one card of A, as a rig with per-card figures needs."""
    out = copy.deepcopy(fleet_)
    out["units"][SMALL]["launch"] = {
        "shards": [{"rig": A, "gpu": gpu, "room_mib": SMALL_ROOM}]
    }
    return out


def combination(rig: str, slots: list[Any], overhead: int = OVERHEAD) -> dict[str, Any]:
    """One passing dev run of ``slots`` on ``rig``.

    ``big_model`` is measured where it is the head and only there: its worker
    slot on B carries a card peak and no decode or prefill figure.
    """
    peak = {(A, BIG): 5400, (B, BIG): 1900, (A, SMALL): 1400}
    row: dict[str, Any] = {
        "rig": rig,
        "slots": slots,
        "passed": True,
        "overhead_mib": overhead,
        "restarts": {},
        "card_peak_mib": {},
        "warm_decode_tok_s": {},
        "prefill_tok_s": {},
        "validated_at": "2026-09-20T10:00:00Z",
        "envelope": "evidence/span-fleet",
    }
    for unit, state in slots:
        row["restarts"][unit] = 0
        row["card_peak_mib"][unit] = peak[(rig, unit)]
        if state == "awake" and not (unit == BIG and rig == B):
            row["warm_decode_tok_s"][unit] = 30.0 if unit == BIG else 60.0
            row["prefill_tok_s"][unit] = 400.0 if unit == BIG else 800.0
    return row


def evidence(fleet_: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dev evidence for every combination ``fleet_``'s fleets list, each rig on
    one figure of 20000 MiB (A) or 9000 MiB (B)."""
    source = fleet() if fleet_ is None else fleet_
    seen: list[tuple[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for block in source["fleets"].values():
        for rig, slots in block["layout"].items():
            if (rig, slots) not in seen:
                seen.append((rig, slots))
                rows.append(combination(rig, slots))
    return {
        "rigs": {A: {"card_mib": 20000}, B: {"card_mib": 9000}},
        "combinations": rows,
        "moves": [],
    }
