"""``mcgyvr setup --accept-unsampled`` approves the user's own fleet for live
work, and no more.

Setup with flags starts no container, so no sample runs on what it binds, and
``--accept-unsampled`` is the user's acknowledgment that it is locked on no
evidence (without it nothing is locked:
``test_a_fleet_setup_could_not_sample_is_locked_only_once_the_user_acknowledges``).

Live admission refuses a run under the live fleet until the config folder's
``live.json`` names a promoted fleet whose lock it can
hold the rigs to. A stranger has no dev evidence to lock from, so ``init``
approves what it bound itself, through the one path live reads:

* **Only hosted units bound:** ``init`` locks a fleet ``own`` whose layout
  names no rig, on no evidence (:func:`mcgyvr.fleet.lock.write_unsampled`; the
  lock says ``mcgyvr setup`` approved it), promotes it beside the promoted
  ones, ``<config folder>/fleets/own@<today>/``, holding the setup it wrote,
  and ``live.json`` names it, as ``mcgyvr fleet use`` would. Live admission
  then admits a run without reading any rig: the fleet has none, and a hosted
  unit is not a machine of the user's.
* **A machine of the user's is not approved by init:** a unit on a rig, or a
  "hosted" unit whose address is a loopback, private, link-local or otherwise
  non-public address, or a name only a local network answers (``localhost``, a
  name with no dot, ``.local``...). Such a machine is approved only by a read of
  it, which ``init`` does not take; ``init`` says so. Nor is an mcorch setup,
  whose units a fleet with no rig cannot hold awake.
* **A live run is refused** when the config it loaded holds a unit on a rig the
  live fleet does not lay out there, whatever the fleet: re-running ``init``
  after a local server appeared, or adding one by hand, does not ride on an
  approval of hosted units.
* **A re-run of init re-approves its own fleet** in a new folder
  (``own@<today>-2`` on the same day), and names that live; the old folder is
  kept. A fleet live that is not init's own is never replaced, and an ``init``
  that wrote nothing approves nothing.

The machines are invented; detection is substituted, so nothing is probed.
"""

from __future__ import annotations

import ipaddress
import json
import os
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr import cli
from mcgyvr.cli.commands.setup import _read_rig, _rig_id
from mcgyvr.detect import Backend, Detection
from mcgyvr.exits import Exit
from mcgyvr.fleet import admission
from mcgyvr.fleet.admit import admit_live
from mcgyvr.fleet.promote import LOCAL_SUFFIXES, LOCK_DIR, PromoteRefusedError
from mcgyvr.fleet.roots import fleets_dir, is_fleet_name, live_file, live_fleet

HOSTED = "model=hosted-model,address=https://api.hosted.example/v1,api_key_env=K"
HOSTED_UNIT = "api_hosted-model"
#: A second hosted unit, for a re-run of init that binds more.
OTHER = "model=other-model,address=https://api.other.example/v1,api_key_env=K"

TARGET = "src/pkg/messy.py"
CONTRACT = f"""\
id: impl
task_type: code
task: Set VALUE to 1.
target: {TARGET}
stop_conditions: ["The value is not stated."]
demonstration: ["sh -c 'grep -q VALUE {TARGET}'"]
acceptance: ["sh -c 'exit 0'"]
limits:
  max_output_tokens: 256
scope:
  allow: ["src/**"]
"""


def _found(*backends: Backend) -> Detection:
    return Detection(backends=backends, provenance={"backends": "substituted"})


#: A server on a machine of the user's, as init would find it.
LOCAL = Backend(
    name="llama.cpp",
    base_url="http://localhost:8080/v1",
    api="openai",
    models=("small-model",),
    how="substituted",
)


def _init(
    monkeypatch: pytest.MonkeyPatch,
    setup: Path,
    *flags: str,
    found: Detection,
) -> int:
    monkeypatch.setattr("mcgyvr.initialize.detect", lambda _targets: found)
    return cli.main(["setup", "--accept-unsampled", *flags, str(setup)])


def _no_read(rig: str, run_id: str, probe: Sequence[str]) -> int:
    raise AssertionError(f"admission read {rig}, and the own fleet has no rig")


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _run(
    tmp_path: Path,
    setup: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, list[str]]:
    """``mcgyvr run`` from ``setup``: its exit, its stderr and the units dispatched."""
    import mcgyvr.drive as drive

    repo = tmp_path / "repo"
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / TARGET).write_text("x = 0\n", encoding="utf-8")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull}
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t.invalid", *args],
            cwd=repo,
            env=env,
            check=True,
            capture_output=True,
        )
    contract = tmp_path / "impl.yaml"
    contract.write_text(CONTRACT, encoding="utf-8")
    dispatched: list[str] = []

    def dispatch(_map: object, rung: str, _request: object, **_: object) -> object:
        dispatched.append(rung)
        raise AssertionError(f"{rung} was dispatched")

    monkeypatch.setattr(drive, "dispatch", dispatch)
    monkeypatch.setenv("MCGYVR_CONFIG", str(setup))
    capsys.readouterr()
    argv = ["run", str(contract), "--repo", str(repo), "--sandbox", "tempdir"]
    return cli.main(argv), capsys.readouterr().err, dispatched


def test_a_fresh_init_of_hosted_units_makes_its_own_fleet_live(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup = tmp_path / "setup"
    assert _init(monkeypatch, setup, "--api", HOSTED, found=_found()) == 0
    said = capsys.readouterr().out

    name = f"own@{_today()}"
    assert live_fleet() == name
    folder = fleets_dir() / name
    assert str(folder) in said and str(live_file()) in said, said

    # The setup init wrote, as a fleet whose layout names no rig.
    wrote = yaml.safe_load((setup / "fleet.yaml").read_text(encoding="utf-8"))
    live = yaml.safe_load((folder / "fleet.yaml").read_text(encoding="utf-8"))
    assert live["units"] == wrote["units"]
    assert live["fleets"] == {"own": {"layout": {}}}
    policy = yaml.safe_load((folder / "policy.yaml").read_text(encoding="utf-8"))
    assert policy["ladder"] == [HOSTED_UNIT]

    # The lock says who approved it: init, not dev evidence.
    lock = json.loads((folder / LOCK_DIR / "own.json").read_text(encoding="utf-8"))
    assert lock["approved_by"] == "mcgyvr setup"
    assert lock["next"] == [] and lock["switches"] == []

    admitted = admission.admit(reader=_no_read)
    assert admitted.fleet == "own"
    assert admitted.admitted and admitted.commands == []


def _first_host(block: int, prefix: int, *, v6: bool = False) -> str:
    """The first host of the address block ``block/prefix``, from its numbers."""
    network = (ipaddress.IPv6Network if v6 else ipaddress.IPv4Network)((block, prefix))
    return str(next(network.hosts()))


#: Where a unit bound as hosted would be a machine of the user's: the blocks
#: are the RFCs' own (built from their numbers, so no machine is spelled), the
#: names are ``localhost``, one label, and each suffix the product reads as
#: local.
USERS_MACHINES = (
    "127.0.0.1",
    "::1",
    _first_host(0x0A000000, 8),  # RFC 1918
    _first_host(0xAC100000, 12),  # RFC 1918
    _first_host(0xC0A80000, 16),  # RFC 1918
    _first_host(0xA9FE0000, 16),  # link-local, RFC 3927
    _first_host(0x64400000, 10),  # shared, RFC 6598
    _first_host(0xFD << 120, 8, v6=True),  # unique local, RFC 4193
    _first_host(0xFE80 << 112, 10, v6=True),  # link-local, RFC 4291
    "::ffff:" + _first_host(0xC0A80000, 16),  # an RFC 1918 address, mapped
    "192.0.2.20",  # documentation, RFC 5737: no public address either
    # The older spellings inet_aton reads, and so every resolver: octal,
    # hexadecimal, fewer parts, padded parts (joined here, as the octal one
    # reads as another address to a reader of plain decimal).
    ".".join(("0177", "0", "0", "1")),
    "0x7f.0.0.1",
    "127.1",
    "127.000.000.001",
    "10.1",
    str(ipaddress.IPv6Address((0x64FF9B << 96) | 0x7F000001)),  # NAT64, RFC 6052
    # Dots a resolver's IDNA step reads as dots: ideographic, fullwidth and
    # halfwidth ideographic full stops.
    "127\u30020.0.1",
    "127.0\uff0e0.1",
    "127.0.0\uff611",
    "localhost",
    "rig",
    *(f"rig{suffix}" for suffix in LOCAL_SUFFIXES),
)


@pytest.mark.parametrize("host", USERS_MACHINES)
def test_a_hosted_unit_at_a_machine_of_the_users_is_not_approved(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    host: str,
) -> None:
    where = f"[{host}]" if ":" in host else host
    spec = f"model=small-model,address=http://{where}:8080/v1,api_key_env=K"
    assert _init(monkeypatch, tmp_path / "setup", "--api", spec, found=_found()) == 0
    said = capsys.readouterr().out

    assert not live_file().exists()
    assert not fleets_dir().exists()
    assert "No fleet was made live" in said and "api_small-model" in said, said
    assert "not approved" in said, said


def test_an_mcorch_setup_is_not_approved_by_init(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    flags = ("--api", HOSTED, "--jev", HOSTED_UNIT, "--mcorch", HOSTED_UNIT)
    setup = tmp_path / "setup"
    assert _init(monkeypatch, setup, *flags, "--window", "8192", found=_found()) == 0
    said = capsys.readouterr().out

    assert not live_file().exists()
    assert not fleets_dir().exists()
    assert "No fleet was made live" in said and "mcorch" in said, said


#: The rig id a substituted local read hands back, shaped as a rig id is.
RIG_ID = "rig-" + "2" * 64

#: Two invented remote rigs, and the rig ids a substituted remote read hands
#: back for each, shaped as rig ids are.
REMOTE_RIG_IDS = {"box1": "rig-" + "1" * 64, "box2": "rig-" + "3" * 64}

#: What the one reader answers for the invented local machine: its machine id,
#: its one card (what names it), and the capacity scan of the same card.
LOCAL_SCAN: dict[str, Any] = {
    "machine": {"id": "0" * 16, "host": "localhost", "kernel": "6.1.0"},
    "cards": [
        {
            "vendor": "nvidia",
            "index": 0,
            "name": "FakeGPU",
            "total_mib": 8192,
            "used_mib": 0,
            "free_mib": 8192,
        }
    ],
    "unread": [],
    "unsized": [],
    "gpus": [
        {
            "index": 0,
            "name": "FakeGPU",
            "vram": {"total_mib": 8192, "used_mib": 0, "free_mib": 8192},
        }
    ],
    "snapshot": {"hostname": "localhost", "driver": "550.54.15"},
}


def test_a_local_gpu_is_read_then_approved_by_init(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A unit on this machine is approved once init reads it: the fleet lays
    out the rig ``localhost`` (pinned by the read's rig id), and a hosted unit
    beside it stays hosted."""
    setup = tmp_path / "setup"
    found = _found(LOCAL)
    _reads(monkeypatch, lambda rig: RIG_ID)
    assert _init(monkeypatch, setup, "--api", HOSTED, found=found) == 0
    said = capsys.readouterr().out

    name = f"own@{_today()}"
    assert live_fleet() == name, said
    folder = fleets_dir() / name
    live = yaml.safe_load((folder / "fleet.yaml").read_text(encoding="utf-8"))
    assert live["rigs"] == {"localhost": {"rig_id": RIG_ID}}
    assert live["fleets"] == {
        "own": {"layout": {"localhost": [["local_small-model", "awake"]]}}
    }
    assert live["units"]["local_small-model"]["rig"] == "localhost"
    assert live["units"]["local_small-model"]["unit_id"]
    assert live["units"]["api_hosted-model"].get("rig") is None
    lock = json.loads((folder / LOCK_DIR / "own.json").read_text(encoding="utf-8"))
    assert lock["approved_by"] == "mcgyvr setup"
    assert lock["layout_sha256"]

    # Given the door reads the local rig back and finds the unit awake, the
    # fleet is admitted: nothing to clean, nothing to restore. Live admission
    # on this rig still runs through the door's (ssh) read until its local path
    # lands; this proves the part init wrote — layout, lock, unit id — admits.
    unit_id = live["units"]["local_small-model"]["unit_id"]
    plan = admit_live(
        folder,
        live,
        "own",
        {
            "localhost": {
                "rig_id": RIG_ID,
                "units": {unit_id: "awake"},
                "foreign": [],
            }
        },
    )
    assert plan.clean == [] and plan.restore == [], plan


def test_a_hosted_unit_at_a_user_machine_is_not_approved_beside_a_local_rig(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A local rig read and approved does not carry a hosted unit at a machine
    of the user's: the rig is read, the hosted unit is refused."""
    setup = tmp_path / "setup"
    mine = (
        f"model=small-model,address=http://{_first_host(0xC0A80000, 16)}:8080/v1,"
        "api_key_env=K"
    )
    _reads(monkeypatch, lambda rig: RIG_ID)
    assert _init(monkeypatch, setup, "--api", mine, found=_found(LOCAL)) == 0
    said = capsys.readouterr().out

    assert not live_file().exists()
    assert not fleets_dir().exists()
    assert "No fleet was made live" in said and "machine of yours" in said, said


def _reads(monkeypatch: pytest.MonkeyPatch, named: Callable[[str], str]) -> None:
    """Every rig init reads answers with a reading ``named`` names the rig id
    of (or refuses, as ``named`` raises): the read stands in for the machine."""
    monkeypatch.setattr("mcgyvr.cli.commands.setup._read_rig", lambda rig: {"named": named(rig)})
    monkeypatch.setattr("mcgyvr.cli.commands.setup._rig_id", lambda rig, reading: reading["named"])


def test_read_rig_runs_the_one_reader_locally(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The genuine reader runs ``rigscan`` on this machine and writes the rig
    file, and the rig id is the one its reading names."""
    from mcgyvr.fleet import ids
    from mcgyvr.serving import rigfile

    monkeypatch.setattr("mcgyvr.serving.rigscan.scan", lambda **_: LOCAL_SCAN)
    rigs = tmp_path / "rigs"
    monkeypatch.setattr("mcgyvr.serving.rigfile.rigs_dir", lambda: rigs)

    reading = _read_rig("localhost")

    assert _rig_id("localhost", reading) == ids.rig_id(LOCAL_SCAN)
    saved = rigfile.read("localhost")
    assert saved is not None and saved.rig == "localhost"


def _done(
    stdout: str, returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_read_rig_reads_a_remote_one_over_the_read_only_ssh_line_and_records_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The remote reader ships ``rigscan`` over ``ssh_read_only`` — not the
    door — and writes the rig's file, the one its ``serve up``'s gate 2 asks
    for; the rig id is the one its reading names."""
    from mcgyvr.fleet import ids
    from mcgyvr.serving import gatelib, rigfile

    seen: dict[str, str] = {}

    def ssh_read_only(
        host: str, command: str, timeout: float | None = 120.0
    ) -> subprocess.CompletedProcess[str]:
        seen["host"] = host
        seen["command"] = command
        return _done(json.dumps(LOCAL_SCAN))

    monkeypatch.setattr("mcgyvr.serving.gatelib.ssh_read_only", ssh_read_only)
    rigs = tmp_path / "rigs"
    monkeypatch.setattr("mcgyvr.serving.rigfile.rigs_dir", lambda: rigs)

    reading = _read_rig("box.invalid")

    assert _rig_id("box.invalid", reading) == ids.rig_id(LOCAL_SCAN)
    assert seen["host"] == "box.invalid"
    assert seen["command"] == gatelib.scan_read_command()
    assert rigfile.read("box.invalid") is not None


def test_read_rig_refuses_on_a_nonzero_ssh_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rig that cannot answer the read is a refusal, not a traceback."""

    def ssh_read_only(
        host: str, command: str, timeout: float | None = 120.0
    ) -> subprocess.CompletedProcess[str]:
        return _done("", returncode=2, stderr="no route to host")

    monkeypatch.setattr("mcgyvr.serving.gatelib.ssh_read_only", ssh_read_only)

    with pytest.raises(PromoteRefusedError) as excinfo:
        _read_rig("box.invalid")
    assert "box.invalid" in str(excinfo.value)
    assert "no route to host" in str(excinfo.value)


def test_a_rig_whose_reading_names_no_rig_id_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A reading whose card size was not read hashes no rig id: refused."""
    unread = {
        **LOCAL_SCAN,
        "cards": [{**LOCAL_SCAN["cards"][0], "total_mib": None}],
        "unread": [{"field": "card.nvidia.0.total", "why": "printed [N/A]"}],
    }

    def ssh_read_only(
        host: str, command: str, timeout: float | None = 120.0
    ) -> subprocess.CompletedProcess[str]:
        return _done(json.dumps(unread))

    monkeypatch.setattr("mcgyvr.serving.gatelib.ssh_read_only", ssh_read_only)

    monkeypatch.setenv("MCGYVR_RIGS", str(tmp_path / "rigs"))
    with pytest.raises(PromoteRefusedError) as excinfo:
        _rig_id("box.invalid", _read_rig("box.invalid"))
    assert "box.invalid" in str(excinfo.value)
    assert "does not read" in str(excinfo.value)


def _remote(host: str, model: str, *, name: str = "llama.cpp") -> Backend:
    """A backend answering on ``host``, as init would find it over the network."""
    return Backend(
        name=name,
        kind="llama.cpp",
        base_url=f"http://{host}:8080/v1",
        api="openai",
        models=(model,),
        how="substituted",
        host=host,
    )


def test_a_unit_on_a_remote_rig_is_read_then_approved_by_init(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A unit on a machine other than this one is approved once init reads that
    machine over ssh: the fleet lays out the remote rig, pinned by the read's
    rig id, and a hosted unit beside it stays hosted."""
    setup = tmp_path / "setup"
    _reads(monkeypatch, lambda rig: RIG_ID)
    remote = _remote("box.invalid", "small-model")
    assert _init(monkeypatch, setup, "--api", HOSTED, found=_found(remote)) == 0
    said = capsys.readouterr().out

    name = f"own@{_today()}"
    assert live_fleet() == name, said
    folder = fleets_dir() / name
    live = yaml.safe_load((folder / "fleet.yaml").read_text(encoding="utf-8"))
    assert live["rigs"] == {"box.invalid": {"rig_id": RIG_ID}}
    assert live["fleets"] == {
        "own": {"layout": {"box.invalid": [["local_small-model", "awake"]]}}
    }
    assert live["units"]["local_small-model"]["rig"] == "box.invalid"
    assert live["units"]["local_small-model"]["unit_id"]
    assert live["units"]["api_hosted-model"].get("rig") is None
    lock = json.loads((folder / LOCK_DIR / "own.json").read_text(encoding="utf-8"))
    assert lock["approved_by"] == "mcgyvr setup"
    assert lock["layout_sha256"]


def test_a_fleet_on_two_remote_rigs_is_read_then_approved_by_init(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every remote rig the setup lays a unit on is read before the fleet is
    approved: the layout lays each out awake, both rig ids are pinned, and the
    lock holds the multi-rig layout."""
    setup = tmp_path / "setup"
    read: list[str] = []

    def read_rig(rig: str) -> str:
        read.append(rig)
        return REMOTE_RIG_IDS[rig]

    _reads(monkeypatch, read_rig)
    assert (
        _init(
            monkeypatch,
            setup,
            found=_found(
                _remote("box1", "small-model", name="llama.cpp"),
                _remote("box2", "other-model", name="llama.cpp-2"),
            ),
        )
        == 0
    )
    said = capsys.readouterr().out

    name = f"own@{_today()}"
    assert live_fleet() == name, said
    folder = fleets_dir() / name
    live = yaml.safe_load((folder / "fleet.yaml").read_text(encoding="utf-8"))
    assert read == ["box1", "box2"]
    assert live["rigs"] == {
        "box1": {"rig_id": REMOTE_RIG_IDS["box1"]},
        "box2": {"rig_id": REMOTE_RIG_IDS["box2"]},
    }
    assert live["fleets"] == {
        "own": {
            "layout": {
                "box1": [["local_small-model", "awake"]],
                "box2": [["local_other-model", "awake"]],
            }
        }
    }
    assert live["units"]["local_small-model"]["rig"] == "box1"
    assert live["units"]["local_other-model"]["rig"] == "box2"
    assert live["units"]["local_small-model"]["unit_id"]
    assert live["units"]["local_other-model"]["unit_id"]
    lock = json.loads((folder / LOCK_DIR / "own.json").read_text(encoding="utf-8"))
    assert lock["approved_by"] == "mcgyvr setup"
    assert lock["layout_sha256"]


def test_a_remote_rig_that_cannot_be_read_is_not_approved(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A rig that cannot be read is a refusal: the fleet is not approved and
    nothing is written to the fleets folder or named live."""
    setup = tmp_path / "setup"

    def unreadable(rig: str) -> str:
        raise PromoteRefusedError(f"{rig}: cannot be read")

    _reads(monkeypatch, unreadable)
    assert (
        _init(
            monkeypatch,
            setup,
            "--api",
            HOSTED,
            found=_found(_remote("box.invalid", "small-model")),
        )
        == 0
    )
    said = capsys.readouterr().out

    assert not live_file().exists()
    assert not fleets_dir().exists()
    assert "No fleet was made live" in said and "box.invalid" in said, said


#: A "hosted" unit at a machine of the user's, bound or written after the
#: fleet was approved: init refuses to approve it, and a live run to it too.
MINE = "http://127.0.0.1:8080/v1"
#: The same machine, its dots ideographic full stops (U+3002): a resolver's IDNA
#: step reads each one as a dot.
MINE_IDEOGRAPHIC = "http://127\u30020\u30020\u30021:8080/v1"
#: Where each way of adding a machine of the user's after the approval puts it.
ADDED = {
    "reinit-hosted": MINE,
    "edit-hosted": MINE,
    "reinit-ideo": MINE_IDEOGRAPHIC,
    "edit-ideo": MINE_IDEOGRAPHIC,
}


@pytest.mark.parametrize("how", ["edit", *ADDED])
def test_a_live_run_refuses_a_unit_on_a_rig_its_live_fleet_does_not_lay_out(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    how: str,
) -> None:
    setup = tmp_path / "setup"
    assert _init(monkeypatch, setup, "--api", HOSTED, found=_found()) == 0
    approved = live_fleet()
    assert approved == f"own@{_today()}"

    if how.startswith("reinit-"):
        mine = f"model=small-model,address={ADDED[how]},api_key_env=K"
        assert _init(monkeypatch, setup, "--force", "--api", mine, found=_found()) == 0
        said = capsys.readouterr().out
        assert live_fleet() == approved, "a machine of the user's approves nothing"
        assert "is refused" in said, said
    else:
        fleet = yaml.safe_load((setup / "fleet.yaml").read_text(encoding="utf-8"))
        fleet["units"]["box_small"] = (
            {
                "address": "http://rig.invalid:8080/v1",
                "model": "small-model",
                "width": 1,
                "rig": "box",
            }
            if how == "edit"
            else {"address": ADDED[how], "model": "small-model", "width": 1}
        )
        (setup / "fleet.yaml").write_text(yaml.safe_dump(fleet), encoding="utf-8")
        policy = yaml.safe_load((setup / "policy.yaml").read_text(encoding="utf-8"))
        policy["ladder"] = ["box_small", *policy["ladder"]]
        (setup / "policy.yaml").write_text(yaml.safe_dump(policy), encoding="utf-8")

    code, err, dispatched = _run(tmp_path, setup, monkeypatch, capsys)

    assert code == Exit.REFUSED, err
    assert dispatched == []
    assert "not approved for live work yet" in err, err
    unit = {
        "reinit-hosted": "api_small-model (127.0.0.1",
        "reinit-ideo": "api_small-model (127.0.0.1",
        "edit-ideo": "box_small (127.0.0.1",
    }.get(how, "box_small")
    assert unit in err, err


def test_a_unit_on_no_rig_at_a_machine_of_the_users_is_refused_even_if_held() -> None:
    """A live folder's ``fleet.yaml`` holding such a unit approves nothing: its
    lock pins the layout, and a unit on no rig is in no layout, so the folder
    could have been edited to hold it."""
    lan = f"http://{_first_host(0xC0A80000, 16)}:8080/v1"
    unit = {"address": lan, "model": "small-model", "width": 1}
    live = {"units": {"lan_small": unit}, "fleets": {"f": {"layout": {}}}}

    assert admission.unapproved({"lan_small": unit}, live, "f") == [
        f"lan_small ({_first_host(0xC0A80000, 16)} is not a public address)"
    ]


def test_a_rerun_of_init_reapproves_its_own_fleet_in_a_new_folder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup = tmp_path / "setup"
    assert _init(monkeypatch, setup, "--api", HOSTED, found=_found()) == 0
    first = fleets_dir() / f"own@{_today()}"
    before = (first / "fleet.yaml").read_text(encoding="utf-8")

    flags = ("--force", "--api", HOSTED, "--api", OTHER)
    assert _init(monkeypatch, setup, *flags, found=_found()) == 0
    said = capsys.readouterr().out

    second = f"own@{_today()}-2"
    assert live_fleet() == second, said
    live = yaml.safe_load(
        (fleets_dir() / second / "fleet.yaml").read_text(encoding="utf-8")
    )
    assert sorted(live["units"]) == [HOSTED_UNIT, "api_other-model"]
    assert (first / "fleet.yaml").read_text(encoding="utf-8") == before
    assert admission.admit(reader=_no_read).admitted

    assert _init(monkeypatch, setup, *flags, found=_found()) == 0
    assert live_fleet() == f"own@{_today()}-3"


def test_a_second_folder_of_a_day_is_a_live_name() -> None:
    assert is_fleet_name("own@2026-10-08-2")
    assert is_fleet_name("own@2026-10-08-12")
    for bad in ("own@2026-10-08-1", "own@2026-10-08-0", "own@2026-10-08-02"):
        assert not is_fleet_name(bad), bad
    for bad in ("own@2026-10-08-", "own@2026-10-08_2", "own@2026-02-30-2"):
        assert not is_fleet_name(bad), bad


def test_a_fleet_already_live_is_never_replaced_by_init(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    live_file().parent.mkdir(parents=True)
    pointer = json.dumps({"fleet": "elsewhere@2026-01-02", "since": "then"})
    live_file().write_text(pointer, encoding="utf-8")

    assert _init(monkeypatch, tmp_path / "setup", "--api", HOSTED, found=_found()) == 0
    said = capsys.readouterr().out

    assert live_file().read_text(encoding="utf-8") == pointer
    assert not fleets_dir().exists()
    assert "elsewhere@2026-01-02 is live" in said, said


def test_an_init_that_wrote_nothing_approves_nothing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup = tmp_path / "setup"
    setup.mkdir()
    (setup / "fleet.yaml").write_text("units: {}\n", encoding="utf-8")

    assert _init(monkeypatch, setup, "--api", HOSTED, found=_found()) == 0
    capsys.readouterr()

    assert not live_file().exists()
    assert not fleets_dir().exists()
