"""`mcgyvr setup` takes a priority, and refuses the old `--profile`.

What init's composed ladder optimises for is one of three things: throughput,
quality or cost. It used to be free text under `--profile`, free text the
decision could only guess at.

`--priority throughput|quality|cost` is the option. `--profile` was deprecated
in 0.4.0 for removal in the release after next, and is gone: it is now an
unknown flag, refused before anything is handed to init.

The seam is `cli.initialize`: only the priority it is handed is checked, and
nothing is detected or written.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli
from mcgyvr.initialize import InitResult

PRIORITIES = ("throughput", "quality", "cost")


@pytest.fixture
def handed(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Stand in for init and record what it was handed."""
    calls: list[dict[str, Any]] = []

    def fake_initialize(path: Path, **kwargs: Any) -> InitResult:
        calls.append(kwargs)
        return InitResult(path=path, created=False, written=False)

    monkeypatch.setattr(cli.commands.setup, "initialize", fake_initialize)
    return calls


def _run(tmp_path: Path, *flags: str) -> int:
    return cli.main(["setup", *flags, str(tmp_path / "setup")])


@pytest.mark.parametrize("priority", PRIORITIES)
def test_each_priority_reaches_init_without_a_warning(
    priority: str,
    tmp_path: Path,
    handed: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = _run(tmp_path, "--priority", priority)
    assert code == 0
    assert [call["priority"] for call in handed] == [priority]
    assert "profile" not in handed[0]
    assert capsys.readouterr().err == ""


def test_no_priority_is_none_and_says_nothing(
    tmp_path: Path, handed: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(tmp_path) == 0
    assert [call["priority"] for call in handed] == [None]
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("flags", [("--profile", "quality"), ("--profile", "x")])
def test_the_old_profile_is_an_unknown_flag(
    flags: tuple[str, ...],
    tmp_path: Path,
    handed: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exited:
        _run(tmp_path, *flags)
    assert exited.value.code == 2
    assert not handed
    assert "--profile" in capsys.readouterr().err


def test_a_priority_outside_the_three_is_refused(
    tmp_path: Path, handed: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exited:
        _run(tmp_path, "--priority", "speed")
    assert exited.value.code == 2
    assert not handed
