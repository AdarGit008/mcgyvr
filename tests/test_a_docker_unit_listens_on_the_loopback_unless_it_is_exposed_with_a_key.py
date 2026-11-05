"""A docker unit listens on the loopback unless it is exposed, and then only with a key.

Promise: a llama.cpp or vLLM server mcgyvr renders into a container listens on
127.0.0.1 unless its unit states ``expose: lan``. A unit that does listens on
every interface and asks every request for a key mcgyvr makes the first time
``mcgyvr emit`` writes it: kept at mode 0600 in the data folder, named in the
compose service's ``env_file`` and never written into the compose file, and
sent by mcgyvr's own requests to the unit (a dispatch, a status poll, the
availability probe, the door's probes and the rig agent's relay) as a bearer
token. A unit that states its own ``--host`` or ``LLAMA_ARG_HOST`` renders byte
for byte as it did before units listened on the loopback by default, and a unit
from a config that names no ``expose`` listens on the loopback. ``mcgyvr fleet
key`` prints the key, for a client of the owner's own.

The machines are invented, and so are their addresses.
"""

from __future__ import annotations

import os
import stat
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

import mcgyvr.runner as runner
from mcgyvr import unitkey
from mcgyvr.availability import probe_endpoint
from mcgyvr.cli import main
from mcgyvr.cli.commands.ladder import _exposure
from mcgyvr.config import CONFIG_PATH_ENV, ConfigSchemaError, parse
from mcgyvr.emit import EmitError, _healthcheck, render_compose
from mcgyvr.exits import Exit
from mcgyvr.local_pool import SourceUnavailableError, source_map
from mcgyvr.rig.relay import Target
from mcgyvr.rig.relay import _page as relay_page
from mcgyvr.scan import Scan
from mcgyvr.serving import ROLE_HEADLESS, ROLE_RPC, Unit, servelib, unit_for
from tests import records
from tests.doors import DENSE, SEVEN_B_SPEC, rig, service_of
from tests.relays import Host, _host, _ride_body
from tests.sizings import WINDOW

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
    service = service_of(render_compose(unit))

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

    document = render_compose(unit)

    assert made and key is not None
    assert str(path) in document
    assert key not in document


def test_a_worker_and_a_headless_rank_are_rendered_as_before_whatever_expose_says() -> (
    None
):
    head = llama("lan")
    worker = replace(head, role=ROLE_RPC, args={}, extra=("-H", "10.0.0.2"))
    rank = replace(vllm("lan"), role=ROLE_HEADLESS)

    for unit in (worker, rank):
        service = service_of(render_compose(replace(unit, image="example.invalid/x:1")))
        assert "env_file" not in service
        assert "LLAMA_ARG_HOST" not in service.get("environment", {})
        assert "--host" not in service["command"]


def test_a_unit_from_a_config_that_names_no_expose_listens_on_the_loopback() -> None:
    config = parse(
        "units:\n"
        "  coder:\n"
        f"    address: http://{HOST}:8080\n"
        "    model: coder-7b\n"
        "ladder: [coder]\n"
    )

    assert config.units["coder"].expose == "local"
    assert service_of(render_compose(llama()))["environment"] == {
        "LLAMA_ARG_HOST": "127.0.0.1"
    }


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

    assert render_compose(stated) == LLAMA_STATING_ITS_HOST


@pytest.mark.usefixtures("someone")
def test_a_llama_unit_stating_its_host_env_renders_as_it_did_before() -> None:
    stated = replace(llama(), env={"LLAMA_ARG_HOST": "0.0.0.0"})

    assert render_compose(stated) == LLAMA_STATING_ITS_HOST_ENV


@pytest.mark.usefixtures("someone")
def test_a_vllm_unit_stating_its_host_renders_as_it_did_before() -> None:
    unit = vllm()
    stated = replace(unit, args={**unit.args, "--host": "0.0.0.0"})

    assert render_compose(stated) == VLLM_STATING_ITS_HOST


def test_an_exposed_unit_whose_env_sets_its_own_key_is_refused() -> None:
    unit = replace(llama("lan"), env={"LLAMA_API_KEY": "mine"})

    with pytest.raises(EmitError, match="its env sets LLAMA_API_KEY"):
        render_compose(unit)


def test_a_stated_host_beyond_the_loopback_with_no_key_is_warned_about(
    capsys: pytest.CaptureFixture[str],
) -> None:
    wide = replace(llama(), rungs=("coder",), env={"LLAMA_ARG_HOST": "0.0.0.0"})
    loopback = replace(llama(), rungs=("near",), extra=("--host", "127.0.0.1"))

    _exposure([wide, loopback])

    said = capsys.readouterr().err
    assert said.count("warning:") == 1
    assert (
        "its launch states where it listens, beyond 127.0.0.1, and it asks for "
        "no key; state `expose: lan` on coder for one"
    ) in said


def test_a_stated_host_on_an_exposed_unit_is_kept_and_given_the_key() -> None:
    unit = llama("lan")
    stated = replace(unit, extra=("--host", "192.168.7.20"))
    service = service_of(render_compose(stated))

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
    endpoint = source_map(parse(config_for(keyed.address))).bind("coder")

    assert runner.request_headers(endpoint)["Authorization"] == f"Bearer {keyed.key}"
    assert probe_endpoint(endpoint).live
    assert keyed.seen == [("/v1/models", f"Bearer {keyed.key}")]


def test_a_unit_with_no_key_file_is_sent_no_key(keyed: KeyedServer) -> None:
    endpoint = source_map(parse(config_for(keyed.address))).bind("coder")

    assert "Authorization" not in runner.request_headers(endpoint)
    assert not probe_endpoint(endpoint).live


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
    hosted = source_map(
        parse(config_for(keyed.address, extra="    api_key_env: EXAMPLE_API_KEY\n"))
    ).bind("coder")

    assert runner.request_headers(hosted)["Authorization"] == "Bearer a-hosted-key"
    assert runner.unit_in_flight("coder", keyed.address, None, 2) == 0
    assert polled == [(f"{keyed.address}/slots", None)]


def test_a_key_file_that_cannot_be_trusted_stops_the_dispatch_by_name(
    keyed: KeyedServer,
) -> None:
    keep(keyed.key, keyed.port).chmod(0o640)
    endpoint = source_map(parse(config_for(keyed.address))).bind("coder")

    with pytest.raises(SourceUnavailableError, match="chmod 600"):
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


def test_the_door_reads_a_services_key_from_the_file_its_env_file_names(
    tmp_path: Path,
) -> None:
    unit = llama("lan")
    path, _ = unitkey.ensure(unit.host, unit.port)
    compose = tmp_path / "compose.yaml"
    compose.write_text(render_compose(unit), encoding="utf-8")

    (service,) = servelib.services(compose)

    assert service.key_file == str(path)
    assert service.key() == unitkey.load(unit.host, unit.port)


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


def declare(config: Path, expose: str | None) -> None:
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
        "- coder\n",
        encoding="utf-8",
    )


def emit(out: Path) -> int:
    return main(["emit", "--out", str(out), "--ctx-per-slot", str(WINDOW)])


def test_emit_warns_that_a_unit_another_machine_dials_now_listens_on_the_loopback(
    install: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    config, out = install
    declare(config, None)

    assert emit(out) == Exit.OK

    said = capsys.readouterr().err
    assert (
        f"warning: {HOST}:8080/qwen2.5-coder:3b/llama.cpp: listens on 127.0.0.1 alone "
        f"(expose: local, the default), and its address names {HOST}: no other "
        "machine reaches it. State `expose: lan` on coder to listen on every "
        "interface, behind a key mcgyvr makes"
    ) in said.replace("\n", " ")
    assert not unitkey.path(HOST, 8080).exists()


def test_emit_makes_an_exposed_units_key_names_it_and_fleet_key_prints_it(
    install: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    config, out = install
    declare(config, "lan")

    assert emit(out) == Exit.OK
    said = capsys.readouterr().err
    path = unitkey.path(HOST, 8080)
    key = unitkey.load(HOST, 8080)
    assert key is not None
    assert f"made its key in {path} (mode 0600)" in said
    assert "`mcgyvr fleet key coder` prints it" in said
    assert key not in said
    (written,) = out.iterdir()
    assert key not in written.read_text(encoding="utf-8")
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
    declare(config, None)

    assert main(["fleet", "key", "coder"]) == Exit.REFUSED
    assert "expose: local" in capsys.readouterr().err


def test_fleet_key_refuses_an_exposed_unit_emit_has_not_keyed_yet(
    install: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    config, _ = install
    declare(config, "lan")

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
