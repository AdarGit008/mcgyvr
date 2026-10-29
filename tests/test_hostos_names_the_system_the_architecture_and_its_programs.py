"""hostos names the system, the architecture and a program file the same way everywhere.

Linux, macOS and Windows answer ``linux``, ``darwin`` and ``windows`` (any
other POSIX answers ``linux``), the many spellings of one architecture answer
one name, and a program file takes ``.exe`` on Windows alone.
"""

from __future__ import annotations

import platform
import sys

import pytest

from mcgyvr import hostos
from tests.hostos_fakes import PLATFORMS, as_system


@pytest.mark.parametrize("system", sorted(PLATFORMS))
def test_each_system_answers_its_own_name(
    system: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, system)
    assert hostos.os_name() == system


def test_another_posix_system_answers_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd14")
    assert hostos.os_name() == "linux"


@pytest.mark.parametrize(
    ("machine", "named"),
    [
        ("x86_64", "x86_64"),
        ("AMD64", "x86_64"),
        ("arm64", "arm64"),
        ("aarch64", "arm64"),
        ("ARM64", "arm64"),
        ("riscv64", "riscv64"),
    ],
)
def test_one_architecture_answers_one_name_however_it_is_spelled(
    machine: str, named: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(platform, "machine", lambda: machine)
    assert hostos.arch() == named


@pytest.mark.parametrize("system", ["linux", "darwin"])
def test_a_program_keeps_its_name_on_posix(
    system: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_system(monkeypatch, system)
    assert hostos.exe("llama-server") == "llama-server"


def test_a_program_takes_exe_on_windows_once(monkeypatch: pytest.MonkeyPatch) -> None:
    as_system(monkeypatch, "windows")
    assert hostos.exe("nvidia-smi") == "nvidia-smi.exe"
    assert hostos.exe("nvidia-smi.EXE") == "nvidia-smi.EXE"
