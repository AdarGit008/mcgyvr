"""A rig names its launcher, and a native one names the hosts it is reached on.

``launcher`` in the lending file is ``docker`` (the default, left unwritten,
so a file written before it reads the same) or ``native``; anything else is
refused by its field. A Mac or Windows machine reads no interface with
Linux's ioctl numbers (and does not import ``fcntl`` for them), so a native
rig names the hosts its tunnel is reached on itself, and ``rig share`` says
so when none is named.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr.rig import sharing, tunnel
from tests import hostos_fakes


def test_the_launcher_round_trips_and_the_default_stays_unwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "home"))
    written = sharing.save(sharing.Sharing(enabled=True, launcher="native"))
    assert json.loads(written.read_text())["launcher"] == "native"
    assert sharing.load().launcher == "native"
    sharing.save(sharing.Sharing(enabled=True))
    assert "launcher" not in json.loads(written.read_text())
    assert sharing.load().launcher == "docker"


@pytest.mark.parametrize("value", ["podman", ["native"], None, 1])
def test_a_launcher_that_is_not_one_is_refused_by_its_field(value: object) -> None:
    with pytest.raises(sharing.SharingError, match="launcher"):
        sharing.read({"launcher": value})


@pytest.mark.parametrize("system", ["darwin", "windows"])
def test_a_mac_or_windows_rig_reads_no_interface_with_linuxs_ioctl(
    system: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    hostos_fakes.as_system(monkeypatch, system)
    assert tunnel.read_interfaces() == ()


def test_a_native_share_with_no_endpoints_says_to_name_them(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr import cli

    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "home"))
    hostos_fakes.as_system(monkeypatch, "darwin")
    assert cli.main(["rig", "share", "--on", "--launcher", "native"]) == 0
    said = capsys.readouterr().out
    assert "none named: set --endpoints" in said
    assert "roles:   none offered" in said
