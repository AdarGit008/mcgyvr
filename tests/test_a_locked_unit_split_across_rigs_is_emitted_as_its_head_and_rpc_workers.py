"""A locked unit split across rigs is emitted as its head and its rpc workers.

With several machines (#731 item 6), a chat or agent unit is
one pipeline-parallel unit spanning them, a llama.cpp head plus rpc-server
workers on the other rigs. Promises:

* A locked unit split across two rigs is emitted as its stated head on the head
  rig and an rpc-server worker on the other, and the files are the ones the
  unlocked path writes for the same unit: the worker rig's document byte for
  byte, the head's service field for field.
* A worker shard with no ``bind`` listens at the private IPv4 its rig file
  records, and that rendering is the same as stating that address as ``bind``.
* A worker rig with no recorded address is refused by name, and so is an
  overlay (100.64.0.0/10) address when the head's rig file records no address
  on that overlay. A head whose ``--rpc`` names other workers is refused.
* A locked fleet with no unit split across rigs is emitted exactly as before.

Machines, cards, addresses and the model are invented.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.emit import (
    LockedLaunchError,
    _service_name,
    emit_all,
    emit_locked,
    resolved_launch,
)
from mcgyvr.serving import ROLE_SERVE, rigfile, spec_name, units_for
from tests import usermode
from tests.test_a_unit_split_across_cards_is_launched_as_the_split_it_was_sized import (
    MODEL,
    WINDOW,
    config,
    scans,
)

A = "box-a.example"
B = "box-b.example"
IMAGE = "example/llama-rpc:1"
#: Documentation addresses (RFC 5737): the worker's LAN address, and the
#: head's.
LAN_B = "10.20.0.20"
LAN_A = "10.20.0.10"
#: Overlay addresses (RFC 6598), as a tailnet hands them out.
OVERLAY_B = "100.100.1.20"
OVERLAY_A = "100.100.1.10"


def unlocked(tmp_path: Path, bind: str) -> tuple[Any, ...]:
    """The units the unlocked path sizes for a unit split over box-a and box-b."""
    shards = [{"rig": A, "gpu": 0}, {"rig": B, "gpu": 0, "bind": bind}]
    made = config(tmp_path, {"shards": shards}, image=IMAGE)
    return units_for(made, scans(), specs=(), ctx_per_slot=WINDOW)


def locked(head: Any, shards: list[dict[str, Any]]) -> dict[str, Any]:
    """A locked fleet whose one unit carries the launch stamped from `head`."""
    stamped = resolved_launch(head)
    launch = {**stamped["launch"], "shards": shards}
    unit = {
        "unit_id": "unt-big",
        "engine": stamped["engine"],
        "image": stamped["image"],
        "container": stamped["container"],
        "model": MODEL,
        "rig": A,
        "address": f"http://{A}:{head.port}",
        "launch": launch,
    }
    return {
        "rigs": {A: {}, B: {}},
        "units": {"big": unit},
        "fleets": {"one": {"layout": {A: [["big", "awake"]], B: [["big", "awake"]]}}},
    }


def services(path: Path) -> dict[str, Any]:
    return dict(yaml.safe_load(path.read_text(encoding="utf-8"))["services"])


def record_rig(rig: str, reached_at: str | None, *addresses: tuple[str, str]) -> None:
    """Save a rig file for `rig` whose network section says these addresses."""
    payload = usermode.scan_payload()
    payload["network"] = {
        "reached_at": reached_at,
        "ipv4": [{"interface": name, "address": ip} for name, ip in addresses],
    }
    rigfile.write(rigfile.from_reading(rig, payload))


@pytest.fixture(autouse=True)
def _rigs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCGYVR_RIGS", str(tmp_path / "rigs"))


def test_a_split_unit_emits_its_head_and_worker_as_the_unlocked_path_does(
    tmp_path: Path,
) -> None:
    head, worker = unlocked(tmp_path, LAN_B)
    emit_all((head, worker), tmp_path / "unlocked")
    shards = [{"rig": A, "gpu": 0}, {"rig": B, "gpu": 0, "bind": LAN_B}]
    written = emit_locked(locked(head, shards), tmp_path / "locked")

    assert sorted(path.name for path in written) == [
        spec_name(A, "one"),
        spec_name(B, "one"),
    ]
    on_b = (tmp_path / "locked" / spec_name(B, "one")).read_text("utf-8")
    assert on_b == (tmp_path / "unlocked" / spec_name(B, None)).read_text("utf-8")
    on_a = services(tmp_path / "unlocked" / spec_name(A, None))
    assert services(tmp_path / "locked" / spec_name(A, "one")) == {
        "big": on_a[_service_name(head)]
    }

    (rpc,) = services(tmp_path / "locked" / spec_name(B, "one")).values()
    assert rpc["entrypoint"] == ["rpc-server"]
    assert rpc["command"] == ["--port", "50052", "-H", LAN_B, "-d", "CUDA0"]
    assert rpc["deploy"]["resources"]["reservations"]["devices"][0]["device_ids"] == [
        "0"
    ]
    command = services(tmp_path / "locked" / spec_name(A, "one"))["big"]["command"]
    assert command[command.index("--rpc") + 1] == f"{LAN_B}:50052"
    assert head.role == ROLE_SERVE and worker.port == 50052


def test_a_worker_with_no_bind_listens_at_the_address_its_rig_file_records(
    tmp_path: Path,
) -> None:
    head, _ = unlocked(tmp_path, LAN_B)
    stated = [{"rig": A, "gpu": 0}, {"rig": B, "gpu": 0, "bind": LAN_B}]
    recorded = [{"rig": A, "gpu": 0}, {"rig": B, "gpu": 0}]
    record_rig(B, LAN_B, ("lo", "127.0.0.1"), ("eth0", LAN_B))

    emit_locked(locked(head, stated), tmp_path / "stated")
    emit_locked(locked(head, recorded), tmp_path / "recorded")

    for rig in (A, B):
        name = spec_name(rig, "one")
        assert (tmp_path / "recorded" / name).read_text("utf-8") == (
            tmp_path / "stated" / name
        ).read_text("utf-8")


def test_a_worker_rig_with_no_rig_file_is_refused_by_name(tmp_path: Path) -> None:
    head, _ = unlocked(tmp_path, LAN_B)
    out = tmp_path / "locked"
    fleet = locked(head, [{"rig": A, "gpu": 0}, {"rig": B, "gpu": 0}])

    with pytest.raises(LockedLaunchError, match=rf"big: .*{B} has no recorded address"):
        emit_locked(fleet, out)
    assert not out.exists()


def test_a_worker_rig_whose_file_records_no_address_is_refused_with_its_reason(
    tmp_path: Path,
) -> None:
    head, _ = unlocked(tmp_path, LAN_B)
    record_rig(B, None, ("eth0", LAN_B), ("eth1", "10.30.0.30"))
    fleet = locked(head, [{"rig": A, "gpu": 0}, {"rig": B, "gpu": 0}])

    with pytest.raises(LockedLaunchError, match=rf"{B} .*several private IPv4"):
        emit_locked(fleet, tmp_path / "locked")


def test_an_overlay_address_is_refused_when_the_head_is_not_on_that_overlay(
    tmp_path: Path,
) -> None:
    head, _ = unlocked(tmp_path, OVERLAY_B)
    record_rig(B, OVERLAY_B, ("tailscale0", OVERLAY_B))
    record_rig(A, LAN_A, ("eth0", LAN_A))
    fleet = locked(head, [{"rig": A, "gpu": 0}, {"rig": B, "gpu": 0}])

    with pytest.raises(
        LockedLaunchError, match=rf"{B} records {OVERLAY_B} .*overlay.*{A}"
    ):
        emit_locked(fleet, tmp_path / "locked")


def test_an_overlay_address_is_emitted_when_the_head_shares_that_overlay(
    tmp_path: Path,
) -> None:
    head, _ = unlocked(tmp_path, OVERLAY_B)
    record_rig(B, OVERLAY_B, ("tailscale0", OVERLAY_B))
    record_rig(A, LAN_A, ("eth0", LAN_A), ("tailscale0", OVERLAY_A))
    fleet = locked(head, [{"rig": A, "gpu": 0}, {"rig": B, "gpu": 0}])

    emit_locked(fleet, tmp_path / "locked")

    (rpc,) = services(tmp_path / "locked" / spec_name(B, "one")).values()
    assert rpc["command"] == ["--port", "50052", "-H", OVERLAY_B, "-d", "CUDA0"]


def test_a_head_whose_rpc_names_other_workers_is_refused(tmp_path: Path) -> None:
    head, _ = unlocked(tmp_path, LAN_B)
    moved = "10.20.0.99"
    fleet = locked(head, [{"rig": A, "gpu": 0}, {"rig": B, "gpu": 0, "bind": moved}])

    with pytest.raises(LockedLaunchError, match=rf"--rpc {LAN_B}:50052.*{moved}"):
        emit_locked(fleet, tmp_path / "locked")


#: The healthcheck command `small` carries, which `big` waits on.
PROBE = (
    "curl -sf http://localhost:8080/v1/models >/dev/null 2>&1 || "
    "wget -q -O- http://localhost:8080/v1/models >/dev/null 2>&1"
)
#: What `emit_locked` wrote for the unsplit fleet below on main at v0.5.1,
#: before a unit could span rigs.
UNSPLIT_DOCUMENT = f"""\
services:
  big:
    command:
    - --model
    - /srv/weights/big.gguf
    - --port
    - '8082'
    container_name: mcgyvr-big
    depends_on:
      small:
        condition: service_healthy
    deploy:
      resources:
        reservations:
          devices:
          - capabilities:
            - gpu
            device_ids:
            - '0'
            - '1'
            driver: nvidia
    environment:
      LLAMA_ARG_HOST: 0.0.0.0
    image: example.invalid/server:pinned
    network_mode: host
    restart: unless-stopped
    volumes:
    - /srv/weights:/srv/weights:ro
  small:
    command:
    - --model
    - /srv/weights/small.gguf
    - --port
    - '8080'
    container_name: mcgyvr-small
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
    healthcheck:
      interval: 5s
      retries: 3
      start_period: 600s
      test:
      - CMD-SHELL
      - {PROBE}
      timeout: 3s
    image: example.invalid/server:pinned
    network_mode: host
    restart: unless-stopped
    volumes:
    - /srv/weights:/srv/weights:ro
"""


def plain(name: str, port: int, shards: Any = None) -> dict[str, Any]:
    launch: dict[str, Any] = {
        "argv": ["--model", f"/srv/weights/{name}.gguf", "--port", str(port)],
        "env": {"LLAMA_ARG_HOST": "0.0.0.0"},
        "volumes": ["/srv/weights:/srv/weights:ro"],
    }
    if shards is not None:
        launch["shards"] = shards
    return {
        "unit_id": f"unt-{name}",
        "engine": "llama.cpp",
        "image": "example.invalid/server:pinned",
        "container": f"mcgyvr-{name}",
        "rig": A,
        "address": f"http://{A}:{port}",
        "launch": launch,
    }


def test_a_locked_fleet_with_no_unit_across_rigs_is_emitted_as_before(
    tmp_path: Path,
) -> None:
    unsplit = {
        "rigs": {A: {}},
        "units": {
            "small": plain("small", 8080),
            "big": plain("big", 8082, [{"rig": A, "gpu": 0}, {"rig": A, "gpu": 1}]),
        },
        "fleets": {"one": {"layout": {A: [["small", "awake"], ["big", "awake"]]}}},
    }

    (written,) = emit_locked(unsplit, tmp_path)

    assert written.name == spec_name(A, "one")
    assert written.read_text("utf-8") == UNSPLIT_DOCUMENT
