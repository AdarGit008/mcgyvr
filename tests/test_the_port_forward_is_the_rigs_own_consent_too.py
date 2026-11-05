"""The port forward is the owner's to allow on the rig too, not on the hub's word.

A rig forwards its tunnel ports only when its own settings say so
(``port_forward``, off until the owner sets it): until then its hello names
no ``port_map`` feature, an ask from the hub is refused as ``failed``
``not_allowed`` with how to allow it, a check is refused, and a forward the
owner withdraws is given back. A lease is never permanent unless the owner
allowed that too (``port_forward_permanent``): a router that grants only
permanent leases is refused as ``failed`` ``permanent_only``. Each mapping is
recorded until it is given back, so an agent that starts after a crash gives
back what the one before left. The agent's first words say what this rig
allows, never what the hub agreed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.rig import portmap, sessionwire
from tests import rig_pool_fakes as fakes
from tests import rig_schema
from tests.test_a_rig_forwards_the_hubs_block_renews_it_and_gives_it_back import (
    LAN,
    FakeRouter,
    World,
    ask,
)

ALLOWED = portmap.Consent(forward=True)
PERMANENT = portmap.Consent(forward=True, permanent=True)


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("MCGYVR_HOME", str(home))
    monkeypatch.setenv("MCGYVR_DATA", str(tmp_path / "data"))
    return home


def check(mapper: portmap.Mapper) -> dict[str, Any]:
    frame = {
        "v": 1,
        "type": "port_check",
        "id": "c1",
        "body": {"check_id": "k1", "secret": "00" * 16, "port": 51820},
    }
    from mcgyvr.rig import protocol

    answer = mapper.check(protocol.decode(json.dumps(frame)))
    assert answer is not None
    found: dict[str, Any] = json.loads(answer)
    return found


def schema_reads(report: dict[str, Any]) -> None:
    """The report is a port_map_report the hub's published schema takes."""
    rig_schema.validate(
        {"v": 1, "type": "port_map_report", "id": "r1", "body": report},
        rig_schema.load(),
        "#/$defs/AgentMessage",
    )


# --- the policy -------------------------------------------------------------------


def test_a_mapper_allows_nothing_until_it_is_told_and_refuses_the_hubs_ask(
    capsys: pytest.CaptureFixture[str],
) -> None:
    upnp = FakeRouter()
    world = World([upnp])
    mapper = portmap.Mapper(  # no consent named: the default denies
        send=world.send,
        tunnel_ports=lambda: world.ports,
        hosts=lambda: world.hosts,
        routers=lambda: world.routers,
        clock=world.clock,
    )
    answer = ask(mapper, external_port=52000)
    assert answer is not None and json.loads(answer)["type"] == "ack"
    mapper.tick()
    assert upnp.adds == [] and upnp.held == {}
    [report] = world.reports()
    assert report["state"] == "failed" and report["error"] == portmap.NOT_ALLOWED
    assert portmap.ALLOW_FORWARD in report["message"]
    assert set(report) == {"state", "error", "message"}  # no rule to forward by hand
    schema_reads(report)
    said = capsys.readouterr().err
    assert "refused" in said and portmap.ALLOW_FORWARD in said
    refused = check(mapper)
    assert refused["type"] == "error" and refused["body"]["code"] == "not_capable"


def test_a_release_asked_while_not_allowed_is_said_as_ever() -> None:
    world = World([FakeRouter()], consent=portmap.Consent())
    mapper = world.mapper()
    ask(mapper)
    mapper.tick()
    assert world.reports() == [{"state": "released"}]


def test_a_forward_the_owner_withdraws_on_the_rig_is_given_back() -> None:
    upnp = FakeRouter()
    world = World([upnp])
    mapper = world.mapper()
    ask(mapper, external_port=52000)
    mapper.tick()
    assert len(upnp.held) == 4
    world.consent = portmap.Consent()
    assert mapper.tick() == portmap.IDLE_S
    assert upnp.held == {}
    assert world.reports()[-1]["error"] == portmap.NOT_ALLOWED
    mapper.tick()  # given back once, said once
    assert len(world.reports()) == 2


def test_a_permanent_lease_is_refused_unless_the_owner_allowed_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for router in (
        FakeRouter(lease=0),  # grants 0 when asked for a lease
        FakeRouter(refuse_at={52000: portmap.PERMANENT_ONLY}),  # UPnP 725
    ):
        world = World([router], consent=ALLOWED)
        mapper = world.mapper()
        ask(mapper, external_port=52000)
        mapper.tick()
        assert router.held == {}  # rolled back, never kept
        [report] = world.reports()
        assert report["state"] == "failed"
        assert report["error"] == portmap.PERMANENT_ONLY
        assert portmap.ALLOW_PERMANENT in report["message"]
        assert report["lan_host"] == LAN and report["external_port"] == 52000
        schema_reads(report)
    assert portmap.ALLOW_PERMANENT in capsys.readouterr().err


def test_a_block_that_turns_permanent_midway_is_held_permanent_whole() -> None:
    upnp = FakeRouter()

    def add(*, lan_host: str, internal: int, external: int, lease_s: int) -> int:
        # The third port takes only a permanent lease (UPnP 725).
        if lease_s and external == 52002:
            raise portmap.MapError(portmap.PERMANENT_ONLY, "only permanent")
        return FakeRouter.add(
            upnp,
            lan_host=lan_host,
            internal=internal,
            external=external,
            lease_s=lease_s,
        )

    upnp.add = add  # type: ignore[method-assign]
    world = World([upnp], consent=PERMANENT)
    mapper = world.mapper()
    ask(mapper, external_port=52000, lease_s=600)
    mapper.tick()
    # Every port permanent, so none is left on a lease that is never renewed.
    assert {port: lease for port, (_, _, lease) in upnp.held.items()} == {
        52000 + i: 0 for i in range(4)
    }
    assert world.reports()[0]["lease_s"] == 0
    world.clock.now += 100_000
    mapper.tick()
    assert len(upnp.adds) == 2 + 4  # two leased, then the whole block; no renewal


def test_a_permanent_lease_withdrawn_is_given_back_and_asked_with_a_lease() -> None:
    upnp = FakeRouter(lease=0)
    world = World([upnp], consent=PERMANENT)
    mapper = world.mapper()
    ask(mapper, external_port=52000)
    mapper.tick()
    assert world.reports()[0]["lease_s"] == 0
    world.consent = ALLOWED
    mapper.tick()
    assert upnp.held == {}
    assert world.reports()[-1]["error"] == portmap.PERMANENT_ONLY


# --- the record and the crash ------------------------------------------------------


def recording(world: World, record: Path, routers: dict[str, FakeRouter]) -> Any:
    return portmap.Mapper(
        send=world.send,
        tunnel_ports=lambda: world.ports,
        hosts=lambda: world.hosts,
        routers=lambda: world.routers,
        consent=lambda: world.consent,
        record=record,
        recall=lambda method, address: routers.get(address.get("name", "")),
        clock=world.clock,
    )


def test_every_mapping_is_recorded_and_a_crash_is_cleaned_at_the_next_start(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = tmp_path / "data" / portmap.RECORD_FILE
    upnp = FakeRouter()
    world = World([upnp])
    first = recording(world, record, {"upnp": upnp})
    ask(first, external_port=52000)
    first.tick()
    [kept] = portmap.read_record(record)
    assert (kept.method, kept.lan_host, kept.internal, kept.external, kept.ports) == (
        "upnp",
        LAN,
        51820,
        52000,
        4,
    )
    assert record.stat().st_mode & 0o077 == 0
    # The agent dies here: no close, the router still forwards the block.
    assert len(upnp.held) == 4
    second = recording(world, record, {"upnp": upnp})
    second.give_back_recorded()
    assert upnp.held == {}
    assert not record.exists()
    assert "gave back 1 of the 1" in capsys.readouterr().err
    assert world.reports()[-1]["state"] == "mapped"  # the restart says nothing


def test_a_normal_stop_gives_back_and_leaves_no_record(tmp_path: Path) -> None:
    record = tmp_path / "data" / portmap.RECORD_FILE
    upnp = FakeRouter()
    world = World([upnp])
    mapper = recording(world, record, {"upnp": upnp})
    ask(mapper, external_port=52000)
    mapper.tick()
    assert record.exists()
    mapper.close()
    assert upnp.held == {} and not record.exists()


def test_a_permanent_mapping_whose_router_is_away_stays_on_record(
    tmp_path: Path,
) -> None:
    record = tmp_path / "data" / portmap.RECORD_FILE
    upnp = FakeRouter(lease=0)
    world = World([upnp], consent=PERMANENT)
    first = recording(world, record, {"upnp": upnp})
    ask(first, external_port=52000)
    first.tick()

    def away(**_: Any) -> None:
        raise portmap.MapError("timeout", "away")

    upnp.remove = away  # type: ignore[method-assign]
    first.close()  # the router does not answer: the permanent lease stays
    assert len(portmap.read_record(record)) == 1
    recording(world, record, {"upnp": upnp}).give_back_recorded()
    assert len(portmap.read_record(record)) == 1  # still away: kept for next time
    del upnp.remove
    recording(world, record, {"upnp": upnp}).give_back_recorded()
    assert upnp.held == {} and not record.exists()


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        json.dumps({"mappings": [{"method": "upnp"}]}),
        json.dumps({"mappings": "no"}),
        json.dumps(
            {
                "mappings": [
                    {
                        "method": "upnp",
                        "address": {},
                        "lan_host": "8.8.8.8",
                        "internal": 1,
                        "external": 1,
                        "ports": 1,
                        "lease_s": 0,
                    }
                ]
            }
        ),
    ],
)
def test_a_record_of_another_shape_names_nothing(tmp_path: Path, text: str) -> None:
    record = tmp_path / portmap.RECORD_FILE
    record.write_text(text)
    assert portmap.read_record(record) == []


def test_a_recorded_router_is_recalled_only_on_a_private_address() -> None:
    wan = portmap.WAN_SERVICES[0]
    assert isinstance(
        portmap.recall("natpmp", {"gateway": "192.168.1.1"}), portmap.NatPmp
    )
    assert portmap.recall("natpmp", {"gateway": "8.8.8.8"}) is None
    upnp = portmap.recall(
        "upnp", {"service": wan, "control": "http://192.168.1.1:5000/c"}
    )
    assert isinstance(upnp, portmap.Upnp)
    assert upnp.address() == {"service": wan, "control": "http://192.168.1.1:5000/c"}
    for control in ("https://192.168.1.1/c", "http://1.2.3.4/c", "http://h:x/c"):
        assert portmap.recall("upnp", {"service": wan, "control": control}) is None
    assert (
        portmap.recall("upnp", {"service": "other", "control": "http://10.0.0.1/"})
        is None
    )
    assert portmap.recall("pcp", {}) is None


# --- the settings, the hello and the words -----------------------------------------


def test_the_settings_allow_nothing_by_default_and_keep_what_the_owner_says() -> None:
    from mcgyvr.rig import sharing

    kept = sharing.load()
    assert not kept.port_forward and not kept.port_forward_permanent
    assert "port_forward" not in sharing.as_data(kept)  # older agents read it still
    allowed = sharing.read({"port_forward": True, "port_forward_permanent": True})
    assert allowed.port_forward and allowed.port_forward_permanent
    assert sharing.as_data(allowed)["port_forward"] is True
    for name in ("port_forward", "port_forward_permanent"):
        with pytest.raises(sharing.SharingError, match=name):
            sharing.read({name: "yes"})


def test_the_hello_names_port_map_only_when_the_rig_allows_it(tmp_path: Path) -> None:
    from mcgyvr.rig import session

    held = fakes.inventory(tmp_path)

    def features(**changes: Any) -> tuple[str, ...]:
        share = fakes.sharing(tmp_path, **changes)
        return session.offer(
            share, held, (fakes.LAN_ADDRESS,), (), fakes.report()
        ).features

    assert session.PORT_MAP_FEATURE not in features()
    assert session.PORT_MAP_FEATURE in features(port_forward=True)
    assert set(features(port_forward=True)) - set(features()) == {
        session.PORT_MAP_FEATURE
    }


def test_the_agent_says_what_this_rig_allows_never_what_the_hub_agreed() -> None:
    from mcgyvr.rig import sharing, verbs

    denied = verbs.port_forward_line(sharing.Sharing())
    assert "not allowed on this rig" in denied and portmap.ALLOW_FORWARD in denied
    allowed = verbs.port_forward_line(sharing.Sharing(port_forward=True))
    assert "allowed on this rig" in allowed and "51820-51823" in allowed
    assert portmap.ALLOW_PERMANENT in allowed  # no permanent lease unless allowed
    permanent = verbs.port_forward_line(
        sharing.Sharing(port_forward=True, port_forward_permanent=True)
    )
    assert "a permanent lease where the router grants no other" in permanent
    for line in (denied, allowed, permanent):
        assert "as agreed on the hub" not in line
    consent = verbs.forward_consent(sharing.Sharing(port_forward=True))
    assert consent == portmap.Consent(forward=True, permanent=False)


def test_share_allows_and_withdraws_the_forward_and_says_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr import cli
    from mcgyvr.rig import sharing

    assert cli.main(["rig", "share", "--port-forward"]) == 0
    assert sharing.load().port_forward and not sharing.load().port_forward_permanent
    assert "forward: allowed" in capsys.readouterr().out
    assert cli.main(["rig", "share", "--permanent-forward"]) == 0
    assert sharing.load().port_forward_permanent
    assert cli.main(["rig", "share", "--no-port-forward"]) == 0
    assert not sharing.load().port_forward
    assert "forward: not allowed" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("flag", "allowed"), [("--port-forward", True), ("--no-port-forward", False)]
)
def test_join_keeps_the_owners_word_on_the_forward(
    monkeypatch: pytest.MonkeyPatch, flag: str, allowed: bool
) -> None:
    from mcgyvr import cli
    from mcgyvr.rig import sharing, verbs

    seen: list[bool] = []

    def run(kept: Any, config: Any = None) -> int:
        seen.append(sharing.load().port_forward)
        return 0

    monkeypatch.setattr(verbs, "run_agent", run)
    token = "mhr_0123456789abcdef_" + "s" * 43
    assert (
        cli.main(["rig", "join", "https://hub.example.com", "--token", token, flag])
        == 0
    )
    assert seen == [allowed]


def test_join_without_a_word_leaves_the_forward_as_it_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr import cli
    from mcgyvr.rig import sharing, verbs

    monkeypatch.setattr(verbs, "run_agent", lambda kept, config=None: 0)
    token = "mhr_0123456789abcdef_" + "s" * 43
    assert cli.main(["rig", "join", "https://hub.example.com", "--token", token]) == 0
    assert not sharing.path().exists() and not sharing.load().port_forward


def test_the_report_tags_are_tags_the_wire_takes() -> None:
    for tag in (portmap.NOT_ALLOWED, portmap.PERMANENT_ONLY):
        frame = sessionwire.port_map_report(
            sessionwire.PortMapped(state="failed", error=tag, message="m")
        )
        schema_reads(json.loads(frame)["body"])


def test_the_setup_document_names_the_rigs_own_switches_and_tags() -> None:
    import argparse

    from mcgyvr import docgen
    from mcgyvr.rig import sharing, verbs

    assert docgen.SHARING_FILE == sharing.SHARING_FILE
    assert docgen.FORWARD_NOT_ALLOWED == portmap.NOT_ALLOWED
    assert docgen.FORWARD_PERMANENT_ONLY == portmap.PERMANENT_ONLY
    assert portmap.ALLOW_FORWARD.endswith(docgen.PORT_FORWARD_SWITCH)
    assert portmap.ALLOW_PERMANENT.endswith(docgen.PERMANENT_FORWARD_SWITCH)
    parser = argparse.ArgumentParser()
    verbs.add_parser(parser.add_subparsers(), add_config=lambda *a, **k: None)
    share = parser.parse_args(
        ["rig", "share", docgen.PORT_FORWARD_SWITCH, docgen.PERMANENT_FORWARD_SWITCH]
    )
    assert (share.port_forward, share.permanent_forward) == (True, True)
    join = parser.parse_args(
        [
            "rig",
            "join",
            "https://hub.example.com",
            "--token",
            "t",
            docgen.PORT_FORWARD_SWITCH,
        ]
    )
    assert join.port_forward is True
    section = "\n".join(docgen._port_forward_section())
    assert "on the hub's My rigs page, and on the rig itself" in section


def test_a_release_the_hub_asks_as_the_owner_withdraws_is_said_released() -> None:
    upnp = FakeRouter()
    world = World([upnp])
    mapper = world.mapper()
    ask(mapper, external_port=52000)
    mapper.tick()
    world.consent = portmap.Consent()
    ask(mapper)  # the hub asks it back in the same pass
    mapper.tick()
    assert upnp.held == {}
    assert world.reports()[-1] == {"state": "released"}


def test_a_mapping_is_on_record_before_the_router_is_asked(tmp_path: Path) -> None:
    record = tmp_path / "data" / portmap.RECORD_FILE
    upnp = FakeRouter()
    seen: list[list[portmap.Recorded]] = []

    def add(*, lan_host: str, internal: int, external: int, lease_s: int) -> int:
        seen.append(portmap.read_record(record))  # as a crash right now would leave it
        return FakeRouter.add(
            upnp,
            lan_host=lan_host,
            internal=internal,
            external=external,
            lease_s=lease_s,
        )

    upnp.add = add  # type: ignore[method-assign]
    world = World([upnp])
    mapper = recording(world, record, {"upnp": upnp})
    ask(mapper, external_port=52000)
    mapper.tick()
    assert all(
        [(r.external, r.ports, r.lease_s) for r in found] == [(52000, 4, 3600)]
        for found in seen
    )
    assert len(seen) == 4


def test_a_mapping_no_router_took_leaves_no_record(tmp_path: Path) -> None:
    record = tmp_path / "data" / portmap.RECORD_FILE
    upnp = FakeRouter(refuse_at={52001: "refused"})
    world = World([upnp])
    mapper = recording(world, record, {"upnp": upnp})
    ask(mapper, external_port=52000)
    mapper.tick()
    assert upnp.held == {} and not record.exists()


@pytest.mark.parametrize("host", ["127.0.0.1", "169.254.1.1"])
def test_a_record_never_aims_a_router_at_this_host_or_a_link_local_one(
    host: str,
) -> None:
    wan = portmap.WAN_SERVICES[0]
    assert portmap.recall("natpmp", {"gateway": host}) is None
    assert (
        portmap.recall("upnp", {"service": wan, "control": f"http://{host}/c"}) is None
    )
