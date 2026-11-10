"""A docker unit listens on the loopback unless it is exposed, and then only with a key.

Promise: a llama.cpp or vLLM server mcgyvr renders into a container listens on
127.0.0.1 when its unit is ``expose: local``, and on every interface when it is
``expose: lan``; a unit that states neither is ``local`` when its address names
this machine and ``lan`` when it names another host. Only this machine's exact
names (``gatelib.LOCAL_RIGS``) are this machine here, in two cases. A launch
that states where it listens is held to them as written: 127.0.0.2,
``LOCALHOST``, 0.0.0.0 and ``::``, which the looser match that finds a rig file
takes for this machine, listen beyond it. A unit's address is held to them by
its URL host, which a URL lower-cases (RFC 3986: a host is case-insensitive):
``http://LOCALHOST`` is ``http://localhost``, so it is ``local`` and listens on
127.0.0.1, while 127.0.0.2, 0.0.0.0 and ``[::]`` come out ``lan`` and keyed.
A ``lan`` unit asks every request for a key mcgyvr makes the first time
``mcgyvr emit`` writes it: kept at mode 0600 in the data folder, named in the
compose service's ``env_file`` and never written into the compose file, and
sent by mcgyvr's own requests to the unit (a dispatch, a status poll, the
availability probe, setup's discovery, the sampler's read, the door's probes
and the rig agent's relay) as a bearer token, to the unit's own address alone.
A unit that states its own ``--host`` or ``LLAMA_ARG_HOST`` renders byte for
byte as it did before units listened on the loopback by default. ``mcgyvr
emit`` says where each keyed unit listens, and warns where a unit's own address
cannot reach it. ``mcgyvr fleet key`` prints the key, for a client of the owner's
own.

The machines are invented, and so are their addresses.
"""

from __future__ import annotations

import base64
import json
import os
import stat
import subprocess
import sys
import threading
import types
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml

import mcgyvr.runner as runner
from mcgyvr import detect, unitkey
from mcgyvr.availability import probe_endpoint
from mcgyvr.cli import main
from mcgyvr.cli.commands.ladder import _exposure
from mcgyvr.config import CONFIG_PATH_ENV, ConfigSchemaError, parse
from mcgyvr.emit import (
    EmitError,
    _healthcheck,
    emit_locked,
    listens_beyond_loopback,
    locked_keyed,
    locked_open,
)
from mcgyvr.exits import Exit
from mcgyvr.fleet import harness, read, sampler
from mcgyvr.ladder_map import UnitUnavailableError, unit_map
from mcgyvr.rig import hitchhike
from mcgyvr.rig.relay import Target
from mcgyvr.rig.relay import _page as relay_page
from mcgyvr.scan import Scan
from mcgyvr.serving import (
    ROLE_RPC,
    Unit,
    exposure,
    host_of,
    rigfile,
    servelib,
    unit_for,
    units_for,
)
from mcgyvr.serving.gatelib import LOCAL_RIGS
from mcgyvr.serving.run import GATE_SCRIPTS
from tests import onedoor, reads, records
from tests.doors import DENSE, SEVEN_B_SPEC, rig, service_of
from tests.emitted import compose_of
from tests.relays import Host, _host, _ride_body
from tests.sizings import WINDOW
from tests.test_a_locked_unit_split_across_rigs_is_emitted_as_its_head_and_rpc_workers import (  # noqa: E501
    A as LOCKED_RIG,
)
from tests.test_a_locked_unit_split_across_rigs_is_emitted_as_its_head_and_rpc_workers import (  # noqa: E501
    plain,
)
from tests.test_serving_gatelib import clean_env, fake_door, ssh_stub, under

HOST = "gpu-box.example"
#: A key of the shape `unitkey` makes, for files a test writes itself.
A_KEY = "k" * 43
#: An invented HOME, for renders that name the weights under it.
SOMEONE = "/home/someone"


def llama(expose: str = "local") -> Unit:
    made = unit_for(
        rig(HOST, vram_mib=6144, free_mib=5727), DENSE, width=8, ctx_per_slot=WINDOW
    )
    return replace(made, expose=expose)


def vllm(expose: str = "local") -> Unit:
    made = unit_for(
        rig(HOST), SEVEN_B_SPEC, engine="vllm", width=8, port=8002, ctx_per_slot=WINDOW
    )
    return replace(made, expose=expose)


def host_flag(command: list[str]) -> str | None:
    return command[command.index("--host") + 1] if "--host" in command else None


# --- the render table: expose x engine -> where it listens, and whether it is keyed --


@pytest.mark.parametrize(
    ("build", "expose", "listens"),
    [
        (llama, "local", "127.0.0.1"),
        (llama, "lan", "0.0.0.0"),
        (vllm, "local", "127.0.0.1"),
        (vllm, "lan", "0.0.0.0"),
    ],
)
def test_a_unit_listens_where_its_expose_says_and_lan_alone_is_keyed(
    build: Any, expose: str, listens: str
) -> None:
    unit = build(expose)
    service = service_of(compose_of(unit))

    if unit.engine == "vllm":
        assert host_flag(service["command"]) == listens
        assert "LLAMA_ARG_HOST" not in service["environment"]
    else:
        assert service["environment"]["LLAMA_ARG_HOST"] == listens
        assert host_flag(service["command"]) is None
    if expose == "lan":
        assert service["env_file"] == [str(unitkey.path(unit.host, unit.port))]
    else:
        assert "env_file" not in service


def test_the_compose_file_names_the_key_file_and_never_holds_the_key() -> None:
    unit = llama("lan")
    path, made = unitkey.ensure(unit.host, unit.port)
    key = unitkey.load(unit.host, unit.port)

    document = compose_of(unit)

    assert made and key is not None
    assert str(path) in document
    assert key not in document


def test_a_worker_is_rendered_as_before_whatever_expose_says() -> None:
    head = llama("lan")
    worker = replace(head, role=ROLE_RPC, args={}, extra=("-H", "10.0.0.2"))

    service = service_of(compose_of(replace(worker, image="example.invalid/x:1")))
    assert "env_file" not in service
    assert "LLAMA_ARG_HOST" not in service.get("environment", {})
    assert "--host" not in service["command"]


@pytest.mark.parametrize(
    ("address", "stated", "listens", "keyed"),
    [
        ("http://localhost:8080", None, "127.0.0.1", False),
        ("http://127.0.0.1:8080", None, "127.0.0.1", False),
        (f"http://{HOST}:8080", None, "0.0.0.0", True),
        (f"http://{HOST}:8080", "local", "127.0.0.1", False),
        ("http://localhost:8080", "lan", "0.0.0.0", True),
    ],
)
def test_a_unit_that_states_no_expose_follows_its_address(
    address: str, stated: str | None, listens: str, keyed: bool
) -> None:
    host = host_of(address)
    config = parse(
        "units:\n"
        "  coder:\n"
        f"    address: {address}\n"
        f"    model: {DENSE.name}\n"
        + (f"    expose: {stated}\n" if stated else "")
        + "ladder: [coder]\n"
    )

    (unit,) = units_for(config, {host: rig(host)}, specs=[DENSE], ctx_per_slot=WINDOW)
    service = service_of(compose_of(unit))

    assert config.units["coder"].expose == stated
    assert service["environment"]["LLAMA_ARG_HOST"] == listens
    assert ("env_file" in service) is keyed


# --- this machine's exact names alone decide a unit's bind and key -----------------

#: Spellings the looser match that finds a rig file takes for this machine
#: (`rigfile._names_this_machine`) and the exact names (`LOCAL_RIGS`) do not.
LOOSELY_THIS_MACHINE = ("127.0.0.2", "LOCALHOST", "0.0.0.0", "::")


@pytest.mark.parametrize("spelling", LOOSELY_THIS_MACHINE)
def test_a_name_only_the_loose_match_takes_for_this_machine_listens_beyond_it(
    spelling: str,
) -> None:
    # The two lists disagree on purpose: widening LOCAL_RIGS to the loose
    # match would make such a unit local, and so unkeyed.
    assert rigfile._names_this_machine(spelling)
    assert spelling not in LOCAL_RIGS
    assert listens_beyond_loopback(replace(llama(), extra=("--host", spelling)))
    assert listens_beyond_loopback(replace(llama(), env={"LLAMA_ARG_HOST": spelling}))
    fleet = {
        "units": {
            "near": {
                "address": "http://localhost:8080",
                "launch": {"env": {"LLAMA_ARG_HOST": spelling}},
            }
        }
    }
    assert locked_open(fleet) == (("near", spelling),)


@pytest.mark.parametrize("host", ["127.0.0.2", "0.0.0.0", "[::]"])
def test_a_unit_whose_address_is_only_loosely_this_machine_is_lan_and_keyed(
    host: str,
) -> None:
    address = f"http://{host}:8080"
    config = parse(
        "units:\n"
        "  coder:\n"
        f"    address: {address}\n"
        f"    model: {DENSE.name}\n"
        "ladder: [coder]\n"
    )
    named = host_of(address)

    (unit,) = units_for(config, {named: rig(named)}, specs=[DENSE], ctx_per_slot=WINDOW)
    service = service_of(compose_of(unit))

    assert exposure(None, address=address) == "lan"
    assert service["environment"]["LLAMA_ARG_HOST"] == "0.0.0.0"
    assert service["env_file"] == [str(unitkey.path(unit.host, unit.port))]


def test_a_unit_addressed_at_localhost_in_any_case_is_local_and_unkeyed() -> None:
    # A URL's host is case-insensitive, so the address names `localhost`, one
    # of the exact names: the unit listens on the loopback, which that address
    # reaches, and no list grew to say so.
    address = "http://LOCALHOST:8080"
    config = parse(
        "units:\n"
        "  coder:\n"
        f"    address: {address}\n"
        f"    model: {DENSE.name}\n"
        "ladder: [coder]\n"
    )
    named = host_of(address)

    (unit,) = units_for(config, {named: rig(named)}, specs=[DENSE], ctx_per_slot=WINDOW)
    service = service_of(compose_of(unit))

    assert named == "localhost"
    assert "LOCALHOST" not in LOCAL_RIGS
    assert exposure(None, address=address) == "local"
    assert service["environment"]["LLAMA_ARG_HOST"] == "127.0.0.1"
    assert "env_file" not in service


def test_a_native_unit_follows_no_address_and_listens_on_the_loopback() -> None:
    assert exposure(None, address=f"http://{HOST}:8080", launcher="native") == "local"
    assert exposure(None, address="not an address") == "local"


def test_a_native_unit_cannot_be_exposed() -> None:
    with pytest.raises(ConfigSchemaError, match="launcher native"):
        parse(
            "units:\n"
            "  coder:\n"
            "    address: http://localhost:8080\n"
            "    model: coder-7b\n"
            "    launcher: native\n"
            "    expose: lan\n"
            "ladder: [coder]\n"
        )


def test_a_keyed_unit_is_waited_on_at_health_which_asks_for_no_key() -> None:
    plain = str(_healthcheck(8080)["test"])
    keyed = str(_healthcheck(8080, keyed=True)["test"])

    assert "http://localhost:8080/v1/models" in plain
    assert "http://localhost:8080/health" in keyed
    assert "/v1/models" not in keyed


# --- a unit that states its own host renders byte for byte as it did ---------------


@pytest.fixture
def someone(monkeypatch: pytest.MonkeyPatch) -> None:
    """The HOME the renders below were made under, which their weights paths name."""
    monkeypatch.setenv("HOME", SOMEONE)


@pytest.mark.usefixtures("someone")
def test_a_llama_unit_stating_its_host_flag_renders_as_it_did_before() -> None:
    unit = llama()
    stated = replace(unit, args={**unit.args, "--host": "0.0.0.0"})

    assert compose_of(stated) == LLAMA_STATING_ITS_HOST


@pytest.mark.usefixtures("someone")
def test_a_llama_unit_stating_its_host_env_renders_as_it_did_before() -> None:
    stated = replace(llama(), env={"LLAMA_ARG_HOST": "0.0.0.0"})

    assert compose_of(stated) == LLAMA_STATING_ITS_HOST_ENV


@pytest.mark.usefixtures("someone")
def test_a_vllm_unit_stating_its_host_renders_as_it_did_before() -> None:
    unit = vllm()
    stated = replace(unit, args={**unit.args, "--host": "0.0.0.0"})

    assert compose_of(stated) == VLLM_STATING_ITS_HOST


def test_an_exposed_unit_whose_env_sets_its_own_key_is_refused() -> None:
    unit = replace(llama("lan"), env={"LLAMA_API_KEY": "mine"})

    with pytest.raises(EmitError, match="its env sets LLAMA_API_KEY"):
        compose_of(unit)


def one_unit_config(*, rider_slots: int = 0) -> Any:
    return parse(
        "units:\n"
        "  coder:\n"
        f"    address: http://{HOST}:8080\n"
        "    model: coder-7b\n"
        "    width: 2\n"
        "ladder: [coder]\n"
        + (f"rider_slots: {{coder: {rider_slots}}}\n" if rider_slots else "")
    )


def test_a_stated_host_beyond_this_machine_with_no_key_is_warned_about(
    capsys: pytest.CaptureFixture[str],
) -> None:
    wide = replace(llama(), rungs=("coder",), env={"LLAMA_ARG_HOST": "0.0.0.0"})
    near = replace(llama(), rungs=("near",), extra=("--host", "127.0.0.1"))
    named = replace(llama(), rungs=("named",), extra=("--host", "localhost"))

    _exposure([wide, near, named], one_unit_config())

    said = capsys.readouterr().err
    assert said.count("warning:") == 1
    assert (
        "its launch states where it listens, 0.0.0.0, beyond this machine, and it "
        "asks for no key; state `expose: lan` on coder for one"
    ) in said


@pytest.mark.parametrize(
    ("unit", "stated"),
    [
        (replace(llama("lan"), env={"LLAMA_ARG_HOST": "127.0.0.1"}), "127.0.0.1"),
        (replace(vllm("lan"), extra=("--host", "127.0.0.1")), "127.0.0.1"),
    ],
)
def test_a_keyed_unit_its_launch_keeps_on_the_loopback_is_warned_not_noted(
    unit: Unit, stated: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _exposure([replace(unit, rungs=("coder",))], one_unit_config())

    said = capsys.readouterr().err
    assert "note:" not in said
    assert (
        f"expose: lan gives it a key, but its launch states {stated}, so it listens "
        "there alone; drop the --host or LLAMA_ARG_HOST it states"
    ) in said


def test_the_note_names_where_a_keyed_unit_listens(
    capsys: pytest.CaptureFixture[str],
) -> None:
    unit = replace(llama("lan"), rungs=("coder",), extra=("--host", "192.168.7.20"))

    _exposure([unit], one_unit_config())

    assert ": listens on 192.168.7.20 (expose: lan)" in capsys.readouterr().err


def test_a_shared_keyed_unit_on_another_host_says_the_agent_needs_the_key_file(
    capsys: pytest.CaptureFixture[str],
) -> None:
    unit = replace(llama("lan"), rungs=("coder",))

    _exposure([unit], one_unit_config(rider_slots=1))

    said = capsys.readouterr().err
    path = unitkey.path(HOST, unit.port)
    assert (
        f"It is shared with riders, and the rig agent on {HOST} looks its key up in "
        "its own data folder, in unit-keys/ under the name of the address its own "
        f"config gives the unit: {path.name} for http://{HOST}:{unit.port}, "
        f"localhost-{unit.port}.env for http://localhost:{unit.port}. `mcgyvr emit` "
        "does not put it there: copy this file there under that name at mode 0600, "
        "or the agent does not share the unit and says once on its stderr which "
        "file it lacks"
    ) in said


def test_a_unit_stating_its_host_env_in_another_case_is_given_the_host_too() -> None:
    service = service_of(compose_of(replace(llama(), env={"llama_arg_host": "x"})))

    assert service["environment"] == {
        "LLAMA_ARG_HOST": "127.0.0.1",
        "llama_arg_host": "x",
    }


def test_a_lock_that_states_no_expose_on_another_host_gains_its_key(
    tmp_path: Path,
) -> None:
    fleet = {
        "rigs": {LOCKED_RIG: {}},
        "units": {"small": plain("small", 8080), "big": plain("big", 8082)},
        "fleets": {
            "one": {"layout": {LOCKED_RIG: [["small", "awake"], ["big", "awake"]]}}
        },
    }

    (written,) = emit_locked(fleet, tmp_path)
    services = yaml.safe_load(written.read_text("utf-8"))["services"]

    for name, port in (("small", 8080), ("big", 8082)):
        assert services[name]["env_file"] == [str(unitkey.path(LOCKED_RIG, port))]
        assert services[name]["environment"] == {"LLAMA_ARG_HOST": "0.0.0.0"}
    assert "http://localhost:8080/health" in str(services["small"]["healthcheck"])


def test_a_locked_unit_follows_its_address_and_its_lock_states_where_it_listens() -> (
    None
):
    fleet = {
        "units": {
            "far": {
                "address": f"http://{HOST}:8080",
                "launch": {"env": {"LLAMA_ARG_HOST": "0.0.0.0"}},
            },
            "kept": {
                "address": f"http://{HOST}:8081",
                "expose": "lan",
                "launch": {"argv": ["--host", "127.0.0.1"]},
            },
            "near": {
                "address": "http://localhost:8082",
                "launch": {"env": {"LLAMA_ARG_HOST": "0.0.0.0"}},
            },
            "old_vllm": {
                "address": "http://localhost:8083",
                "engine": "vllm",
                "launch": {"argv": ["--port", "8083"]},
            },
        }
    }

    assert locked_keyed(fleet) == (
        ("far", HOST, 8080, "0.0.0.0"),
        ("kept", HOST, 8081, "127.0.0.1"),
    )
    assert locked_open(fleet) == (("near", "0.0.0.0"), ("old_vllm", "0.0.0.0"))


def test_a_stated_host_on_an_exposed_unit_is_kept_and_given_the_key() -> None:
    unit = llama("lan")
    stated = replace(unit, extra=("--host", "192.168.7.20"))
    service = service_of(compose_of(stated))

    assert service["command"][-2:] == ["--host", "192.168.7.20"]
    assert service["env_file"] == [str(unitkey.path(unit.host, unit.port))]


# --- the key file -------------------------------------------------------------------


def test_the_key_is_made_once_at_mode_0600_and_kept_from_one_emit_to_the_next() -> None:
    path, made = unitkey.ensure(HOST, 8080)
    key = unitkey.load(HOST, 8080)
    again, made_again = unitkey.ensure(HOST, 8080)

    assert made and not made_again and again == path
    assert key is not None and unitkey.KEY.fullmatch(key)
    assert unitkey.load(HOST, 8080) == key
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert path.read_text(encoding="ascii") == (
        f"LLAMA_API_KEY={key}\nVLLM_API_KEY={key}\n"
    )
    assert path.is_relative_to(Path.home() / ".local" / "state" / "mcgyvr")


def test_a_key_file_others_can_read_is_refused_and_never_sent() -> None:
    path, _ = unitkey.ensure(HOST, 8080)
    path.chmod(0o644)

    with pytest.raises(unitkey.UnitKeyError, match="chmod 600"):
        unitkey.load(HOST, 8080)
    with pytest.raises(unitkey.UnitKeyError):
        unitkey.ensure(HOST, 8080)


def test_a_link_in_the_key_files_place_is_refused() -> None:
    path = unitkey.path(HOST, 8080)
    path.parent.mkdir(parents=True, mode=0o700)
    elsewhere = path.parent / "elsewhere"
    elsewhere.write_text(f"LLAMA_API_KEY={A_KEY}\nVLLM_API_KEY={A_KEY}\n")
    elsewhere.chmod(0o600)
    path.symlink_to(elsewhere)

    with pytest.raises(unitkey.UnitKeyError):
        unitkey.load(HOST, 8080)


# --- mcgyvr's own clients send the key ---------------------------------------------


@dataclass
class KeyedServer:
    """A server that asks for a key as llama-server b11960 does: every path but
    `/health` answers 401 without the bearer token it was given."""

    key: str
    seen: list[tuple[str, str | None]] = field(default_factory=list)
    server: ThreadingHTTPServer | None = None

    @property
    def address(self) -> str:
        assert self.server is not None
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    @property
    def port(self) -> int:
        assert self.server is not None
        return int(self.server.server_address[1])


@pytest.fixture
def keyed() -> Iterator[KeyedServer]:
    made = KeyedServer(key=A_KEY)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_GET(self) -> None:
            said = self.headers.get("Authorization")
            made.seen.append((self.path, said))
            if self.path != "/health" and said != f"Bearer {made.key}":
                self.send_response(401)
                self.end_headers()
                return
            body = b'{"data": [{"id": "coder-7b"}]}' if "models" in self.path else b"[]"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            said = self.headers.get("Authorization")
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            made.seen.append((f"POST {self.path}", said))
            ok = said == f"Bearer {made.key}"
            body = b'{"choices": []}' if ok else b'{"error": "Unauthorized"}'
            self.send_response(200 if ok else 401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    made.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    made.server.daemon_threads = True
    threading.Thread(target=made.server.serve_forever, daemon=True).start()
    yield made
    made.server.shutdown()


def keep(key: str, port: int) -> Path:
    """Write the key file `ensure` would, holding `key`."""
    path = unitkey.path("127.0.0.1", port)
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.write_text(f"LLAMA_API_KEY={key}\nVLLM_API_KEY={key}\n", encoding="ascii")
    path.chmod(0o600)
    return path


def config_for(address: str, *, extra: str = "") -> str:
    return (
        "units:\n"
        "  coder:\n"
        f"    address: {address}\n"
        "    model: coder-7b\n"
        "    width: 2\n"
        "    expose: lan\n"
        f"{extra}"
        "ladder: [coder]\n"
    )


def test_a_dispatch_and_the_availability_probe_send_the_units_key(
    keyed: KeyedServer,
) -> None:
    keep(keyed.key, keyed.port)
    endpoint = unit_map(parse(config_for(keyed.address))).bind("coder")

    assert runner.request_headers(endpoint)["Authorization"] == f"Bearer {keyed.key}"
    assert probe_endpoint(endpoint).live
    assert keyed.seen == [("/v1/models", f"Bearer {keyed.key}")]


def test_a_unit_with_no_key_file_is_sent_no_key(keyed: KeyedServer) -> None:
    endpoint = unit_map(parse(config_for(keyed.address))).bind("coder")

    assert "Authorization" not in runner.request_headers(endpoint)
    assert not probe_endpoint(endpoint).live


def llama_target(address: str) -> detect.ProbeTarget:
    """The target setup's discovery sweeps for a llama-server at `address`."""
    return detect.ProbeTarget(
        name="llama-server", base_url=address, api="openai", host=host_of(address)
    )


def test_setup_discovery_lists_a_unit_that_asks_for_its_key(
    keyed: KeyedServer,
) -> None:
    keep(keyed.key, keyed.port)

    found = detect.probe(llama_target(keyed.address))

    assert found is not None and found.models == ("coder-7b",)
    assert keyed.seen == [
        ("/v1/models", f"Bearer {keyed.key}"),
        ("/props", f"Bearer {keyed.key}"),
    ]


def test_setup_discovery_sends_no_key_where_none_is_kept(keyed: KeyedServer) -> None:
    assert detect.probe(llama_target(keyed.address)) is None
    assert keyed.seen == [("/v1/models", None)]


def test_a_sweep_sends_a_unit_its_key_and_no_other_host_or_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The key is kept for one address; every other address the sweep tries,
    on another host or another port of the unit's own, is asked keyless."""
    unitkey.ensure("unit-a.lan", 8080)
    asked: list[tuple[str, str | None]] = []

    def urlopen(request: Any, timeout: float) -> Any:
        asked.append((request.full_url, request.get_header("Authorization")))
        raise OSError("nothing listens on an invented machine")

    monkeypatch.setattr("mcgyvr.detect.urllib.request.urlopen", urlopen)

    assert detect.probe_all(detect.targets_for(("unit-a.lan", "rig-b.lan"))) == ()
    assert len(asked) == 2 * len(detect.PORT_CONVENTIONS)
    assert [(url, said) for url, said in asked if said is not None] == [
        (
            "http://unit-a.lan:8080/v1/models",
            f"Bearer {unitkey.load('unit-a.lan', 8080)}",
        )
    ]

    asked.clear()
    assert detect.probe_all(detect.targets_for(("rig-b.lan",))) == ()
    assert asked and all(said is None for _, said in asked)


@pytest.fixture
def redirecting(keyed: KeyedServer) -> Iterator[str]:
    """A server that sends every request on to the keyed server."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header("Location", f"{keyed.address}{self.path}")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_a_units_key_does_not_follow_its_redirect_to_another_address(
    keyed: KeyedServer, redirecting: str
) -> None:
    keep(keyed.key, int(redirecting.rsplit(":", 1)[1]))

    assert detect.probe(llama_target(redirecting)) is None
    assert keyed.seen == [("/v1/models", None)]


def test_a_key_file_setup_cannot_trust_is_noted_and_its_unit_asked_keyless(
    keyed: KeyedServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    keep(keyed.key, keyed.port).chmod(0o644)
    monkeypatch.setattr(detect, "_reading", lambda: {})
    monkeypatch.setattr(detect, "detect_docker", lambda: (True, "an invented daemon"))

    found = detect.detect((llama_target(keyed.address),))

    assert found.backends == ()
    assert keyed.seen == [("/v1/models", None)]
    assert any(
        note.startswith("Unit key: ") and f"{keyed.address} was asked without" in note
        for note in found.notes
    ), found.notes


def test_a_data_folder_setup_cannot_name_is_noted_and_detection_goes_on(
    keyed: KeyedServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative `$MCGYVR_DATA` names no folder a key could be read from:
    setup notes it and asks keyless, as it did before it read keys at all."""
    monkeypatch.setenv("MCGYVR_DATA", "relative/data")
    monkeypatch.setattr(detect, "_reading", lambda: {})
    monkeypatch.setattr(detect, "detect_docker", lambda: (True, "an invented daemon"))

    found = detect.detect((llama_target(keyed.address),))

    assert found.backends == ()
    assert keyed.seen == [("/v1/models", None)]
    assert any(
        note.startswith("Unit key: ") and "$MCGYVR_DATA" in note for note in found.notes
    ), found.notes


def test_the_sampler_reads_a_keyed_units_window_and_slots_with_its_key(
    keyed: KeyedServer,
) -> None:
    keep(keyed.key, keyed.port)

    sampler.served({"address": f"{keyed.address}/v1", "engine": "llama.cpp"})
    sampler.served({"address": f"{keyed.address}/v1", "engine": "vllm"})

    assert keyed.seen == [
        ("/props", f"Bearer {keyed.key}"),
        ("/v1/models", f"Bearer {keyed.key}"),
    ]


def test_the_sampler_sends_no_key_to_a_unit_none_is_kept_for(
    keyed: KeyedServer,
) -> None:
    assert sampler.served({"address": f"{keyed.address}/v1"}) == {}
    assert keyed.seen == [("/props", None)]


@pytest.fixture
def polled(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str | None]]:
    """The status pages the runner reads, with the key each was read with."""
    seen: list[tuple[str, str | None]] = []

    def get_text(url: str, timeout: float, *, key: str | None = None) -> str:
        seen.append((url, key))
        return '[{"id": 0, "is_processing": false}]'

    monkeypatch.setattr(runner, "_get_text", get_text)
    return seen


def test_the_status_poll_of_an_exposed_unit_sends_its_key(
    polled: list[tuple[str, str | None]],
) -> None:
    keep(A_KEY, 9123)

    busy = runner.unit_in_flight(
        "coder", "http://127.0.0.1:9123", None, 2, own_key=True
    )

    assert busy == 0
    assert polled == [("http://127.0.0.1:9123/slots", A_KEY)]


def test_a_hosted_unit_and_an_address_not_your_own_are_never_sent_a_units_key(
    keyed: KeyedServer,
    polled: list[tuple[str, str | None]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keep(keyed.key, keyed.port)
    monkeypatch.setenv("EXAMPLE_API_KEY", "a-hosted-key")
    hosted = unit_map(
        parse(config_for(keyed.address, extra="    api_key_env: EXAMPLE_API_KEY\n"))
    ).bind("coder")

    assert runner.request_headers(hosted)["Authorization"] == "Bearer a-hosted-key"
    assert runner.unit_in_flight("coder", keyed.address, None, 2) == 0
    assert polled == [(f"{keyed.address}/slots", None)]


def test_a_key_file_that_cannot_be_trusted_stops_the_dispatch_by_name(
    keyed: KeyedServer,
) -> None:
    keep(keyed.key, keyed.port).chmod(0o640)
    endpoint = unit_map(parse(config_for(keyed.address))).bind("coder")

    with pytest.raises(UnitUnavailableError, match="chmod 600"):
        runner.request_headers(endpoint)


def test_the_relay_carries_the_units_key_and_never_shows_it() -> None:
    keep(A_KEY, 9123)

    target = Target.of_url("http://127.0.0.1:9123/v1/chat/completions")

    assert target.key == A_KEY
    assert A_KEY not in repr(target)
    assert Target.of_url("http://127.0.0.1:9124/v1/chat/completions").key is None


@pytest.fixture
def ridden(tmp_path: Path) -> Iterator[Host]:
    made = _host(tmp_path)
    yield made
    made.unit.release.set()
    made.relays.cancel_all()
    assert made.unit.server is not None
    made.unit.server.shutdown()


def test_a_ride_reaches_an_exposed_unit_with_its_key(ridden: Host) -> None:
    keep(A_KEY, ridden.unit.port)

    ridden.ride(_ride_body())

    assert ridden.ended() == {"request_id": "q1", "outcome": "complete"}
    assert ridden.unit.authorized == [f"Bearer {A_KEY}"]


def test_a_ride_to_a_unit_with_no_key_is_posted_as_before(ridden: Host) -> None:
    ridden.ride(_ride_body())

    assert ridden.ended() == {"request_id": "q1", "outcome": "complete"}
    assert ridden.unit.authorized == [None]


def test_the_relays_slots_read_of_an_exposed_unit_sends_its_key(
    keyed: KeyedServer,
) -> None:
    keep(keyed.key, keyed.port)

    page = relay_page(Target.of_url(f"{keyed.address}/v1/chat/completions"))

    assert page == b"[]"
    assert keyed.seen == [("/slots", f"Bearer {keyed.key}")]


def test_the_relay_refuses_a_key_file_it_cannot_trust() -> None:
    keep(A_KEY, 9123).chmod(0o644)

    with pytest.raises(ValueError, match="chmod 600"):
        Target.of_url("http://127.0.0.1:9123/v1/chat/completions")


def test_the_doors_probe_sends_the_key_on_stdin_and_a_plain_unit_as_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    class Done:
        returncode = 0
        stdout = '{"data": [{"id": "coder-7b"}]}'

    def ssh(host: str, command: str, **kwargs: Any) -> Done:
        calls.append((command, kwargs))
        return Done()

    monkeypatch.setattr(servelib, "ssh", ssh)

    assert servelib.models_served("localhost", 8080, key=A_KEY) == ["coder-7b"]
    assert servelib.models_served("localhost", 8080) == ["coder-7b"]
    (keyed_command, keyed_kwargs), (plain_command, plain_kwargs) = calls
    assert keyed_command == "curl -sf -H @- http://localhost:8080/v1/models"
    assert keyed_kwargs == {"timeout": 30, "input": f"Authorization: Bearer {A_KEY}\n"}
    assert A_KEY not in keyed_command
    assert plain_command == "curl -sf http://localhost:8080/v1/models"
    assert plain_kwargs == {"timeout": 30}


def test_the_doors_probe_of_this_machine_sends_the_key_without_ssh(
    tmp_path: Path, keyed: KeyedServer
) -> None:
    door = fake_door(tmp_path)
    stub = ssh_stub(tmp_path / "stubs")
    env = clean_env(stub.parent)
    env.update(RUN_HOST="localhost", MCGYVR_LOCAL_TRANSPORT="direct")
    code = (
        "from mcgyvr.serving import servelib\n"
        f"print(servelib.models_served('localhost', {keyed.port}, key={keyed.key!r}))\n"
        f"print(servelib.models_served('localhost', {keyed.port}))\n"
    )

    result = under(door, [sys.executable, "-c", code], env)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["['coder-7b']", "None"]
    assert keyed.seen == [("/v1/models", f"Bearer {keyed.key}"), ("/v1/models", None)]
    assert not (tmp_path / "stubs" / "ssh.log").exists(), "ssh was reached"


def test_the_door_reads_a_services_key_from_the_file_its_env_file_names(
    tmp_path: Path,
) -> None:
    unit = llama("lan")
    path, _ = unitkey.ensure(unit.host, unit.port)
    compose = tmp_path / "compose.yaml"
    compose.write_text(compose_of(unit), encoding="utf-8")

    (service,) = servelib.services(compose)

    assert service.key_file == str(path)
    assert service.key() == unitkey.load(unit.host, unit.port)


# --- what runs on the rig: the door's read and the lock's harness send the key ------


def test_the_rig_reader_sends_a_keyed_ports_key_on_curls_stdin(
    tmp_path: Path, keyed: KeyedServer
) -> None:
    stubs = tmp_path / "bin"
    onedoor.executable(stubs / "docker", "#!/usr/bin/env bash\nexit 0\n")
    onedoor.executable(stubs / "nvidia-smi", "#!/usr/bin/env bash\nexit 0\n")
    env = {**os.environ, "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}"}
    script = (GATE_SCRIPTS / "rig-units.sh").read_text(encoding="utf-8")
    wanted = f"set -- llama.cpp:{keyed.port}\n" + script

    def rows(prefix: str) -> list[str]:
        done = subprocess.run(
            ["bash", "-s"],
            input=prefix + wanted,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert done.returncode == 0, done.stderr
        return [row for row in done.stdout.splitlines() if row.startswith("status=")]

    assert rows(read.key_function({keyed.port: keyed.key})) == [
        f"status={keyed.port},{base64.b64encode(b'[]').decode()}"
    ]
    assert rows(read.key_function({})) == []
    assert keyed.seen == [("/slots", f"Bearer {keyed.key}"), ("/slots", None)]
    assert keyed.key not in read.key_function({}) + wanted


def test_the_door_finds_the_keys_of_the_units_it_reads_on_a_rig() -> None:
    unitkey.ensure(HOST, 8080)
    fleet = read.Live(
        "f",
        Path("/nowhere"),
        {
            "fleets": {
                "f": {"layout": {HOST: [["coder", "awake"], ["plain", "awake"]]}}
            },
            "units": {
                "coder": {"address": f"http://{HOST}:8080"},
                "plain": {"address": f"http://{HOST}:8081"},
            },
        },
    )

    keys = read.unit_keys(fleet, HOST)

    assert keys == {8080: unitkey.load(HOST, 8080)}
    assert f"8080) printf %s '{keys[8080]}' ;;" in read.key_function(keys)


def test_the_harness_shipped_with_a_key_sends_it_on_every_request(
    keyed: KeyedServer,
) -> None:
    source = Path(harness.__file__).read_text(encoding="utf-8")
    shipped = types.ModuleType("shipped_harness")
    exec(
        compile(harness.with_key(source, keyed.key), "harness", "exec"),
        shipped.__dict__,
    )

    shipped.HttpTransport().get(f"{keyed.address}/v1/models", 5)
    shipped.HttpTransport().post(f"{keyed.address}/v1/chat/completions", {}, 5)
    assert shipped._page(f"{keyed.address}/slots") == "[]"

    assert keyed.seen == [
        ("/v1/models", f"Bearer {keyed.key}"),
        ("POST /v1/chat/completions", f"Bearer {keyed.key}"),
        ("/slots", f"Bearer {keyed.key}"),
    ]
    assert harness.with_key(source, None) == source
    assert harness.UNIT_KEY is None


def test_the_harness_takes_no_key_that_could_break_out_of_its_line() -> None:
    source = Path(harness.__file__).read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="only letters"):
        harness.with_key(source, "x'\nimport os")
    with pytest.raises(ValueError, match="key line once"):
        harness.with_key("no line here", A_KEY)


def test_a_door_read_of_a_keyed_unit_ships_its_key_on_stdin_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = onedoor.fixture_repo(tmp_path, host="box2")
    reads.go_live(tmp_path)
    reads.reading(root, status=(f"8001,{reads.page(reads.metrics(0))}",))
    stubs = onedoor.stubs_dir(root)
    (stubs / "harness.json").write_text(
        reads.Rig()("box2_3b", json.dumps({})), encoding="utf-8"
    )
    ssh = stubs / "ssh"
    stub = ssh.read_text(encoding="utf-8")
    for kept, was in (
        ("bash", '"bash -s")\n    cat >/dev/null'),
        ("harness", '*"mcgyvr-harness"*) cat >/dev/null'),
    ):
        assert stub.count(was) == 1, was
        stub = stub.replace(
            was, was.replace("cat >/dev/null", f'cat > "$STUBS/{kept}.in"')
        )
    ssh.write_text(stub, encoding="utf-8")
    monkeypatch.setenv("MCGYVR_DATA", str(root / "data"))
    unitkey.ensure("box2", 8001)
    key = unitkey.load("box2", 8001)
    assert key is not None

    result = reads.read_door(root, "--probe", "box2_3b")

    assert result.returncode == 0, (result.stdout, result.stderr[-2000:])
    assert f"8001) printf %s '{key}' ;;" in (stubs / "bash.in").read_text("utf-8")
    assert f"UNIT_KEY: str | None = {key!r}" in (stubs / "harness.in").read_text(
        "utf-8"
    )
    assert key not in "\n".join(onedoor.ssh_log(root))
    assert key not in result.stdout + result.stderr


# --- the rig agent shares a keyed unit only with its key ----------------------------


def agent_config(address: str, *, expose: str | None = None) -> Any:
    return parse(
        "units:\n"
        "  coder:\n"
        f"    address: {address}\n"
        "    model: coder-7b\n"
        "    width: 2\n"
        "    window: 4096\n"
        + (f"    expose: {expose}\n" if expose else "")
        + "ladder: [coder]\n"
        "rider_slots: {coder: 1}\n"
    )


@pytest.fixture
def fresh_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hitchhike, "_asked", {})


@pytest.mark.usefixtures("fresh_probe")
def test_an_agent_with_no_key_for_a_unit_that_asks_for_one_does_not_share_it(
    keyed: KeyedServer,
) -> None:
    config = agent_config(keyed.address)
    units, _ = hitchhike.shared_units(config)

    kept, notes = hitchhike.keyed_shares(config, units)

    path = unitkey.path("127.0.0.1", keyed.port)
    assert kept == ()
    assert notes == (
        f"unit 'coder' is not shared with riders: its server asks for a key and "
        f"this agent holds none in {path}; put the key there at mode 0600 "
        "(`mcgyvr fleet key coder` prints it on the machine whose `mcgyvr emit` "
        "made it)",
    )
    assert keyed.seen == [("/v1/models", None)]


@pytest.mark.usefixtures("fresh_probe")
def test_an_agent_holding_the_key_shares_the_unit_and_asks_nothing(
    keyed: KeyedServer,
) -> None:
    keep(keyed.key, keyed.port)
    config = agent_config(keyed.address)
    units, _ = hitchhike.shared_units(config)

    assert hitchhike.keyed_shares(config, units) == (units, ())
    assert keyed.seen == []


@pytest.mark.usefixtures("fresh_probe")
def test_an_agent_shares_a_keyless_unit_as_before_and_asks_once_a_while(
    keyed: KeyedServer,
) -> None:
    config = agent_config("http://127.0.0.1:9")  # nothing listens there
    units, _ = hitchhike.shared_units(config)

    assert hitchhike.keyed_shares(config, units) == (units, ())
    assert hitchhike.keyed_shares(config, units) == (units, ())


def test_an_agent_whose_config_keys_a_remote_unit_needs_its_key_without_asking() -> (
    None
):
    config = agent_config(f"http://{HOST}:8080")
    units, _ = hitchhike.shared_units(config)

    kept, notes = hitchhike.keyed_shares(config, units)

    assert kept == ()
    assert str(unitkey.path(HOST, 8080)) in notes[0]


# --- the CLI: emit makes the key and says so; fleet key prints it -------------------


@pytest.fixture
def install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A scanned rig that is another machine, a config naming it, and an out dir."""
    scans = tmp_path / "scans"
    scans.mkdir()
    (scans / f"{HOST}.json").write_text(
        records.rig_file(
            Scan.of(
                host=HOST,
                vram_mib=12288,
                ram_gb=64.0,
                disk_free_gb=900.0,
                cores=10,
                threads=20,
                bandwidth_gbps=41.2,
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(records.RIGS_ENV, str(scans))
    config = tmp_path / "mcgyvr.yaml"
    monkeypatch.setenv(CONFIG_PATH_ENV, str(config))
    out = tmp_path / "compose"
    out.mkdir()
    return config, out


def declare(config: Path, expose: str | None, *, rider_slots: int = 0) -> None:
    config.write_text(
        "units:\n"
        "  coder:\n"
        f"    address: http://{HOST}:8080\n"
        "    model: 'qwen2.5-coder:3b'\n"
        f"    rig: {HOST}\n"
        "    width: 2\n"
        + (f"    expose: {expose}\n" if expose else "")
        + "    launch:\n"
        "      vram_gb: 2.4\n"
        "      disk_gb: 1.9\n"
        "      kv_cache_dtype_k: f16\n"
        "      kv_cache_dtype_v: f16\n"
        "ladder:\n"
        "- coder\n"
        + (f"rider_slots: {{coder: {rider_slots}}}\n" if rider_slots else ""),
        encoding="utf-8",
    )


def emit(out: Path) -> int:
    return main(["emit", "--out", str(out), "--ctx-per-slot", str(WINDOW)])


SLUG = f"{HOST}:8080/qwen2.5-coder:3b/llama.cpp"


def test_emit_warns_that_a_unit_stating_local_is_one_its_address_cannot_reach(
    install: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    config, out = install
    declare(config, "local")

    assert emit(out) == Exit.OK

    said = capsys.readouterr().err
    assert (
        f"warning: {SLUG}: listens on 127.0.0.1 alone, as its unit states "
        f"(expose: local), and its address names {HOST}: that name reaches the "
        "machine's network address, never 127.0.0.1, so nothing dials it by that "
        "name, this machine included. State `expose: lan` on coder, or leave "
        "`expose` out (an address on another host is `lan` by default), to listen "
        "on every interface behind a key mcgyvr makes\n"
    ) in said
    assert not unitkey.path(HOST, 8080).exists()


def test_emit_warns_how_a_shared_unit_stating_local_shows_on_the_rig(
    install: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    config, out = install
    declare(config, "local", rider_slots=1)

    assert emit(out) == Exit.OK

    assert (
        "It is shared with riders, so the rig agent advertises it with no free "
        "slot and says `unit 'coder' is shared with no free slot: its server does "
        "not say what it has in flight` once on its stderr; riders are matched "
        f"elsewhere and no ride fails. On {HOST}, address the unit as "
        "http://localhost:8080 in the rig agent's own config"
    ) in capsys.readouterr().err


@pytest.mark.parametrize("stated", [None, "lan"])
def test_emit_makes_a_lan_units_key_names_it_and_fleet_key_prints_it(
    stated: str | None,
    install: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    config, out = install
    declare(config, stated)

    assert emit(out) == Exit.OK
    said = capsys.readouterr().err
    path = unitkey.path(HOST, 8080)
    key = unitkey.load(HOST, 8080)
    assert key is not None
    assert f"note: {SLUG}: listens on 0.0.0.0 (expose: lan)" in said
    assert f"made its key in {path} (mode 0600)" in said
    assert "`mcgyvr fleet key coder` prints it" in said
    assert key not in said
    (written,) = out.iterdir()
    assert key not in written.read_text(encoding="utf-8")
    assert f"env_file:\n    - {path}\n" in written.read_text(encoding="utf-8")
    assert key not in config.read_text(encoding="utf-8")

    assert emit(out) == Exit.OK
    assert f"its key is in {path}" in capsys.readouterr().err
    assert unitkey.load(HOST, 8080) == key

    assert main(["fleet", "key", "coder"]) == Exit.OK
    assert capsys.readouterr().out == f"{key}\n"


def test_fleet_key_refuses_a_unit_that_is_not_exposed(
    install: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    config, _ = install
    declare(config, "local")

    assert main(["fleet", "key", "coder"]) == Exit.REFUSED
    assert "expose: local" in capsys.readouterr().err


def test_fleet_key_refuses_an_exposed_unit_emit_has_not_keyed_yet(
    install: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    config, _ = install
    declare(config, None)

    assert main(["fleet", "key", "coder"]) == Exit.REFUSED
    assert "`mcgyvr emit` makes it" in capsys.readouterr().err
    assert os.listdir(Path.home()) == [".claude"]


# --- what the render was before the default moved, for a unit stating its host ------
# Rendered by 160c0fa98 (the commit before units listened on the loopback by
# default) under the invented HOME `SOMEONE`.

LLAMA_STATING_ITS_HOST = """\
services:
  qwen2.5-coder-3b-8080:
    command:
    - --alias
    - qwen2.5-coder-3b
    - --fit
    - 'off'
    - --host
    - 0.0.0.0
    - --model
    - /home/someone/.cache/mcgyvr/weights/qwen2.5-coder-3b.gguf
    - --parallel
    - '8'
    - --port
    - '8080'
    - -b
    - '512'
    - -c
    - '32768'
    - -ctk
    - f16
    - -ctv
    - f16
    - -fa
    - 'on'
    - -ngl
    - '99'
    - -t
    - '10'
    - -ub
    - '512'
    - --chat-template-kwargs
    - '{"enable_thinking":false}'
    container_name: mcgyvr-gpu-box.example-qwen2.5-coder-3b-8080
    deploy:
      resources:
        reservations:
          devices:
          - capabilities:
            - gpu
            device_ids:
            - '0'
            driver: nvidia
    environment:
      LLAMA_ARG_HOST: 0.0.0.0
    image: ghcr.io/ggml-org/llama.cpp:server-cuda-b11960
    network_mode: host
    restart: unless-stopped
    volumes:
    - /home/someone/.cache/mcgyvr/weights:/home/someone/.cache/mcgyvr/weights:ro
    - /home/someone/.cache/mcgyvr/weights:/models:ro
"""


LLAMA_STATING_ITS_HOST_ENV = """\
services:
  qwen2.5-coder-3b-8080:
    command:
    - --alias
    - qwen2.5-coder-3b
    - --fit
    - 'off'
    - --model
    - /home/someone/.cache/mcgyvr/weights/qwen2.5-coder-3b.gguf
    - --parallel
    - '8'
    - --port
    - '8080'
    - -b
    - '512'
    - -c
    - '32768'
    - -ctk
    - f16
    - -ctv
    - f16
    - -fa
    - 'on'
    - -ngl
    - '99'
    - -t
    - '10'
    - -ub
    - '512'
    - --chat-template-kwargs
    - '{"enable_thinking":false}'
    container_name: mcgyvr-gpu-box.example-qwen2.5-coder-3b-8080
    deploy:
      resources:
        reservations:
          devices:
          - capabilities:
            - gpu
            device_ids:
            - '0'
            driver: nvidia
    environment:
      LLAMA_ARG_HOST: 0.0.0.0
    image: ghcr.io/ggml-org/llama.cpp:server-cuda-b11960
    network_mode: host
    restart: unless-stopped
    volumes:
    - /home/someone/.cache/mcgyvr/weights:/home/someone/.cache/mcgyvr/weights:ro
    - /home/someone/.cache/mcgyvr/weights:/models:ro
"""


VLLM_STATING_ITS_HOST = """\
services:
  Qwen-Qwen2.5-Coder-7B-Instruct-AWQ-8002:
    command:
    - Qwen/Qwen2.5-Coder-7B-Instruct-AWQ
    - --host
    - 0.0.0.0
    - --kv-cache-dtype
    - auto
    - --max-model-len
    - '4096'
    - --max-num-seqs
    - '8'
    - --port
    - '8002'
    - --gpu-memory-utilization
    - '0.68'
    container_name: mcgyvr-gpu-box.example-Qwen-Qwen2.5-Coder-7B-Instruct-AWQ-8002
    deploy:
      resources:
        reservations:
          devices:
          - capabilities:
            - gpu
            device_ids:
            - '0'
            driver: nvidia
    environment:
      HF_HUB_OFFLINE: '1'
    image: vllm/vllm-openai:v0.26.0
    ipc: host
    network_mode: host
    restart: unless-stopped
    volumes:
    - /home/someone/.cache/huggingface:/root/.cache/huggingface:ro
"""
