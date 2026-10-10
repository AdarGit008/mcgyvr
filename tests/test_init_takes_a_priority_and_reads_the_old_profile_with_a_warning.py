"""`mcgyvr setup` takes a priority, and reads the old `--profile` with a warning.

What init's composed ladder optimises for is one of three things: throughput,
quality or cost. It used to be free text under `--profile`, a word the config
already uses for something else (`profile: live|dev`, which runs are allowed),
and free text the decision could only guess at.

`--priority throughput|quality|cost` is the option now. `--profile` is still
read for one release: a known word maps onto that priority, any other text is
ignored, and either way stderr says it is deprecated, what to type instead,
and that the config's `profile: live|dev` is a different setting. When both
are given, `--priority` wins.

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

    monkeypatch.setattr(cli, "initialize", fake_initialize)
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


@pytest.mark.parametrize("word", ["throughput", "Quality", " cost "])
def test_an_old_profile_naming_a_priority_maps_to_it_and_warns(
    word: str,
    tmp_path: Path,
    handed: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = _run(tmp_path, "--profile", word)
    err = capsys.readouterr().err
    want = word.strip().lower()
    assert code == 0
    assert [call["priority"] for call in handed] == [want]
    assert "deprecated" in err
    assert f"--priority {want}" in err
    assert "live|dev" in err


def test_an_old_profile_of_other_text_is_ignored_with_a_warning(
    tmp_path: Path, handed: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(tmp_path, "--profile", "fast and cheap")
    err = capsys.readouterr().err
    assert code == 0
    assert [call["priority"] for call in handed] == [None]
    assert "deprecated" in err
    assert "ignored" in err
    assert "'fast and cheap'" in err
    assert "throughput|quality|cost" in err
    assert "live|dev" in err


def test_priority_wins_over_the_old_profile_and_says_so(
    tmp_path: Path, handed: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(tmp_path, "--priority", "cost", "--profile", "quality")
    err = capsys.readouterr().err
    assert code == 0
    assert [call["priority"] for call in handed] == ["cost"]
    assert "deprecated" in err
    assert "ignored" in err


def test_a_priority_outside_the_three_is_refused(
    tmp_path: Path, handed: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exited:
        _run(tmp_path, "--priority", "speed")
    assert exited.value.code == 2
    assert not handed
