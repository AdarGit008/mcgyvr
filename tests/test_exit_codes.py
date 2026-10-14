"""Exit codes a script can branch on.

The suite already had two answers -- worked, or did not. Three of the new
outcomes are neither: a host nobody has scanned is a refusal rather than a
crash, and hardware that stopped matching its record is a successful scan with
something to say. A caller that cannot tell those apart has to read prose.

``scan --json`` prints the wire format ``mcgyvr.scan.Scan.from_json`` reads,
so its contract is here too: stdout is the scan and nothing else.

The machine is read by the one reader (:mod:`mcgyvr.serving.rigscan`), stubbed
here with an invented machine's document, and recorded as its rig file
(``$MCGYVR_RIGS/localhost.json``), the one record ``emit`` sizes from.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr import scan as scan_module
from mcgyvr.cli import main
from mcgyvr.exits import Exit

#: The invented machine's id and the name it calls itself.
MACHINE_ID = "0a1b2c3d4e5f6a7b"
HOST = "bench-host"


def _reading(ram_kb: int) -> dict[str, Any]:
    """What the one reader prints for the invented machine with ``ram_kb`` RAM."""
    return {
        "machine": {"id": MACHINE_ID, "host": HOST, "kernel": "6.8.0-invented"},
        "gpus": [
            {
                "index": 0,
                "name": "Example Card 12G",
                "vram": {
                    "total_mib": 12288,
                    "used_mib": 12,
                    "free_mib": 12276,
                    "reserved_mib": 0,
                },
            }
        ],
        "memory": {
            "total_gb": round(ram_kb / (1024.0 * 1024.0), 1),
            "available_gb": round(30000000 / (1024.0 * 1024.0), 1),
        },
        "cpu": {"cores": 10, "threads": 20},
        "bandwidth": {"measured_gbps": 41.2, "how": "copy loop"},
        "disk": {"path": "/home/user/.cache/mcgyvr/weights", "free_gb": 900.0},
        "models_on_disk": [],
        "docker": None,
        "network": {"reached_at": None, "ipv4": []},
        "snapshot": {"driver": "580.1", "kernel": "6.8.0-invented"},
        "notes": [],
        "facts": [],
    }


#: What the `bench` fixture hands a case: a re-installer for the stubbed
#: reading, called with any subset of `install`'s keyword arguments.
Bench = Callable[..., None]


@pytest.fixture
def bench(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Bench:
    from mcgyvr.serving import rigscan

    monkeypatch.setenv("MCGYVR_RIGS", str(tmp_path / "rigs"))
    monkeypatch.setattr(rigscan, "machine_id", lambda **_: MACHINE_ID)

    def install(*, ram_kb: int = 49293144) -> None:
        monkeypatch.setattr(rigscan, "scan", lambda *a, **k: _reading(ram_kb))

    install()
    return install


def test_the_codes_are_distinct() -> None:
    values = [Exit.OK, Exit.ERROR, Exit.USAGE, Exit.REFUSED, Exit.MISMATCH]
    assert [int(value) for value in values] == [0, 1, 2, 3, 4]


def test_a_clean_scan_exits_zero(
    bench: Bench, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["scan"]) == Exit.OK


def test_scan_json_writes_only_the_scan_to_stdout(
    bench: Bench, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["scan", "--json"]) == Exit.OK
    document = json.loads(capsys.readouterr().out)
    assert document["machine"]["id"]


def test_a_mismatch_exits_four(
    bench: Bench, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["scan"])
    capsys.readouterr()
    bench(ram_kb=33554432)
    assert main(["scan"]) == Exit.MISMATCH


def test_a_mismatch_still_wrote_the_scan(
    bench: Bench, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["scan"])
    capsys.readouterr()
    bench(ram_kb=33554432)
    main(["scan"])
    assert "moved since" in capsys.readouterr().out.lower()
    saved = json.loads((tmp_path / "rigs" / "localhost.json").read_text("utf-8"))
    assert saved["reading"]["memory"]["total_gb"] == 32.0


def test_emitting_for_an_unscanned_host_exits_three(
    bench: Bench, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "mcgyvr.yaml").write_text(
        """\
units:
  r:
    address: http://desktop-9:8080
    model: qwen3-coder-30b
    rig: d9
ladder:
- r
""",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "emit",
                "--ctx-per-slot",
                "4096",
                "--config",
                str(tmp_path / "mcgyvr.yaml"),
            ]
        )
        == Exit.REFUSED
    )


def test_an_unknown_command_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["nonesuch"])
    assert raised.value.code == Exit.USAGE


def test_an_existing_command_keeps_its_codes(bench: Bench) -> None:
    assert main(["caps"]) in (Exit.OK, Exit.ERROR)


def test_two_models_on_one_endpoint_are_two_launch_specs(
    bench: Bench, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One llama-server process serves one model, and one URL may still hold two.

    This exited REFUSED until 2026-09-09 — "give each model its own source on
    its own port" — and the advice was right about co-residents and wrong about
    the shape the ladder is now made of. Two rungs on one URL are two models
    *taking turns* on it, and telling an owner to invent a second port is
    telling them to buy a second card.

    One process per model has not stopped being true; it is enforced by giving
    each alternative a launch spec of its own
    (:func:`mcgyvr.serving.launch_specs`), so no file ever holds two services
    that would race for one port. The exit code moves from REFUSED to OK and
    the count of files written is what says the rule survived the change.
    """
    main(["scan"])
    capsys.readouterr()
    scanned = tmp_path / "rigs" / "localhost.json"
    host = json.loads(scanned.read_text(encoding="utf-8"))["reading"]["machine"]["host"]
    config = tmp_path / "two.yaml"
    config.write_text(
        f"""\
units:
  fast:
    address: http://{host}:8080
    model: qwen2.5-coder:3b
    rig: d1
  smart:
    address: http://{host}:8080
    model: qwen2.5-coder:1.5b
    rig: d1
ladder:
- fast
- smart
""",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "emit",
                "--ctx-per-slot",
                "4096",
                "--config",
                str(config),
                "--out",
                str(tmp_path),
            ]
        )
        == Exit.OK
    )
    capsys.readouterr()
    written = sorted(path.name for path in tmp_path.glob("compose.*.yml"))
    assert written == sorted(
        (
            f"compose.{host}.qwen2.5-coder-1.5b.yml",
            f"compose.{host}.qwen2.5-coder-3b.yml",
        )
    ), written
    # One service in each, which is the whole of "one process serves one
    # model": a file holding both would be a file whose second never binds.
    for name in written:
        document = yaml.safe_load((tmp_path / name).read_text(encoding="utf-8"))
        assert len(document["services"]) == 1, (name, document["services"])


def test_a_loopback_source_resolves_to_the_scan_of_this_machine(
    bench: Bench, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`base_url: http://localhost:8080` names the machine that was just scanned.

    A machine is known by what it calls itself (``platform.node()``) and by
    its rig name; a source is looked up by the hostname in its URL. Those
    strings almost never agree, so `emit` refused the one machine it did have a
    measurement for -- and `localhost` is what the stock config ships with,
    which made the command unusable for the ordinary case of a rig serving
    itself.
    """
    assert main(["scan"]) == Exit.OK
    capsys.readouterr()
    config = tmp_path / "loopback.yaml"
    config.write_text(
        """\
units:
  fast:
    address: http://localhost:8080
    model: qwen2.5-coder:3b
    rig: here
ladder:
- fast
""",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "emit",
                "--ctx-per-slot",
                "4096",
                "--config",
                str(config),
                "--out",
                str(tmp_path),
            ]
        )
        == Exit.OK
    )
    assert "never been scanned" not in capsys.readouterr().err


def test_a_loopback_address_resolves_the_same_way_a_name_does(
    bench: Bench, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """127.0.0.1 and ::1 are this machine as surely as the word `localhost` is."""
    assert main(["scan"]) == Exit.OK
    capsys.readouterr()
    for index, host in enumerate(("127.0.0.1", "[::1]")):
        config = tmp_path / f"addr{index}.yaml"
        config.write_text(
            f"""\
units:
  fast:
    address: http://{host}:8080
    model: qwen2.5-coder:3b
    rig: here
ladder:
- fast
""",
            encoding="utf-8",
        )
        code = main(
            [
                "emit",
                "--ctx-per-slot",
                "4096",
                "--config",
                str(config),
                "--out",
                str(tmp_path),
            ]
        )
        capsys.readouterr()
        assert code == Exit.OK, host


def test_another_machine_is_still_refused_when_this_one_is_scanned(
    bench: Bench, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Resolving `localhost` must not turn into resolving everything.

    A unit is sized from measured free VRAM, RAM and disk. Sizing one rig from
    another rig's numbers writes a compose file that looks entirely reasonable
    and cannot work, which is worse than a refusal that costs a minute.
    """
    assert main(["scan"]) == Exit.OK
    capsys.readouterr()
    config = tmp_path / "elsewhere.yaml"
    config.write_text(
        """\
units:
  fast:
    address: http://desktop-9:8080
    model: qwen2.5-coder:3b
    rig: d9
ladder:
- fast
""",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "emit",
                "--ctx-per-slot",
                "4096",
                "--config",
                str(config),
                "--out",
                str(tmp_path),
            ]
        )
        == Exit.REFUSED
    )
    assert "never been scanned" in capsys.readouterr().err


def test_scan_json_exits_zero_even_when_the_hardware_drifted(
    bench: Bench, capsys: pytest.CaptureFixture[str]
) -> None:
    """A drifted rig must still deliver its measurement down the wire.

    `--json` prints the remote transport's format, and a transport that reads a
    command's stdout discards it for any non-zero status, whatever was
    written. Exiting 4 there would make the exact rig exit 4 exists
    to report -- one that lost a DIMM or a card -- read as unreachable and drop
    out of the sweep, taking a perfectly good scan with it. The mismatch is
    reported on stderr instead, where the transport never looks.
    """
    main(["scan"])
    capsys.readouterr()
    bench(ram_kb=33554432)
    assert main(["scan", "--json"]) == Exit.OK
    captured = capsys.readouterr()
    assert json.loads(captured.out)["memory"]["total_gb"] == 32.0
    assert "moved since" in captured.err.lower()


def test_a_drifted_rig_survives_the_transport_that_reads_the_json(
    bench: Bench, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same rule stated as a transport states it, so the two cannot drift
    apart."""
    main(["scan"])
    capsys.readouterr()
    bench(ram_kb=33554432)
    code = main(["scan", "--json"])
    written = capsys.readouterr().out
    # What a transport does with a status and a stdout: anything non-zero is
    # discarded and becomes `Unreachable` one frame up.
    delivered = written if code == Exit.OK else None
    assert delivered is not None
    assert scan_module.Scan.from_json(delivered).memory is not None
