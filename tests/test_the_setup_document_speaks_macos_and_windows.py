"""SETUP.md says what differs on macOS and Windows, from docgen, on any host.

The platform text lives in ``docgen.render_setup`` (never in the .md), and it
names what the Mac/Windows layer ships: the data folder of each system as
``hostos`` answers it, the native launcher (``launcher: native``, the pinned
llama.cpp build, its backends and the two environment variables), the
loopback bind with the rig agent's relay, the quarantine and firewall notes,
long paths, the PowerShell PATH line setup writes, the Windows skills
installer, and the background-service notes as commands a person runs. It
renders the same bytes whichever system docgen runs on.
"""

from __future__ import annotations

import contextlib
import io
import re
from pathlib import Path

import pytest

from mcgyvr import docgen, hostos
from mcgyvr.cli.commands import setup as setup_command
from mcgyvr.config import LAUNCHER_NATIVE
from mcgyvr.serving import llamacpp, native
from mcgyvr.serving.gatelib import LOCAL_TRANSPORT_ENV
from tests.hostos_fakes import as_system

SECTION = "## macOS and Windows"


def _section() -> str:
    """The macOS and Windows section of SETUP.md, up to the next `## `."""
    text = docgen.render_setup()
    start = text.index(SECTION)
    end = text.find("\n## ", start + len(SECTION))
    return text[start : end if end != -1 else len(text)]


def _expand(shown: str, home: Path, local: Path) -> Path:
    """A folder as SETUP.md shows it, made a path under a fake home."""
    path = shown.replace("%LOCALAPPDATA%", str(local)).replace("~", str(home))
    return Path(path.replace("\\", "/"))


@pytest.mark.parametrize("system", ["linux", "darwin", "windows"])
def test_each_systems_data_and_cache_folder_is_the_one_hostos_answers(
    system: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home, local = tmp_path / "home", tmp_path / "local"
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    as_system(monkeypatch, system)
    names = {"linux": "Linux", "darwin": "macOS", "windows": "Windows"}
    data = dict(hostos.DATA_FOLDERS)[names[system]]
    cache = dict(hostos.CACHE_FOLDERS)[names[system]]

    assert _expand(data, home, local) == hostos.user_data_dir()
    assert _expand(cache, home, local) == hostos.user_cache_dir()


def test_the_setup_document_names_every_systems_data_folder() -> None:
    text = docgen.render_setup()
    for _system, shown in hostos.DATA_FOLDERS + hostos.CACHE_FOLDERS:
        assert f"`{shown}`" in text, shown


def test_the_native_launcher_is_named_as_the_layer_ships_it() -> None:
    section = _section()
    assert f"launcher: {LAUNCHER_NATIVE}" in section
    assert llamacpp.TAG in section
    assert f"{native.BIN.as_posix()}/{llamacpp.TAG}/" in section
    assert f"${native.BACKEND_ENV}" in section
    for backend in llamacpp.BACKENDS:
        assert f"`{backend}`" in section, backend
    assert f"${LOCAL_TRANSPORT_ENV}" in section
    assert "Docker" in section


def test_a_native_unit_is_loopback_only_and_reached_through_the_relay() -> None:
    section = _section()
    assert "127.0.0.1" in section
    assert "relay" in section
    # A native unit that states another host is refused; nothing here tells
    # anyone to give one.
    assert "--host" not in section
    assert "0.0.0.0" not in section


def test_firewall_quarantine_and_long_paths_are_said() -> None:
    section = _section()
    assert "firewall" in section.lower()
    assert "com.apple.quarantine" in section
    assert "LongPathsEnabled" in section


def test_background_service_notes_are_commands_not_an_install() -> None:
    section = _section()
    assert "launchctl bootstrap gui/" in section
    assert "launchctl bootout gui/" in section
    # load/unload are launchctl's legacy subcommands.
    assert not re.search(r"launchctl (un)?load\b", section)
    assert "~/Library/LaunchAgents/" in section
    assert "mcgyvr rig run" in section
    assert "mcgyvr rig join" in section
    # A rig that refuses at once is not restarted in a tight loop.
    assert "<key>ThrottleInterval</key>" in section
    assert "Startup" in section


def test_the_path_offer_names_the_powershell_line_setup_writes() -> None:
    text = docgen.render_setup()
    assert f"`{setup_command._PATH_EXPORT}`" in text
    assert f"`{setup_command._PATH_POWERSHELL}`" in text
    assert "uv tool update-shell" in text
    assert "~/.zshrc" in text


def test_the_windows_skills_installer_is_named() -> None:
    section = _section()
    assert "skills/mcgyvr/install.ps1" in section
    assert docgen.INSTALL_PS1_COMMAND in section
    # The run is let through a policy that refuses every script, never with
    # the downloaded-file check turned off.
    assert "-ExecutionPolicy RemoteSigned" in docgen.INSTALL_PS1_COMMAND
    assert "Bypass" not in section


@pytest.mark.parametrize("system", ["darwin", "windows"])
def test_the_setup_document_does_not_depend_on_the_host(
    system: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    linux = docgen.render_setup()
    as_system(monkeypatch, system)
    assert docgen.render_setup() == linux


def test_no_line_of_the_new_section_passes_the_house_width() -> None:
    for line in _section().splitlines():
        assert len(line) <= 105, line


def test_the_door_help_names_each_systems_weights_folder_and_renders() -> None:
    # argparse formats help with %, so %LOCALAPPDATA% must reach the reader
    # whole rather than fail the --help it is in.
    from mcgyvr.serving import run

    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(SystemExit) as done:
        run._serve_parse(["--help"])
    assert done.value.code == 0
    text = " ".join(out.getvalue().split())
    for _system, folder in hostos.CACHE_FOLDERS:
        assert folder in text, folder


def test_the_serving_names_docgen_states_are_the_modules_own() -> None:
    # docgen may not import serving or rig (the seam), so it states these
    # names itself; each is held here to the constant that defines it.
    from mcgyvr.rig import rungs
    from mcgyvr.serving import fetcher, gatelib, release

    assert docgen.NATIVE_TAG == llamacpp.TAG
    assert docgen.NATIVE_BACKENDS == llamacpp.BACKENDS
    assert native.BIN.as_posix() == docgen.NATIVE_BIN
    assert docgen.NATIVE_BACKEND_ENV == native.BACKEND_ENV
    assert docgen.NVIDIA_SMI_EXE == hostos.NVIDIA_SMI_EXE
    assert docgen.WEIGHTS_DIR_ENV == fetcher.WEIGHTS_DIR_ENV
    assert docgen.LOCAL_TRANSPORT_ENV == gatelib.LOCAL_TRANSPORT_ENV
    assert gatelib.SSHD[1] == docgen.SSHD_PORT
    assert docgen.QUARANTINE == release.QUARANTINE
    assert docgen.HUB_KEY_ENV == rungs.KEY_ENV
