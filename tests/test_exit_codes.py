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
from pathlib import Path

import pytest

from mcgyvr import scan as scan_module
from mcgyvr.cli import main
from mcgyvr.exits import Exit


@pytest.fixture
def bench(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    def install(*, ram_kb: int = 49293144) -> None:
        monkeypatch.setattr(
            scan_module,
            "_run",
            lambda binary, *a, **k: {
                "nvidia-smi": "0, NVIDIA GeForce RTX 3060, 12288, 12\n",
                "lscpu": "CPU(s):                20\nCore(s) per socket:    10\nThread(s) per core:    2\n",
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


def test_a_clean_scan_exits_zero(bench, capsys) -> None:
    assert main(["scan"]) == Exit.OK


def test_scan_json_writes_only_the_scan_to_stdout(bench, capsys) -> None:
    assert main(["scan", "--json"]) == Exit.OK
    document = json.loads(capsys.readouterr().out)
    assert document["machine"]["id"]


def test_a_mismatch_exits_four(bench, capsys) -> None:
    main(["scan"])
    capsys.readouterr()
    bench(ram_kb=33554432)
    assert main(["scan"]) == Exit.MISMATCH


def test_a_mismatch_still_wrote_the_scan(bench, capsys) -> None:
    main(["scan"])
    capsys.readouterr()
    bench(ram_kb=33554432)
    main(["scan"])
    assert "mismatch" in capsys.readouterr().out.lower()


def test_emitting_for_an_unscanned_host_exits_three(bench, tmp_path: Path, capsys) -> None:
    (tmp_path / "mcgyvr.yaml").write_text(
        "version: 1\n"
        'sources:\n  d9: {base_url: "http://desktop-9:8080", api: openai}\n'
        "ladder:\n  tiers:\n    - {name: r, source: d9, model: qwen3-coder-30b}\n",
        encoding="utf-8",
    )
    assert main(["emit", "--config", str(tmp_path / "mcgyvr.yaml")]) == Exit.REFUSED


def test_an_unknown_command_exits_two(capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["nonesuch"])
    assert raised.value.code == Exit.USAGE


def test_an_existing_command_keeps_its_codes(bench) -> None:
    assert main(["caps"]) in (Exit.OK, Exit.ERROR)
