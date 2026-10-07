"""The Jev unit is opt-in, resident, sized first, at 4k per slot.

Owner, Round 3 (OQ5): "Jev: ALWAYS opt-in (never on by default). When opted
in, the default model is Qwen3.5-4B." Round 4: "Jev 4k." Plan section 6.1:
the Jev unit is placed first, resident, on the card with the most room, and
every other unit is sized against what is left.

Promises, over invented machines and the shipped knowledge:

* Without ``--jev`` no Jev unit is planned.
* ``--jev`` plans one, marked ``jev`` (its role ``always-on``: it is
  resident), Qwen3.5-4B, 4096 tokens per slot, one slot per user, on the card
  with the most room, for every use case planned.
* ``--jev MODEL`` plans that model instead; a model the knowledge does not
  hold is refused, by name.
* The other units are sized around it: on its card, the card figures of
  everything awake there sum to no more than what was free (a unit that
  sleeps until needed fits beside the Jev unit alone, since the rungs it
  swaps with sleep while it is awake), and a unit split across cards does
  not take the Jev unit's card.
* The Jev unit is not a rung: it is not on the ladder.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli, planner, recommend
from mcgyvr.scan import Disk, Gpu, Machine, Memory, Scan, Vram

RIG = "rig-f.invalid"


def _scan(free_mib: tuple[int, ...]) -> Scan:
    return Scan(
        machine=Machine(id="machine-f", host=RIG, kernel="0.0.0-example"),
        gpus=tuple(
            Gpu(
                index=index,
                name="Example Card X",
                vram=Vram(
                    total_mib=free + 512, used_mib=512, free_mib=free, reserved_mib=0
                ),
            )
            for index, free in enumerate(free_mib)
        ),
        memory=Memory(total_gb=36.0, available_gb=32.0),
        disk=Disk(path=Path("/weights"), free_gb=500.0),
    )


def _run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    scan: Scan,
    *extra: str,
    use_case: str = "coding",
    users: int = 2,
) -> tuple[int, str, str]:
    monkeypatch.setattr(recommend, "_scan_host", lambda host: scan)
    code = cli.main(
        [
            "recommend",
            "--use-case",
            use_case,
            "--users",
            str(users),
            "--host",
            RIG,
            "--offline",
            *extra,
        ]
    )
    out = capsys.readouterr()
    return code, out.out, out.err


def _jev(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [u for laid in plan["rigs"].values() for u in laid["units"] if u["jev"]]


@pytest.mark.parametrize("use_case", ["chat", "agent", "coding"])
def test_without_jev_no_jev_unit_is_planned(
    use_case: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(monkeypatch, capsys, _scan((11800,)), use_case=use_case)
    assert code == 0, err
    assert _jev(json.loads(out)) == []


@pytest.mark.parametrize("use_case", ["chat", "agent", "coding"])
def test_jev_plans_the_default_resident_at_4k_on_the_roomiest_card(
    use_case: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(
        monkeypatch, capsys, _scan((6000, 11800)), "--jev", use_case=use_case
    )
    assert code == 0, err
    plan = json.loads(out)
    (jev,) = _jev(plan)
    assert jev["model"]["id"] == planner.JEV_DEFAULT
    assert jev["ctx_per_slot"] == planner.JEV_CTX == 4096
    assert jev["slots"] == 2
    assert jev["cards"] == [1]
    assert jev["name"] not in plan["ladder"]
    for laid in plan["rigs"].values():
        for unit in laid["units"]:
            if unit is not jev and len(unit["cards"]) > 1:
                assert 1 not in unit["cards"]


def test_jev_with_a_model_plans_that_model(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(
        monkeypatch, capsys, _scan((24000,)), "--jev", "Qwen/Qwen3-8B"
    )
    assert code == 0, err
    (jev,) = _jev(json.loads(out))
    assert jev["model"]["id"] == "Qwen/Qwen3-8B"


def test_jev_with_a_model_the_knowledge_does_not_hold_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _out, err = _run(
        monkeypatch, capsys, _scan((11800,)), "--jev", "example-org/Not-Known"
    )
    assert code == 1
    assert "example-org/Not-Known" in err


def jev_gib(plan: dict[str, Any]) -> float:
    (jev,) = _jev(plan)
    gib: float = jev["fit"]["vram_gib"]
    return gib


@pytest.mark.parametrize("use_case", ["chat", "coding"])
def test_everything_on_the_jev_card_sums_to_what_was_free(
    use_case: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scan = _scan((11800,))
    code, out, err = _run(monkeypatch, capsys, scan, "--jev", use_case=use_case)
    assert code == 0, err
    plan = json.loads(out)
    assert len([u for laid in plan["rigs"].values() for u in laid["units"]]) >= 2
    on_card: dict[int, float] = defaultdict(float)
    for laid in plan["rigs"].values():
        for unit in laid["units"]:
            if unit["role"] == "sleeps-until-needed":
                # It wakes only when the rungs it swaps with sleep.
                assert unit["fit"]["vram_gib"] + jev_gib(plan) <= 11800 / 1024
                continue
            for card in unit["cards"]:
                on_card[card] += unit["fit"]["vram_gib"]
    assert on_card[0] * 1024 <= 11800
