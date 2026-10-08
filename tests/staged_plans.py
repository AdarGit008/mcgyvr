"""Invented plans (version 2) for the staged-setup and sample-run tests.

Each plan is what ``mcgyvr recommend`` prints for an invented rig and invented
dense models, read back as JSON, with the scans it was planned from: the
planner itself makes it, so a test of what is staged from a plan is a test of
what a real plan stages. Nothing here reaches a machine.

* :func:`coding_plan` is a ladder whose top rung does not fit awake beside
  the others and fits alone: it sleeps until needed and swaps with them.
* :func:`chat_plan` is one strong unit, with no sleeper.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli, planner, recommend
from mcgyvr.scan import Disk, Gpu, Machine, Memory, Scan, Vram
from tests.test_recommend import dense_header, invented_model

RIG = "rig-s.invalid"
GB = 1_000_000_000
#: Invented dense models: doublings, each a clear step over the one below.
SIZES = {"tiny": 2 * GB, "small": 4 * GB, "mid": 8 * GB, "big": 16 * GB}
#: What the invented card has free: the top rung fits alone, not beside the rest.
SWAP_FREE_MIB = 19000
#: A card roomy enough for the chat plan's one unit.
CHAT_FREE_MIB = 12000
#: The card's total, as the rig file records it.
CARD_TOTAL_MIB = SWAP_FREE_MIB + 512


def library() -> planner.Library:
    return planner.Library(
        models=tuple(
            invented_model(
                f"invented-org/coder-{name}",
                dense_header(f"coder-{name}-Q4_K_M.gguf", int(size), context=32768),
            )
            for name, size in SIZES.items()
        )
    )


def scan(free_mib: int = SWAP_FREE_MIB) -> Scan:
    return Scan(
        machine=Machine(id="machine-s", host=RIG, kernel="0.0.0-example"),
        gpus=(
            Gpu(
                index=0,
                name="Example Card S",
                vram=Vram(
                    total_mib=free_mib + 512,
                    used_mib=512,
                    free_mib=free_mib,
                    reserved_mib=0,
                ),
            ),
        ),
        memory=Memory(total_gb=68.0, available_gb=64.0),
        disk=Disk(path=Path("/weights"), free_gb=500.0),
    )


def _plan(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    use_case: str,
    free_mib: int,
) -> tuple[dict[str, Any], dict[str, Scan]]:
    measured = scan(free_mib)
    monkeypatch.setattr(recommend, "_scan_host", lambda host: measured)
    monkeypatch.setattr(recommend, "load_models", library)
    code = cli.main(
        ["recommend", "--use-case", use_case, "--users", "1", "--host", RIG]
    )
    out = capsys.readouterr()
    assert code == 0, out.err
    plan: dict[str, Any] = json.loads(out.out)
    return plan, {RIG: measured}


def coding_plan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[dict[str, Any], dict[str, Scan]]:
    """A coding ladder with a sleeper, and the scans it was planned from."""
    plan, scans = _plan(monkeypatch, capsys, "coding", SWAP_FREE_MIB)
    roles = [unit["role"] for unit in plan["rigs"][RIG]["units"]]
    assert "sleeps-until-needed" in roles, roles
    return plan, scans


def chat_plan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[dict[str, Any], dict[str, Scan]]:
    """One strong chat unit, and the scans it was planned from."""
    return _plan(monkeypatch, capsys, "chat", CHAT_FREE_MIB)


def units(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The plan's units by name."""
    return {
        unit["name"]: unit
        for laid in plan["rigs"].values()
        for unit in laid["units"]
    }
