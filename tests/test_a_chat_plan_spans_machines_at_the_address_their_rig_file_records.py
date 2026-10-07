"""A chat plan spans machines named by ``--host`` at the address each rig file records.

Owner, Round 9 (2026-10-07): a chat or agent unit spans every machine over
llama.cpp RPC, and each worker listens on a private IPv4 address, never on a
name the product would resolve. "Setup's scan records each machine's private
IPv4 in its rig file" (``mcgyvr scan --rig``), so a ``--host`` given by name
spans when its rig file records an address.

Promises, over invented machines and the shipped knowledge:

* A machine whose rig file records a private address is spanned: its RPC
  worker listens on that address, and the head reaches it there.
* A machine with no address recorded (no rig file, or one that records none)
  is left out of the span, and the unit's notes say so plainly and name the
  command that records it.
* The other machines that have one are still spanned.
* The plan, sized again (:func:`mcgyvr.planner.units_of`), binds the same
  worker to the same address.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli, planner, recommend
from mcgyvr.scan import Disk, Gpu, Machine, Memory, Scan, Vram
from mcgyvr.serving import rigfile

#: Invented machines as the user's ssh names them (RFC 6761 ``.invalid``),
#: and the documentation addresses (RFC 5737) their rig files record.
HEAD, NEAR, FAR = "rig-d.invalid", "rig-e.invalid", "rig-f.invalid"
NEAR_AT, FAR_AT = "192.0.2.21", "192.0.2.22"


def _scan(host: str, free_mib: tuple[int, ...]) -> Scan:
    return Scan(
        machine=Machine(id=f"machine-{host}", host=host, kernel="0.0.0-example"),
        gpus=tuple(
            Gpu(
                index=index,
                name="Example Card Y",
                vram=Vram(
                    total_mib=free + 512, used_mib=512, free_mib=free, reserved_mib=0
                ),
            )
            for index, free in enumerate(free_mib)
        ),
        memory=Memory(total_gb=4.0, available_gb=0.0),
        disk=Disk(path=Path("/weights"), free_gb=500.0),
    )


def _record(rig: str, address: str | None) -> None:
    rigfile.write(
        rigfile.Rig(
            rig=rig,
            read_at="2026-10-07T00:00:00Z",
            hostname=f"{rig}-host",
            machine_id=f"machine-{rig}",
            private_ipv4=address,
            private_ipv4_how=(
                "the address the rig was reached at over ssh"
                if address
                else "it was not reached over ssh, and no private IPv4 is on "
                "its interfaces"
            ),
        )
    )


def _plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    scans: dict[str, Scan],
) -> dict[str, Any]:
    monkeypatch.setattr(recommend, "_scan_host", lambda host: scans[host])
    argv = ["recommend", "--use-case", "chat", "--users", "1", "--offline"]
    for host in scans:
        argv += ["--host", host]
    code = cli.main(argv)
    out = capsys.readouterr()
    assert code == 0, out.err
    plan: dict[str, Any] = json.loads(out.out)
    return plan


@pytest.fixture(autouse=True)
def _settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "settings"))


def _processes(plan: dict[str, Any], process: str) -> list[tuple[str, dict[str, Any]]]:
    return [
        (rig, unit)
        for rig, laid in plan["rigs"].items()
        for unit in laid["units"]
        if unit["process"] == process
    ]


def test_a_machine_whose_rig_file_records_an_address_is_spanned_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _record(NEAR, NEAR_AT)
    scans = {HEAD: _scan(HEAD, (7000,)), NEAR: _scan(NEAR, (7000,))}

    plan = _plan(tmp_path, monkeypatch, capsys, scans)

    ((head_rig, head),) = _processes(plan, "serve")
    ((worker_rig, worker),) = _processes(plan, "rpc")
    assert (head_rig, worker_rig) == (HEAD, NEAR)
    assert worker["args"]["-H"] == NEAR_AT
    assert head["args"]["--rpc"] == f"{NEAR_AT}:{worker['port']}"
    assert {(s["rig"], s["card"]) for s in head["shards"]} == {(HEAD, 0), (NEAR, 0)}
    assert {"rig": NEAR, "card": 0, "bind": NEAR_AT} in head["shards"]


@pytest.mark.parametrize("recorded", ["no rig file", "a rig file with no address"])
def test_a_machine_with_no_address_is_left_out_and_the_plan_says_how_to_record_it(
    recorded: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if recorded != "no rig file":
        _record(NEAR, None)
    scans = {HEAD: _scan(HEAD, (7000, 7000)), NEAR: _scan(NEAR, (7000,))}

    plan = _plan(tmp_path, monkeypatch, capsys, scans)

    ((rig, unit),) = _processes(plan, "serve")
    assert rig == HEAD
    assert unit["cards"] == [0, 1]
    assert not _processes(plan, "rpc")
    said = " ".join(unit["notes"])
    assert f"no private IPv4 is recorded for {NEAR}" in said, unit["notes"]
    assert f"`mcgyvr scan --rig {NEAR}`" in said, unit["notes"]


def test_the_machines_that_have_an_address_are_spanned_without_the_one_that_has_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _record(NEAR, NEAR_AT)
    scans = {
        HEAD: _scan(HEAD, (7000,)),
        NEAR: _scan(NEAR, (7000,)),
        FAR: _scan(FAR, (7000,)),
    }

    plan = _plan(tmp_path, monkeypatch, capsys, scans)

    ((_rig, head),) = _processes(plan, "serve")
    ((worker_rig, worker),) = _processes(plan, "rpc")
    assert worker_rig == NEAR and worker["args"]["-H"] == NEAR_AT
    assert {s["rig"] for s in head["shards"]} == {HEAD, NEAR}
    assert any(FAR in note and "mcgyvr scan --rig" in note for note in head["notes"])
    assert not any(FAR_AT in note for note in head["notes"])


def test_the_plan_sized_again_binds_the_worker_to_the_same_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _record(NEAR, NEAR_AT)
    scans = {HEAD: _scan(HEAD, (7000,)), NEAR: _scan(NEAR, (7000,))}
    plan = _plan(tmp_path, monkeypatch, capsys, scans)

    units = planner.units_of(plan, scans)

    (worker,) = [unit for unit in units if unit.host == NEAR]
    assert worker.args["-H"] == NEAR_AT
