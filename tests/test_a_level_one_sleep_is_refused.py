"""Level 1 is a decision the fleet measured twice and never wrote down as code.

vLLM's level-2 sleep drops the weights and frees the card. Level 1 is meant to
be the fast one — park the weights in host RAM, wake instantly. On this fleet it
does something else. Measured 2026-09-09 and again in the campaign, identically:
the 3B never gives back 3.14 GiB and the 7B never gives back 10.32, **13.46 GiB
of host RAM surrendered for the life of the process**. A later level-2 sleep
does not release it; only a container restart does. It is bounded rather than a
leak — a second cycle costs nothing more — and it buys nothing at all, because
level 1 frees the same card as level 2 (within 14-26 MiB) while being 4-12x
slower to sleep and to wake.

Until now there was nowhere to put the ban: nothing in `src/` issued a sleep at
any level, and the only caller was the bench harness. This is that place. It is
the one function through which a sleep level may be spelled, so a fleet-shape
controller written later cannot route around it.
"""

from __future__ import annotations

import subprocess

import pytest

from mcgyvr.serving import servelib
from mcgyvr.serving.servelib import SleepLevelError


class FakeSsh:
    """Records what was dialled, and answers with a fixed result."""

    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.calls: list[tuple[str, str]] = []
        self.returncode = returncode
        self.stdout = stdout

    def __call__(
        self, host: str, command: str, timeout: float = 30
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((host, command))
        return subprocess.CompletedProcess(
            args=["ssh"], returncode=self.returncode, stdout=self.stdout, stderr=""
        )


def test_a_level_two_sleep_is_issued_against_the_units_own_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The safe level, and the only one this fleet has a use for."""
    dialled = FakeSsh()
    monkeypatch.setattr(servelib, "ssh", dialled, raising=True)

    assert servelib.sleep("srv2", 8002, level=2) is True
    assert len(dialled.calls) == 1
    host, command = dialled.calls[0]
    assert host == "srv2"
    assert "8002" in command, command
    assert "/sleep" in command and "level=2" in command, command


def test_a_level_one_sleep_is_refused_and_nothing_is_dialled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refused *before* the transport, because the cost is paid by the request
    arriving, not by it succeeding. A ban that dialled first and refused the
    answer would have surrendered the RAM already."""
    dialled = FakeSsh()
    monkeypatch.setattr(servelib, "ssh", dialled, raising=True)

    with pytest.raises(SleepLevelError):
        servelib.sleep("srv2", 8002, level=1)
    assert dialled.calls == [], "the refusal must not reach the rig"


def test_the_refusal_says_what_it_costs_and_what_to_use_instead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator who reads only the error must not have to find the campaign
    to know why. It carries the measured number, the fact that level 2 does not
    recover it, and the level to use instead."""
    monkeypatch.setattr(servelib, "ssh", FakeSsh(), raising=True)

    with pytest.raises(SleepLevelError) as caught:
        servelib.sleep("srv2", 8001, level=1)
    said = str(caught.value)
    assert "13.46" in said, said
    assert "level 2" in said, said
    assert "restart" in said, "only a container restart recovers it"


def test_a_level_nobody_measured_is_refused_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two levels exist and one of them is banned, which leaves exactly one. A
    third number is not a conservative default, it is an unmeasured call to a
    live rig."""
    dialled = FakeSsh()
    monkeypatch.setattr(servelib, "ssh", dialled, raising=True)

    for level in (0, 3, -1):
        with pytest.raises(SleepLevelError):
            servelib.sleep("srv2", 8002, level=level)
    assert dialled.calls == []


def test_a_sleep_that_does_not_land_is_false_and_not_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rig that cannot be reached has not been asked to do anything wrong.
    The policy failure and the transport failure are different answers, the
    way `sleeping` already keeps `None` apart from `False`."""
    monkeypatch.setattr(servelib, "ssh", FakeSsh(returncode=7), raising=True)
    assert servelib.sleep("srv2", 8002, level=2) is False
