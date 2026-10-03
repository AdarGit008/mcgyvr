"""A host turns sharing on and off while connected, and the hub hears within a second.

Sharing is policy (``rider_slots`` in ``policy.yaml``), and the owner may
change it at any moment: turn a unit's sharing on, change how many slots it
lends, turn it off. The connected agent picks the edit up by itself, with no
reconnect and no command: it reads the setup again every
:data:`~mcgyvr.rig.hitchhike.POLL_S`, a cheap read of local files, and sends a
fresh ``unit_advert`` as soon as the shared set differs from what the hub was
told, still never two adverts within a second. The unit's server is read only
when something is to be sent.

For that, the hello always names ``hitchhike_units``, also for a rig that
lends no session and shares nothing yet: a rig whose setup starts sharing
mid-connection is heard at once, not at the next reconnect. A rig that lends
nothing offers no role, so the hub sends it no session.

The setup here is real files in a temporary folder, the agent's ticker and
clock are the real ones, and the unit's address answers nothing.
"""

from __future__ import annotations

import json
import socket
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes
from tests import rig_schema

#: The longest an edit may take to reach the hub.
WITHIN_S = 1.0


def _closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    (tmp_path / "fleet.yaml").write_text(
        "units:\n"
        "  coder:\n"
        f"    address: http://127.0.0.1:{_closed_port()}\n"
        "    model: qwen-coder-7b\n"
        "    width: 4\n"
        "    window: 8192\n",
        encoding="utf-8",
    )
    (tmp_path / "policy.yaml").write_text("ladder: [coder]\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def agent(folder: Path) -> Iterator[tuple[Any, fakes.Box]]:
    from mcgyvr.rig import hitchhike

    box = fakes.Box()
    units = hitchhike.Units(
        setup=lambda: hitchhike.load_setup(folder),
        send=box.put,
        say=lambda line: None,
    )
    units.online()
    units.run_ticker()
    yield units, box
    units.close()


def _adverts(box: fakes.Box) -> list[list[dict[str, Any]]]:
    return [frame["body"]["units"] for frame in box.of_type("unit_advert")]


def _heard(box: fakes.Box, wanted: Callable[[list[dict[str, Any]]], bool]) -> float:
    """How long until an advert ``wanted`` holds of goes; fails past twice the
    bound, so a slow edit is a number in the failure and not a hang."""
    started = time.monotonic()
    while time.monotonic() - started < 2 * WITHIN_S:
        adverts = _adverts(box)
        if adverts and wanted(adverts[-1]):
            return time.monotonic() - started
        time.sleep(0.01)
    raise AssertionError(f"no advert holding the edit; sent: {_adverts(box)}")


def _share(folder: Path, policy: str) -> None:
    staged = folder / ".policy.yaml.part"
    staged.write_text("ladder: [coder]\n" + policy, encoding="utf-8")
    staged.replace(folder / "policy.yaml")


def test_an_edit_to_the_share_reaches_the_hub_within_a_second(
    folder: Path, agent: tuple[Any, fakes.Box]
) -> None:
    _, box = agent
    time.sleep(0.5)
    assert _adverts(box) == []  # nothing is shared yet, so nothing is said

    _share(folder, "rider_slots: {coder: 1}\n")
    assert _heard(box, lambda units: [u["rider_cap"] for u in units] == [1]) <= (
        WITHIN_S
    )

    time.sleep(1.1)  # an advert goes at most once a second
    _share(folder, "rider_slots: {coder: 3}\n")
    assert _heard(box, lambda units: [u["rider_cap"] for u in units] == [3]) <= (
        WITHIN_S
    )

    time.sleep(1.1)
    _share(folder, "rider_slots: {coder: 0}\n")
    assert _heard(box, lambda units: units == []) <= WITHIN_S

    schema = rig_schema.load()
    for frame in box.of_type("unit_advert"):
        rig_schema.validate(frame, schema, "#/$defs/AgentMessage")
    (unit,) = _adverts(box)[0]
    assert unit["unit_id"] == "coder" and unit["free_slots"] == 0  # unread server


def test_an_unchanged_setup_is_read_again_and_nothing_is_sent(
    folder: Path, agent: tuple[Any, fakes.Box]
) -> None:
    _share(folder, "rider_slots: {coder: 1}\n")
    _heard(box := agent[1], lambda units: len(units) == 1)
    time.sleep(1.5)
    assert len(_adverts(box)) == 1


def test_the_hello_always_names_hitchhike_units_and_offers_a_role_only_when_lending(
    tmp_path: Path,
) -> None:
    from mcgyvr.rig import protocol, session

    held = fakes.inventory(tmp_path)
    idle = session.offer(
        fakes.sharing(tmp_path, enabled=False), held, (fakes.LAN_ADDRESS,), ("s1",)
    )
    assert idle == protocol.Offer(
        roles=(),
        runtime=None,
        endpoints=(),
        models=(),
        sessions=("s1",),
        features=(session.HITCHHIKE_FEATURE,),
    )
    hello = json.loads(
        protocol.hello(
            "h",
            machine_id="m",
            agent_version="1",
            ram_total_mb=1,
            ram_free_mb=None,
            cards=(),
            offer=idle,
        )
    )
    rig_schema.validate(hello, rig_schema.load(), "#/$defs/Hello")
    assert hello["body"]["capabilities"] == {
        "roles": [],
        "features": ["hitchhike_units"],
    }
