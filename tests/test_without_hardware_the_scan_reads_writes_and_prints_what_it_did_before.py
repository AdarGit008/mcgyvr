"""Without --hardware the scan reads, writes and prints what it did before.

The device list (``devices``) and the CPU detail (``cpu_detail``) are read only
when asked: ``mcgyvr scan --hardware`` on this machine, the reader's
``--hardware`` argument on a rig. Without it none of their reads is made (the
two functions that build them make every one), and the reader's stdout, the
scan document, this machine's rig file, the rig file ``scan --rig`` writes and
the one setup's promote writes hold the keys they held before, in that order.
``scan`` and ``scan --json`` print the same bytes whatever the reading
carries, and the short reading (the rig's hello) carries neither.

The machines are invented (tests.machine_shapes); a rig answers through a fake
read channel that runs the reader's entry point on an invented machine.
"""

from __future__ import annotations

import base64
import copy
import dataclasses
import json
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from tests.machine_shapes import (
    host_reader_stdout,
    host_reading,
    host_scan_document,
    host_shape,
    host_shapes,
)

NEW_KEYS = ("devices", "cpu_detail")

#: The scan document's keys, in the order the reader printed them before the
#: device list and the CPU detail.
DEFAULT_DOCUMENT_KEYS = [
    "machine",
    "host",
    "cards",
    "card_sources",
    "unsized",
    "memory",
    "cpu",
    "resources",
    "unread",
    "gpus",
    "bandwidth",
    "disk",
    "models_on_disk",
    "docker",
    "network",
    "home",
    "snapshot",
    "notes",
    "facts",
]

#: The keys ``mcgyvr scan --json`` prints by default, as it printed them before.
DEFAULT_JSON_KEYS = [
    "machine",
    "gpus",
    "memory",
    "cpu",
    "bandwidth",
    "disk",
    "models_on_disk",
    "docker",
    "network",
    "home",
    "host",
    "notes",
    "facts",
]

RIG = "box-9"


@contextmanager
def _nothing_wider() -> Iterator[None]:
    """The device list and the CPU detail refuse to be built, so a scan that
    reaches any read only they make fails."""
    from mcgyvr.serving import rigscan

    def refused(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("a read of the --hardware scan was made")

    with (
        mock.patch.object(rigscan, "_devices", refused),
        mock.patch.object(rigscan, "_cpu_detail", refused),
    ):
        yield


def _without_new(document: dict[str, Any]) -> list[str]:
    return [key for key in document if key not in NEW_KEYS]


@pytest.mark.parametrize("machine", host_shapes(), ids=lambda m: m.label)
def test_the_scan_without_hardware_makes_none_of_its_reads(machine: Any) -> None:
    with _nothing_wider():
        document = host_scan_document(machine)
    assert list(document) == DEFAULT_DOCUMENT_KEYS
    wider = host_scan_document(machine, wider=True)
    assert set(NEW_KEYS) <= set(wider)
    assert _without_new(wider) == DEFAULT_DOCUMENT_KEYS
    assert wider["cards"] == document["cards"]


@pytest.mark.parametrize("machine", host_shapes(), ids=lambda m: m.label)
def test_the_readers_stdout_without_an_argument_is_the_scan_it_printed_before(
    machine: Any,
) -> None:
    with _nothing_wider():
        code, out = host_reader_stdout(machine)
    assert code == 0
    assert list(json.loads(out)) == DEFAULT_DOCUMENT_KEYS
    code, out = host_reader_stdout(machine, "--hardware")
    assert code == 0
    printed = json.loads(out)
    assert set(NEW_KEYS) <= set(printed)
    assert _without_new(printed) == DEFAULT_DOCUMENT_KEYS


@pytest.mark.parametrize(
    "arguments", [["--hardware", "--cards"], ["--hardware", "--hardware"], ["--wide"]]
)
def test_the_reader_refuses_any_other_argument(arguments: list[str]) -> None:
    code, out = host_reader_stdout(host_shape("linux-one-card"), *arguments)
    assert (code, out) == (2, "")


def _documents(machine: Any) -> dict[bool, dict[str, Any]]:
    with _nothing_wider():
        plain = host_scan_document(machine)
    return {False: plain, True: host_scan_document(machine, wider=True)}


def _saved(folder: Path, rig: str) -> dict[str, Any]:
    saved = json.loads((folder / f"{rig}.json").read_text(encoding="utf-8"))
    assert isinstance(saved, dict)
    return saved


@pytest.mark.parametrize("hardware", [False, True], ids=["default", "hardware"])
def test_this_machines_rig_file_holds_the_wider_reading_only_with_hardware(
    hardware: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.cli import main
    from mcgyvr.serving import rigfile, rigscan

    documents = _documents(host_shape("linux-one-card"))
    asked: list[bool] = []

    def scan(*_args: Any, wider: bool = False, **_kwargs: Any) -> dict[str, Any]:
        asked.append(wider)
        return copy.deepcopy(documents[wider])

    monkeypatch.setenv("MCGYVR_RIGS", str(tmp_path))
    monkeypatch.setattr(rigscan, "scan", scan)
    assert main(["scan", *(["--hardware"] if hardware else [])]) == 0
    capsys.readouterr()
    assert asked == [hardware]
    reading = _saved(tmp_path, rigfile.LOCAL)["reading"]
    if hardware:
        assert _without_new(reading) == DEFAULT_DOCUMENT_KEYS
        assert set(NEW_KEYS) <= set(reading)
    else:
        assert list(reading) == DEFAULT_DOCUMENT_KEYS


def _rig_channel(machine: Any, sent: list[str]) -> Any:
    """A rig's read channel (``gatelib.ssh_read_only``): it admits only the
    scan read as main sends it, or with --hardware, and answers it with what
    the reader prints for `machine`."""
    from mcgyvr.serving import gatelib

    def read(
        host: str, command: str, timeout: float | None = None, **_kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        sent.append(command)
        if command == gatelib.scan_read_command():
            with _nothing_wider():
                code, out = host_reader_stdout(machine)
        elif command == gatelib.scan_read_command(hardware=True):
            code, out = host_reader_stdout(machine, "--hardware")
        else:
            raise AssertionError(f"the rig is not sent {command[-60:]!r}")
        return subprocess.CompletedProcess([command], code, out, "")

    return read


@pytest.mark.parametrize("hardware", [False, True], ids=["default", "hardware"])
def test_scan_rig_asks_and_files_the_wider_reading_only_with_hardware(
    hardware: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.cli import main
    from mcgyvr.serving import gatelib

    sent: list[str] = []
    monkeypatch.setenv("MCGYVR_RIGS", str(tmp_path))
    channel = _rig_channel(host_shape("linux-one-card"), sent)
    monkeypatch.setattr(gatelib, "ssh_read_only", channel)
    flags = ["--hardware"] if hardware else []
    assert main(["scan", "--rig", RIG, "--json", *flags]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert sent == [gatelib.scan_read_command(hardware=hardware)]
    reading = _saved(tmp_path, RIG)["reading"]
    assert printed["reading"] == reading
    if hardware:
        assert set(NEW_KEYS) <= set(reading)
        assert _without_new(reading) == DEFAULT_DOCUMENT_KEYS
    else:
        assert sent == [gatelib.scan_read_command()]
        assert list(reading) == DEFAULT_DOCUMENT_KEYS


def test_setups_promote_files_the_reading_it_filed_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.cli.commands import setup
    from mcgyvr.serving import gatelib

    sent: list[str] = []
    monkeypatch.setenv("MCGYVR_RIGS", str(tmp_path))
    monkeypatch.setattr("mcgyvr.detect.is_local_host", lambda host: False)
    channel = _rig_channel(host_shape("linux-one-card"), sent)
    monkeypatch.setattr(gatelib, "ssh_read_only", channel)
    setup._read_rig(RIG)
    assert sent == [gatelib.scan_read_command()]
    assert list(_saved(tmp_path, RIG)["reading"]) == DEFAULT_DOCUMENT_KEYS


def _windows_lines(shipped: Any) -> list[str]:
    assert isinstance(shipped.stdin, str)
    lines: list[str] = shipped.stdin.split("\n")
    return lines


def _windows_arguments(shipped: Any) -> str:
    return base64.b64decode(_windows_lines(shipped)[1]).decode("utf-8")


def test_the_scan_read_carries_the_argument_only_with_hardware() -> None:
    from mcgyvr.serving import gatelib

    plain = gatelib.scan_read_command()
    assert plain.endswith(" | base64 -d | python3 -I -B -")
    assert gatelib.scan_read_command(hardware=True) == f"{plain} --hardware"
    assert gatelib.scan_read(gatelib.LINUX).command == plain
    windows = gatelib.scan_read(gatelib.WINDOWS)
    assert _windows_arguments(windows) == ""
    wider = gatelib.scan_read(gatelib.WINDOWS, hardware=True)
    assert _windows_arguments(wider) == "--hardware"
    assert _windows_lines(wider)[0] == _windows_lines(windows)[0]
    with pytest.raises(ValueError):
        gatelib.scan_read(gatelib.LINUX, cards=True, hardware=True)


def test_the_read_channel_admits_the_hardware_read_and_nothing_wider() -> None:
    from mcgyvr.serving import gatelib

    admits = gatelib._read_only_command
    assert admits(gatelib.scan_read_command())
    assert admits(gatelib.scan_read_command(hardware=True))
    assert not admits(gatelib.scan_read_command() + " --wide")
    assert not admits(gatelib.scan_read_command() + " --hardware --hardware")
    for shipped in (
        gatelib.scan_read(gatelib.WINDOWS),
        gatelib.scan_read(gatelib.WINDOWS, hardware=True),
        # A header read of a file that happens to be named --hardware.
        gatelib.header_read(gatelib.WINDOWS, "--hardware"),
    ):
        assert admits(shipped.command, shipped.stdin)
    other = gatelib.ship(gatelib.WINDOWS, gatelib._reader_program(), ("--wide",))
    assert not admits(other.command, other.stdin)


def _printed(
    document: dict[str, Any],
    arguments: list[str],
    where: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> str:
    from mcgyvr.cli import main
    from mcgyvr.serving import rigscan

    # Each run starts from no saved rig, in the one folder its report names.
    shutil.rmtree(where, ignore_errors=True)
    monkeypatch.setenv("MCGYVR_RIGS", str(where))
    monkeypatch.setattr(rigscan, "scan", lambda *a, **k: copy.deepcopy(document))
    main(["scan", *arguments])
    return capsys.readouterr().out


def _with_cpu(label: str) -> Any:
    return dataclasses.replace(
        host_shape(label), cpu_flags=("avx", "avx2", "fma"), cpu_max_mhz=3900
    )


@pytest.mark.parametrize(
    "machine", [*host_shapes(), _with_cpu("linux-one-card")], ids=lambda m: m.label
)
@pytest.mark.parametrize("arguments", [[], ["--json"]], ids=["report", "json"])
def test_scan_prints_the_same_bytes_whether_the_reading_is_wider_or_not(
    machine: Any,
    arguments: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # One reading, printed with and without its wider keys (two readings would
    # name two temporary folders).
    document = host_scan_document(machine, wider=True)
    plain = {key: value for key, value in document.items() if key not in NEW_KEYS}
    wider = _printed(document, arguments, tmp_path, monkeypatch, capsys)
    older = _printed(plain, arguments, tmp_path, monkeypatch, capsys)
    assert wider == older
    assert "Device " not in wider and "CPU ISA" not in wider


@pytest.mark.parametrize("machine", host_shapes(), ids=lambda m: m.label)
def test_scan_json_holds_the_keys_it_held_before(
    machine: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = _documents(machine)[False]
    out = _printed(document, ["--json"], tmp_path, monkeypatch, capsys)
    assert list(json.loads(out)) == DEFAULT_JSON_KEYS


def test_scan_with_hardware_prints_every_card_and_the_cpu_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = host_scan_document(_with_cpu("linux-one-card"), wider=True)
    out = _printed(document, ["--hardware"], tmp_path / "r", monkeypatch, capsys)
    assert "  Device   nvidia:0  nvidia 0, Example Card A, " in out
    assert "PCI 0x10de:0x" in out and "(nvidia-smi)" in out
    assert "  CPU ISA  has avx avx2 fma; lacks " in out
    assert "(/proc/cpuinfo flags)" in out
    assert "  CPU MHz  3900 max (cpufreq cpuinfo_max_freq)" in out
    text = _printed(
        document, ["--json", "--hardware"], tmp_path / "j", monkeypatch, capsys
    )
    printed = json.loads(text)
    assert list(printed) == [*DEFAULT_JSON_KEYS, *NEW_KEYS]
    assert printed["devices"][0]["read_from"] == "nvidia-smi"
    assert printed["cpu_detail"]["flags"]["avx2"] is True
    assert printed["cpu_detail"]["max_mhz"] == 3900


@pytest.mark.parametrize("machine", host_shapes(), ids=lambda m: m.label)
def test_the_short_reading_carries_none_of_the_wider_reading(machine: Any) -> None:
    """The short reading is the rig's hello and the card read: not widened."""
    with _nothing_wider():
        short = host_reading(machine)
    assert not set(NEW_KEYS) & set(short)
    whole = host_scan_document(machine, wider=True)
    assert whole["cards"] == short["cards"]
    assert whole["resources"] == short["resources"]
    assert all(set(card) <= _CARD_KEYS for card in short["cards"])


#: The fields a card of the short reading holds, as before the wider reading.
_CARD_KEYS = {
    "vendor",
    "index",
    "total_mib",
    "used_mib",
    "free_mib",
    "name",
    "kind",
    "backend",
    "figure",
    "how",
    "gpu_cores",
}
