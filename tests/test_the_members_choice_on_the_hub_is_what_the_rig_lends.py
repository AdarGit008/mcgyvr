"""The member's choice on the hub is what the rig lends.

A member may set on the hub what a rig lends; the hub sends it in the hello's
ack (:data:`mcgyvr.hubwire.LENDING_FIELD`, :class:`mcgyvr.hubwire.Lending`).
The agent reads it whole and hands it on, or, when it is not the wire's shape
(a field left out: no ``cards`` is never "every card"), keeps its own settings
and says why; and the lending settings it runs under lend that: the member's
cards, memory and cores win over the lending file's while the hub asks them,
an ack that asks nothing gives the file's back, and the rest of the file (on or
off, roles, image) stays the owner's.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import hubwire
from tests import rig_pool_fakes as fakes
from tests.rigagents import Clock, Hub, Report, _agent, _frame

RAM_FLOOR = hubwire.LEND_FLOOR_MB[hubwire.RESOURCE_RAM]
CHOSEN = hubwire.Lending(cards=(1,), ram_mb=RAM_FLOOR, cpu_cores=4)


def _ack(lending: Any) -> Any:
    from mcgyvr.rig import protocol

    raw = _frame("ack", "h1", rig_id="r-1", **{hubwire.LENDING_FIELD: lending})
    return protocol.read_ack(protocol.decode(raw))


def test_the_ack_carries_the_members_lending_in_the_wires_shape() -> None:
    said = {"cards": [1], "ram_mb": RAM_FLOOR, "cpu_cores": 4}
    assert _ack(said).lending == CHOSEN
    every = _ack({"cards": None, "ram_mb": 0, "cpu_cores": 0})
    assert every.lending == hubwire.Lending(cards=None, ram_mb=0, cpu_cores=0)
    none = _ack({"cards": [], "ram_mb": 0, "cpu_cores": 0})
    assert none.lending == hubwire.Lending(cards=(), ram_mb=0, cpu_cores=0)
    assert none.lending_unread is None
    assert _ack(None).lending is None and _ack(None).lending_unread is None


@pytest.mark.parametrize(
    ("lending", "why"),
    [
        # A hub that left out a null field: no cards key is not "every card".
        ({"ram_mb": 0, "cpu_cores": 2}, "no cards"),
        ({"cards": [1], "ram_mb": RAM_FLOOR - 1, "cpu_cores": 4}, "ram_mb"),
        ({"cards": [1, 1], "ram_mb": 0, "cpu_cores": 0}, "cards"),
        ({"cards": "all", "ram_mb": 0, "cpu_cores": 0}, "cards"),
        ({"cards": [1], "ram_mb": 0}, "no cpu_cores"),
        ({"cards": [1], "ram_mb": "8G", "cpu_cores": 0}, "ram_mb"),
        (["not", "a", "lending"], "not an object"),
    ],
)
def test_a_lending_the_wire_refuses_is_not_taken_and_says_why(
    lending: Any, why: str
) -> None:
    ack = _ack(lending)
    assert ack.lending is None
    assert ack.lending_unread is not None and why in ack.lending_unread
    assert ack.lending_unread.startswith(hubwire.LENDING_FIELD)


def test_the_members_choice_wins_over_the_files_lend(tmp_path: Path) -> None:
    kept = fakes.sharing(tmp_path, cards=(0,), ram_mb=0, cpu_cores=0)
    chosen = kept.under(CHOSEN)
    assert (chosen.cards, chosen.ram_mb, chosen.cpu_cores) == (
        CHOSEN.cards,
        CHOSEN.ram_mb,
        CHOSEN.cpu_cores,
    )
    assert (chosen.enabled, chosen.roles, chosen.image) == (
        kept.enabled,
        kept.roles,
        kept.image,
    )
    assert chosen.lending == CHOSEN
    kinds = {r.kind: r for r in chosen.lent(fakes.report())}
    assert kinds[hubwire.RESOURCE_RAM].total_mb == RAM_FLOOR
    assert kinds[hubwire.RESOURCE_CPU].cores == 4
    assert [r.index for r in chosen.lent(fakes.report()) if r.kind == "gpu"] == [1]


def test_the_agent_hands_on_the_lending_each_hello_was_acked_with_or_none() -> None:
    class Choosing(Hub):
        def answer(self, message: dict[str, Any], channel: Any) -> list[Any]:
            out = super().answer(message, channel)
            if message["type"] != "hello":
                return out
            ack = json.loads(out[0])
            ack["body"][hubwire.LENDING_FIELD] = {
                "cards": [1],
                "ram_mb": RAM_FLOOR,
                "cpu_cores": 4,
            }
            return [json.dumps(ack), *out[1:]]

    handed: list[hubwire.Lending | None] = []
    agent, _ = _agent(
        [Choosing(interval=15, beats=1), Hub(interval=15, beats=1)],
        Clock(),
        report=Report(),
        on_lending=handed.append,
    )
    agent.run()
    # The second hub asks nothing: the member cleared the choice, so the rig
    # lends what its settings say again.
    assert handed == [CHOSEN, None]


def test_an_ack_with_a_lending_the_wire_refuses_keeps_the_rigs_own() -> None:
    class Malformed(Hub):
        def answer(self, message: dict[str, Any], channel: Any) -> list[Any]:
            out = super().answer(message, channel)
            if message["type"] != "hello":
                return out
            ack = json.loads(out[0])
            ack["body"][hubwire.LENDING_FIELD] = {"ram_mb": 0, "cpu_cores": 2}
            return [json.dumps(ack), *out[1:]]

    handed: list[hubwire.Lending | None] = []
    said: list[str] = []
    agent, channels = _agent(
        [Malformed(interval=15, beats=1)],
        Clock(),
        report=Report(),
        said=said,
        on_lending=handed.append,
    )
    agent.run()
    assert handed == [None]  # no choice taken: the settings' own lend
    assert any("lending choice is not taken" in line for line in said)
    assert [m["type"] for _, m in channels[0].sent] == ["hello", "heartbeat"]


def test_a_choice_cleared_on_the_hub_gives_the_files_lend_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import sharing

    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "home"))
    kept = fakes.sharing(tmp_path, cards=(0,), ram_mb=0, cpu_cores=0)
    sharing.save(kept)
    choice = sharing.HubChoice()
    assert choice.settings() == kept
    for said, lends in ((CHOSEN, CHOSEN), (None, kept.lending)):
        assert choice.take(said)
        assert choice.settings().lending == lends
        assert not choice.take(said)  # the same ack again changes nothing
    assert choice.settings() == kept
