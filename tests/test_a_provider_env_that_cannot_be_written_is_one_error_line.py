"""A ``provider.env`` that cannot be written privately is one error line.

``handoff.write`` refuses to write through a link in the file's place. Both
of its callers reach it after the servers came up, so the refusal is one
``error:`` line on stderr that says they are up, never a traceback, and the
link's target is left as it was. Setup fails the run (exit 1, as its other
errors do); ``serve up`` keeps its exit 0, since its 1 means a unit is not
serving and setup and wake read it that way.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from mcgyvr import handoff
from mcgyvr.cli.commands.setup import run_menu_setup
from mcgyvr.config import Config
from mcgyvr.fleet.roots import data_home
from tests import onedoor
from tests import setup_door as sd
from tests.doors import CONFIG_VAR, UNITS, compose_file, dev_config

USE_CASE = "Use case — [m] mcgyvr-code, [k] code, [c] chat, [a] agent: "
KEPT = "kept as it was\n"
POSIX_LINK = pytest.mark.skipif(
    sys.platform == "win32", reason="a link needs POSIX here"
)


def _staged() -> Path:
    (staged,) = (data_home() / "setup").iterdir()
    return staged


def _errors(stderr: str) -> list[str]:
    return [line for line in stderr.splitlines() if "error:" in line]


# --- setup, through the menu ----------------------------------------------------


@POSIX_LINK
def test_setup_with_a_link_at_provider_env_is_exit_1_and_one_error_line(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    sd.interactive(monkeypatch, sd.FakeRig(), {}, typed={USE_CASE: "m"})
    target = tmp_path / "elsewhere"
    target.write_text(KEPT, encoding="utf-8")
    real = handoff.from_config

    def planted(config: Config) -> handoff.Provider | None:
        # The staged folder exists once the config is written; the link goes
        # in just before the handoff writes there.
        (_staged() / handoff.PROVIDER_FILENAME).symlink_to(target)
        return real(config)

    monkeypatch.setattr(handoff, "from_config", planted)

    assert run_menu_setup(auto=True, stop=None) == 1

    err = capsys.readouterr().err
    assert "Traceback" not in err
    (line,) = _errors(err)
    assert line.startswith(
        "error: the servers are up, but provider.env was not written:"
    ), line
    assert "is a link" in line
    link = _staged() / handoff.PROVIDER_FILENAME
    assert link.is_symlink()
    assert target.read_text(encoding="utf-8") == KEPT


def test_setup_with_no_fault_writes_provider_env_and_prints_no_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sd.interactive(monkeypatch, sd.FakeRig(), {}, typed={USE_CASE: "m"})

    assert run_menu_setup(auto=True, stop=None) == 0

    out, err = capsys.readouterr()
    assert _errors(err) == []
    written = _staged() / handoff.PROVIDER_FILENAME
    assert not written.is_symlink()
    assert f"endpoint: http://{sd.RIG}:8080/v1" in out.splitlines()


# --- the door's serve up ----------------------------------------------------------


def _serve_up(
    tmp_path: Path, before: Callable[[Path], None] = lambda root: None
) -> tuple[Path, subprocess.CompletedProcess[str]]:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    dev = dev_config(tmp_path / "dev.yaml")
    onedoor.serving(onedoor.stubs_dir(root), UNITS)
    before(root)
    return root, onedoor.serve_door(
        root, "up", compose, env_extra={CONFIG_VAR: str(dev)}
    )


@POSIX_LINK
def test_serve_up_with_a_link_at_provider_env_is_exit_0_and_one_error_line(
    tmp_path: Path,
) -> None:
    target = tmp_path / "elsewhere"
    target.write_text(KEPT, encoding="utf-8")

    def plant(root: Path) -> None:
        # The door's data folder is `MCGYVR_DATA`, `<root>/data` in the fixture.
        (root / "data").mkdir(parents=True, exist_ok=True)
        (root / "data" / handoff.PROVIDER_FILENAME).symlink_to(target)

    root, result = _serve_up(tmp_path, plant)
    data = root / "data"
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "Traceback" not in result.stdout + result.stderr
    (line,) = _errors(result.stderr)
    assert line.startswith(
        "serve-up: error: the units are up, but provider.env was not written:"
    ), line
    assert "is a link" in line
    assert "endpoint:" not in result.stdout
    assert (data / handoff.PROVIDER_FILENAME).is_symlink()
    assert target.read_text(encoding="utf-8") == KEPT


def test_serve_up_with_no_fault_writes_provider_env_and_prints_no_error(
    tmp_path: Path,
) -> None:
    root, result = _serve_up(tmp_path)

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert _errors(result.stderr) == []
    written = root / "data" / handoff.PROVIDER_FILENAME
    assert not written.is_symlink()
    lines = written.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "export MCGYVR_ENDPOINT=http://box1:8001/v1"
    assert lines[2] == "export MCGYVR_MODEL=stub-model"
    assert "endpoint: http://box1:8001/v1" in result.stdout.splitlines()
