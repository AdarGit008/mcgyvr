"""Exit codes a script can branch on.

The suite already had two answers -- worked, or did not. Three of the new
outcomes are neither: a host nobody has scanned is a refusal rather than a
crash, and hardware that stopped matching its record is a successful scan with
something to say. A caller that cannot tell those apart has to read prose.

``scan --json`` is the remote transport's wire format, so its contract is here
too: stdout is the scan and nothing else, or the ssh reader has nothing to parse.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from mcgyvr import scan as scan_module
from mcgyvr.cli import main
from mcgyvr.exits import Exit

LSCPU = (
    "CPU(s):                20\nCore(s) per socket:    10\nThread(s) per core:    2\n"
)
SMI = "0, NVIDIA GeForce RTX 3060, 12288, 12, 12276\n"


#: What the `bench` fixture hands a case: a re-installer for the stubbed
#: hardware answers, called with any subset of `install`'s keyword arguments.
Bench = Callable[..., None]


@pytest.fixture
def bench(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Bench:
    def install(*, ram_kb: int = 49293144) -> None:
        monkeypatch.setattr(
            scan_module,
            "_run",
            lambda binary, *a, **k: {
                "nvidia-smi": SMI,
                "lscpu": LSCPU,
            }.get(binary),
        )
        monkeypatch.setattr(
            scan_module,
            "_read_meminfo",
            lambda: f"MemTotal:       {ram_kb} kB\nMemAvailable:   30000000 kB\n",
        )
        monkeypatch.setattr(
            scan_module,
            "measure_bandwidth",
            lambda: scan_module.Bandwidth(measured_gbps=41.2, how="copy loop"),
        )
        monkeypatch.setattr(scan_module, "_free_bytes", lambda path: 900 * 1024**3)
        monkeypatch.setattr(scan_module, "default_root", lambda: tmp_path)

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
    bench: Bench, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["scan"])
    capsys.readouterr()
    bench(ram_kb=33554432)
    main(["scan"])
    assert "mismatch" in capsys.readouterr().out.lower()


def test_emitting_for_an_unscanned_host_exits_three(
    bench: Bench, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "mcgyvr.yaml").write_text(
        "version: 1\n"
        'sources:\n  d9: {base_url: "http://desktop-9:8080", api: openai}\n'
        "ladder:\n  tiers:\n    - {name: r, source: d9, model: qwen3-coder-30b}\n",
        encoding="utf-8",
    )
    assert main(["emit", "--config", str(tmp_path / "mcgyvr.yaml")]) == Exit.REFUSED


def test_an_unknown_command_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["nonesuch"])
    assert raised.value.code == Exit.USAGE


def test_an_existing_command_keeps_its_codes(bench: Bench) -> None:
    assert main(["caps"]) in (Exit.OK, Exit.ERROR)


def test_two_models_on_one_endpoint_are_refused(
    bench: Bench, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One llama-server process serves one model, so one URL cannot hold two.

    Emitting anyway writes a compose file whose second container loses the
    race for the port -- a file that looks right and fails on the rig. The
    fix an operator needs is a second source on its own port, so the refusal
    says that rather than letting them discover it from a bind error.
    """
    main(["scan"])
    capsys.readouterr()
    scanned = next(iter(scan_module.default_root().glob("*.json")))
    host = json.loads(scanned.read_text(encoding="utf-8"))["machine"]["host"]
    config = tmp_path / "two.yaml"
    config.write_text(
        "version: 1\n"
        f'sources:\n  d1: {{base_url: "http://{host}:8080", api: openai}}\n'
        "ladder:\n  tiers:\n"
        "    - {name: fast, source: d1, model: qwen2.5-coder:3b}\n"
        "    - {name: smart, source: d1, model: qwen2.5-coder:1.5b}\n",
        encoding="utf-8",
    )
    assert (
        main(["emit", "--config", str(config), "--out", str(tmp_path)]) == Exit.REFUSED
    )
    assert "port" in capsys.readouterr().err.lower()


def test_a_loopback_source_resolves_to_the_scan_of_this_machine(
    bench: Bench, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`base_url: http://localhost:8080` names the machine that was just scanned.

    A scan is filed under what the machine calls itself (``platform.node()``);
    a source is looked up by the hostname in its URL. Those two strings almost
    never agree, so `emit` refused the one machine it did have a measurement
    for -- and `localhost` is what the stock config ships with, which made the
    command unusable for the ordinary case of a rig serving itself.
    """
    assert main(["scan"]) == Exit.OK
    capsys.readouterr()
    config = tmp_path / "loopback.yaml"
    config.write_text(
        "version: 1\n"
        'sources:\n  here: {base_url: "http://localhost:8080", api: openai}\n'
        "ladder:\n  tiers:\n"
        "    - {name: fast, source: here, model: qwen2.5-coder:3b}\n",
        encoding="utf-8",
    )
    assert main(["emit", "--config", str(config), "--out", str(tmp_path)]) == Exit.OK
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
            "version: 1\n"
            f'sources:\n  here: {{base_url: "http://{host}:8080", api: openai}}\n'
            "ladder:\n  tiers:\n"
            "    - {name: fast, source: here, model: qwen2.5-coder:3b}\n",
            encoding="utf-8",
        )
        code = main(["emit", "--config", str(config), "--out", str(tmp_path)])
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
        "version: 1\n"
        'sources:\n  d9: {base_url: "http://desktop-9:8080", api: openai}\n'
        "ladder:\n  tiers:\n"
        "    - {name: fast, source: d9, model: qwen2.5-coder:3b}\n",
        encoding="utf-8",
    )
    assert (
        main(["emit", "--config", str(config), "--out", str(tmp_path)]) == Exit.REFUSED
    )
    assert "never been scanned" in capsys.readouterr().err


def test_scan_json_exits_zero_even_when_the_hardware_drifted(
    bench: Bench, capsys: pytest.CaptureFixture[str]
) -> None:
    """A drifted rig must still deliver its measurement down the wire.

    `--json` is only ever the remote transport's format: `scan_over` -> `_ssh`
    -> `_run`, and `_run` answers None for any non-zero status, whatever was
    written to stdout. Exiting 4 there would make the exact rig exit 4 exists
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
    assert "mismatch" in captured.err.lower()


def test_a_drifted_rig_survives_the_transport_that_reads_the_json(
    bench: Bench, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same rule stated as `_run` states it, so the two cannot drift apart."""
    main(["scan"])
    capsys.readouterr()
    bench(ram_kb=33554432)
    code = main(["scan", "--json"])
    written = capsys.readouterr().out
    # What `_run` does with a status and a stdout: anything non-zero is
    # discarded and becomes `Unreachable` one frame up.
    delivered = written if code == Exit.OK else None
    assert delivered is not None
    assert scan_module.Scan.from_json(delivered).memory is not None
