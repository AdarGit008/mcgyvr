"""``mcgyvr direct FILE --config X`` hands X to the door its waker starts.

The door is its own process and reads its setup from ``MCGYVR_CONFIG``, else
from the live fleet. A run under a setup named with ``--config`` wakes a card
whose port refused a draw through that door, so the door is handed the same
setup, by an absolute path, also where ``MCGYVR_CONFIG`` names another. The
draw is sent from a worker thread of the run's capacity, so what holds for the
run's thread has to hold there too. Without ``--config`` the door's
environment is the process's own, as it always was: no ``env`` is passed.

Every host, model and number here is invented.
"""

from __future__ import annotations

import json
import tempfile
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import CONFIG_PATH_ENV
from tests import livejournal as lj
from tests.doors import compose_dir, config_file

#: A sleeping card's answer: nothing listens on its port.
REFUSED = (
    "could not reach http://box2:8001/v1/chat/completions within 120s: "
    "[Errno 111] Connection refused"
)


def refused_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """A backend whose port is shut for the first draw and answers after."""
    from mcgyvr.runner import RefusedConnectionError

    asked: list[str] = []

    def generate(model: str, request: Any) -> Any:
        asked.append(model)
        if len(asked) == 1:
            raise RefusedConnectionError(REFUSED)
        return lj.completion(lj.GOOD_REPLY, request)

    lj.patch_backend(monkeypatch, generate)


def doors(monkeypatch: pytest.MonkeyPatch) -> list[tuple[dict[str, Any], bool]]:
    """The door, recorded with the kwargs it was spawned with and whether it was
    spawned on the main thread."""
    import mcgyvr.wake as wake

    log: list[tuple[dict[str, Any], bool]] = []

    def spawn(argv: Sequence[str], **kwargs: Any) -> int:
        log.append((kwargs, threading.current_thread() is threading.main_thread()))
        return 0

    monkeypatch.setattr(wake, "spawn_door", spawn)
    return log


def a_setup(where: Path, specs: Path) -> Path:
    """A setup with sleep and wake on, its launch specs in `specs`."""
    where.mkdir(parents=True, exist_ok=True)
    return config_file(where / "c.yaml", journal=where / "j", specs=specs, switch=True)


def direct(tmp_path: Path, *config: str) -> tuple[int, dict[str, Any]]:
    """One ``mcgyvr direct`` of a fresh contract, and the result it wrote."""
    repo = lj.make_repo(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "impl.yaml")
    named = ["--config", *config] if config else []
    code = lj.main(
        [
            "direct",
            str(contract),
            "--repo",
            str(repo),
            "--sandbox",
            "tempdir",
            *named,
            "--result",
            str(lj.result_of(contract)),
        ]
    )
    return code, json.loads(lj.result_of(contract).read_text(encoding="utf-8"))


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A HOME, a session and a capacity rendezvous directory nobody else writes to."""
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    (tmp_path / "rendezvous").mkdir(exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "rendezvous"))
    return tmp_path / "home"


def test_the_waker_door_reads_the_config_named_not_the_one_in_the_env(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    specs = compose_dir(tmp_path, with_spec=True)
    named = a_setup(tmp_path / "named", specs)
    other = a_setup(tmp_path / "other", specs)
    monkeypatch.setenv(CONFIG_PATH_ENV, str(other))
    monkeypatch.chdir(tmp_path)
    refused_once(monkeypatch)
    log = doors(monkeypatch)

    code, result = direct(tmp_path, "named/c.yaml")
    capsys.readouterr()

    assert code == 0, result
    assert result["outcome"] == "accepted", result
    assert len(log) == 1, f"expected one wake through the door, saw {log}"
    ((kwargs, on_main),) = log
    assert not on_main, (
        "the draw was sent from the main thread: this test no longer shows "
        "the setup reaching a worker thread of the capacity"
    )
    env = kwargs.get("env")
    assert env is not None, (
        f"the waker's door was left to read {CONFIG_PATH_ENV}, which names "
        "another setup"
    )
    handed = env[CONFIG_PATH_ENV]
    assert Path(handed).is_absolute(), handed
    assert Path(handed) == named.absolute(), handed
    assert env["HOME"] == str(home), "the door lost the rest of the environment"


def test_without_a_config_the_waker_door_keeps_the_process_env(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    specs = compose_dir(tmp_path, with_spec=True)
    monkeypatch.setenv(CONFIG_PATH_ENV, str(a_setup(tmp_path / "env", specs)))
    refused_once(monkeypatch)
    log = doors(monkeypatch)

    code, result = direct(tmp_path)
    capsys.readouterr()

    assert code == 0, result
    assert len(log) == 1, f"expected one wake through the door, saw {log}"
    ((kwargs, _),) = log
    assert "env" not in kwargs, (
        f"a run with no --config changed the door's env: {kwargs}"
    )


def test_the_scope_ends_with_the_run(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr import wake

    specs = compose_dir(tmp_path, with_spec=True)
    named = a_setup(tmp_path / "named", specs)
    refused_once(monkeypatch)
    doors(monkeypatch)

    code, result = direct(tmp_path, str(named))
    capsys.readouterr()

    assert code == 0, result
    assert wake._door_env() == {}, "the named setup outlived the run"
