"""The owner decides whether this rig lends, and what: roles, cards, memory, models.

Lending is off until the owner turns it on, and a file that does not read
turns nothing on: it is refused by the field it gets wrong. On, a rig offers
only the roles its owner allows — the head only with a models folder — in
the engine image the owner names; it lends only the cards the owner lists,
and never a card of a vendor the engine is not started on; the hub is told
of a lent card's free memory at most the owner's cap and of a card not lent
none, so it plans within them; and a hello carries the offer only while the
rig lends. ``mcgyvr rig share`` keeps the settings and says them back.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("MCGYVR_HOME", str(home))
    return home


def test_nothing_is_lent_until_the_owner_turns_it_on() -> None:
    from mcgyvr.rig import sharing

    kept = sharing.load()
    assert kept == sharing.Sharing() and not kept.enabled
    assert kept.offered_roles() == ()
    assert kept.lends(0, fakes.report()) is None
    assert kept.lendable(fakes.report()) == fakes.report()


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ([], "the file"),
        ({"enabled": "yes"}, "enabled"),
        ({"roles": ["boss"]}, "roles"),
        ({"cards": [-1]}, "cards"),
        ({"max_vram_mb": 0}, "max_vram_mb"),
        ({"models_dir": "relative/models"}, "models_dir"),
        ({"endpoints": ["not-an-address"]}, "endpoints"),
        ({"listen_port": 80}, "listen_port"),
        ({"image": "bad image; rm"}, "image"),
        ({"surprise": True}, "surprise"),
    ],
)
def test_a_file_that_does_not_read_is_refused_by_its_field(
    _home: Path, data: Any, field: str
) -> None:
    from mcgyvr.rig import sharing

    _home.mkdir(parents=True)
    (_home / sharing.SHARING_FILE).write_text(json.dumps(data))
    with pytest.raises(sharing.SharingError) as refused:
        sharing.load()
    assert f": {field}:" in str(refused.value)


def test_the_roles_offered_are_the_owners_and_the_head_needs_a_models_folder(
    tmp_path: Path,
) -> None:
    both = fakes.sharing(tmp_path)
    assert both.offered_roles() == ("head", "worker")
    assert fakes.sharing(None).offered_roles() == ("worker",)
    assert fakes.sharing(tmp_path, roles=("worker",)).offered_roles() == ("worker",)
    assert fakes.sharing(tmp_path, image=None).offered_roles() == ()
    assert fakes.sharing(tmp_path, enabled=False).offered_roles() == ()


def test_only_the_cards_the_owner_lists_of_the_engines_vendor_are_lent() -> None:
    report = fakes.report()
    every = fakes.sharing(None)
    assert [every.lends(i, report) for i in (0, 1, 2, 3)] == [0, 1, None, None]
    listed = fakes.sharing(None, cards=(1, 2))
    assert [listed.lends(i, report) for i in (0, 1, 2)] == [None, 1, None]


def test_the_hub_is_told_of_no_more_than_the_owner_lends() -> None:
    report = fakes.report()
    told = fakes.sharing(None, cards=(1,), max_vram_mb=3000, max_ram_mb=4096).lendable(
        report
    )
    assert [c.vram_free_mb for c in told.cards] == [0, 3000, 0]
    assert [c.vram_total_mb for c in told.cards] == [
        c.vram_total_mb for c in report.cards
    ]
    assert told.ram_free_mb == 4096 and told.ram_total_mb == report.ram_total_mb
    assert told.machine_id == report.machine_id


def test_a_hello_offers_only_while_the_rig_lends(tmp_path: Path) -> None:
    from mcgyvr.rig import inventory, protocol, session

    held = fakes.inventory(tmp_path)
    off = session.offer(
        fakes.sharing(tmp_path, enabled=False), held, (fakes.LAN_ADDRESS,), ()
    )
    assert off is None
    on = session.offer(fakes.sharing(tmp_path), held, (fakes.LAN_ADDRESS,), ("s1",))
    assert on == protocol.Offer(
        roles=("head", "worker"),
        runtime="engine:rpc",
        endpoints=((fakes.LAN_ADDRESS, 51820, "lan"),),
        models=held.models,
        sessions=("s1",),
    )
    worker_only = session.offer(
        fakes.sharing(tmp_path, roles=("worker",)), held, (fakes.LAN_ADDRESS,), ()
    )
    assert worker_only is not None and worker_only.models == ()
    frame = json.loads(
        protocol.hello(
            "h",
            machine_id="m",
            agent_version="1",
            ram_total_mb=1,
            ram_free_mb=None,
            cards=(),
            offer=on,
        )
    )
    assert frame["body"]["capabilities"] == {
        "roles": ["head", "worker"],
        "runtime": "engine:rpc",
    }
    assert frame["body"]["models"] == [{"name": fakes.MODEL, "size_bytes": 1024}]
    assert inventory.resolve(held, fakes.MODEL) == f"dense/{fakes.MODEL}"
    assert "dense" not in json.dumps(frame)


def test_share_keeps_the_settings_and_says_them_back(
    _home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr import cli
    from mcgyvr.rig import sharing

    models = tmp_path / "models"
    models.mkdir()
    code = cli.main(
        [
            "rig",
            "share",
            "--on",
            "--image",
            "engine:rpc",
            "--roles",
            "worker,head",
            "--cards",
            "0,1",
            "--max-vram-mb",
            "4000",
            "--max-ram-mb",
            "2048",
            "--models",
            str(models),
            "--endpoints",
            fakes.LAN_ADDRESS,
            "--no-cache",
        ]
    )
    assert code == 0
    kept = sharing.load()
    assert kept.enabled and kept.image == "engine:rpc" and kept.cards == (0, 1)
    assert (kept.max_vram_mb, kept.max_ram_mb, kept.cache) == (4000, 2048, False)
    assert kept.models_dir == str(models) and kept.endpoints == (fakes.LAN_ADDRESS,)
    said = capsys.readouterr().out
    assert "lending: on" in said and "roles:   head, worker" in said
    assert cli.main(["rig", "share", "--off"]) == 0
    assert not sharing.load().enabled


def test_share_will_not_turn_on_without_an_engine_image(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr import cli
    from mcgyvr.rig import sharing

    assert cli.main(["rig", "share", "--on"]) != 0
    assert "--image" in capsys.readouterr().err
    assert not sharing.load().enabled
