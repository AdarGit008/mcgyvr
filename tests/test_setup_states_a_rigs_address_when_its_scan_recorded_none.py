"""Setup states a rig's address when its scan recorded none.

A rig whose scan recorded no address it answers at (no ssh session, no ``ip``)
cannot be found by a unit addressed by its LAN address. The wizard asks for
that address, offering what the rig's name resolves to here, and records it in
the rig file; on the flag path ``--rig-address RIG=ADDRESS`` states it, and
nothing waits on a terminal. A rig whose scan recorded an address is not asked.

Nothing reaches a machine: detection is substituted, the rigs are invented
files, and the resolver is stubbed.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from mcgyvr import cli
from mcgyvr.cli.commands import setup
from mcgyvr.detect import Detection
from mcgyvr.scan import Scan
from mcgyvr.serving import rigfile
from tests.records import RIGS_ENV

HOSTED = "model=hosted-model,address=https://api.hosted.example/v1,api_key_env=K"
LAN = "10.0.0.7"


@pytest.fixture
def rigs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "rigs"
    folder.mkdir()
    monkeypatch.setenv(RIGS_ENV, str(folder))
    monkeypatch.setattr(
        "mcgyvr.initialize.detect",
        lambda _targets: Detection(backends=(), provenance={"backends": "none"}),
    )
    return folder


def _record(rig: str, *, reached_at: str | None = None) -> None:
    reading = json.loads(Scan.of(host=rig, vram_mib=12288).to_json())
    reading["network"] = {"reached_at": reached_at, "ipv4": []}
    rigfile.write(rigfile.from_reading(rig, reading, "2026-10-22T00:00:00Z"))


def _answers(monkeypatch: pytest.MonkeyPatch, *said: str) -> list[str]:
    """Answer the wizard's questions with `said` in turn; the questions asked."""
    asked: list[str] = []
    replies: Iterator[str] = iter(said)

    def answer(question: str) -> str:
        asked.append(question)
        return next(replies)

    monkeypatch.setattr(setup, "_ask", answer)
    return asked


def test_the_flag_states_a_rigs_address_without_a_terminal(
    rigs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _record("gpu-box")

    assert cli.main(["setup", "--rig-address", f"gpu-box={LAN}", "--api", HOSTED]) == 0

    saved = rigfile.read("gpu-box")
    assert saved is not None
    assert saved.addresses == (LAN,)
    assert (
        f"Recorded {LAN} as where gpu-box's units are reached"
        in capsys.readouterr().out
    )


def test_the_flag_makes_the_run_the_flag_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup, "_stdin_isatty", lambda: True)
    args = cli.build_parser().parse_args(["setup", "--rig-address", f"gpu-box={LAN}"])

    assert not setup._setup_is_interactive(args)


@pytest.mark.parametrize(
    ("spec", "said"),
    [
        ("gpu-box", "is not RIG=ADDRESS"),
        ("gpu-box=", "is not RIG=ADDRESS"),
        ("gpu-box=gpu-box.lan", "is not an IPv4 address"),
        (f"nowhere={LAN}", "mcgyvr scan --rig nowhere"),
    ],
)
def test_a_flag_that_states_no_address_is_refused_and_writes_nothing(
    rigs: Path, capsys: pytest.CaptureFixture[str], spec: str, said: str
) -> None:
    _record("gpu-box")

    assert cli.main(["setup", "--rig-address", spec, "--api", HOSTED]) == 1

    assert said in capsys.readouterr().err
    saved = rigfile.read("gpu-box")
    assert saved is not None
    assert saved.addresses == ()


def test_the_wizard_asks_for_a_rig_with_no_address_offering_what_its_name_resolves_to(
    rigs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record("gpu-box")
    monkeypatch.setattr(
        rigfile, "_resolve", lambda name: (LAN,) if name == "gpu-box" else ()
    )
    asked = _answers(monkeypatch, "")

    setup._ask_rig_addresses(("gpu-box",))

    assert asked == [f"Address of gpu-box [{LAN}]: "]
    saved = rigfile.read("gpu-box")
    assert saved is not None
    assert saved.addresses == (LAN,)


def test_the_wizard_asks_again_for_an_answer_that_is_not_an_address(
    rigs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record("gpu-box")
    asked = _answers(monkeypatch, "gpu-box.lan", LAN)

    setup._ask_rig_addresses(("gpu-box",))

    assert len(asked) == 2
    saved = rigfile.read("gpu-box")
    assert saved is not None
    assert saved.addresses == (LAN,)


def test_an_empty_answer_with_nothing_offered_leaves_the_rig_unrecorded(
    rigs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record("gpu-box")
    asked = _answers(monkeypatch, "")

    setup._ask_rig_addresses(("gpu-box",))

    assert asked == ["Address of gpu-box (empty to skip): "]
    saved = rigfile.read("gpu-box")
    assert saved is not None
    assert saved.addresses == ()


def test_a_rig_whose_scan_recorded_an_address_is_not_asked(
    rigs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record("gpu-box", reached_at=LAN)
    asked = _answers(monkeypatch)

    setup._ask_rig_addresses(("gpu-box",))

    assert asked == []


def test_this_machine_is_not_asked_about(
    rigs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record("localhost")
    asked = _answers(monkeypatch)

    setup._ask_rig_addresses(("localhost",))

    assert asked == []
