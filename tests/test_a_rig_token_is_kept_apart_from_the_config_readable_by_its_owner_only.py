"""A rig token is kept apart from the config, readable by its owner only.

The config names a secret by the variable that holds it and never holds it.
A rig token is different: the hub shows it once, and the agent needs it after
every restart. So it is kept in a file of its own in the config folder, never
in a config: written whole or not at all, at mode 0600 whatever the umask, in
a folder created at 0700. A file anyone else could read or write, a link, a
file of another user, or one that is not what the agent wrote is refused with
what to do, never read past. What is shown of a token is its public id, never
its secret.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

TOKEN = "mhr_0123456789abcdef_" + "s" * 43
HUB = "https://hub.example.com"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "config-folder"
    monkeypatch.setenv("MCGYVR_HOME", str(folder))
    return folder


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_a_saved_token_is_its_owners_alone_and_reads_back(home: Path) -> None:
    from mcgyvr.rig import credentials

    old = os.umask(0)
    try:
        written = credentials.save(credentials.Credentials(hub=HUB, token=TOKEN))
    finally:
        os.umask(old)
    assert written == credentials.path() == home / credentials.CREDENTIALS_FILE
    assert _mode(written) == 0o600
    assert _mode(home) == 0o700
    assert credentials.load() == credentials.Credentials(hub=HUB, token=TOKEN)
    assert [p.name for p in home.iterdir()] == [credentials.CREDENTIALS_FILE]


def test_a_folder_that_exists_keeps_its_mode_and_the_file_is_still_0600(
    home: Path,
) -> None:
    from mcgyvr.rig import credentials

    home.mkdir(mode=0o755)
    os.chmod(home, 0o755)
    credentials.save(credentials.Credentials(hub=HUB, token=TOKEN))
    assert _mode(home) == 0o755
    assert _mode(credentials.path()) == 0o600


def test_saving_again_replaces_the_file_whole(home: Path) -> None:
    from mcgyvr.rig import credentials

    credentials.save(credentials.Credentials(hub=HUB, token=TOKEN))
    other = "mhr_fedcba9876543210_" + "t" * 43
    credentials.save(credentials.Credentials(hub="http://127.0.0.1:8000", token=other))
    loaded = credentials.load()
    assert loaded is not None and loaded.token == other
    assert sorted(p.name for p in home.iterdir()) == [credentials.CREDENTIALS_FILE]


def test_no_token_saved_reads_as_none(home: Path) -> None:
    from mcgyvr.rig import credentials

    assert credentials.load() is None
    assert credentials.remove() is False


def test_leaving_removes_the_file(home: Path) -> None:
    from mcgyvr.rig import credentials

    credentials.save(credentials.Credentials(hub=HUB, token=TOKEN))
    assert credentials.remove() is True
    assert not credentials.path().exists()


@pytest.mark.parametrize("mode", [0o640, 0o604, 0o620, 0o602, 0o660, 0o644])
def test_a_file_others_could_read_or_write_is_refused(home: Path, mode: int) -> None:
    from mcgyvr.rig import credentials

    credentials.save(credentials.Credentials(hub=HUB, token=TOKEN))
    os.chmod(credentials.path(), mode)
    with pytest.raises(credentials.CredentialsError) as refused:
        credentials.load()
    assert "chmod 600" in str(refused.value)
    assert TOKEN not in str(refused.value)


def test_a_link_is_refused_and_not_followed(home: Path, tmp_path: Path) -> None:
    from mcgyvr.rig import credentials

    real = tmp_path / "elsewhere.json"
    real.write_text(json.dumps({"hub": HUB, "token": TOKEN}))
    os.chmod(real, 0o600)
    home.mkdir(mode=0o700)
    credentials.path().symlink_to(real)
    with pytest.raises(credentials.CredentialsError):
        credentials.load()
    with pytest.raises(credentials.CredentialsError):
        credentials.save(credentials.Credentials(hub=HUB, token=TOKEN))
    assert json.loads(real.read_text())["token"] == TOKEN


def test_a_file_of_another_user_is_refused(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import credentials

    credentials.save(credentials.Credentials(hub=HUB, token=TOKEN))
    real_uid = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: real_uid + 1)
    with pytest.raises(credentials.CredentialsError):
        credentials.load()


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        json.dumps({"hub": HUB}),
        json.dumps({"token": TOKEN}),
        json.dumps({"hub": HUB, "token": 7}),
        json.dumps({"hub": HUB, "token": "bad token\r\nX: y"}),
        json.dumps({"hub": "", "token": TOKEN}),
        json.dumps({"hub": HUB, "token": TOKEN, "pad": "x" * 10_000}),
    ],
)
def test_a_file_that_is_not_what_the_agent_wrote_is_refused(
    home: Path, text: str
) -> None:
    from mcgyvr.rig import credentials

    home.mkdir(mode=0o700)
    fd = os.open(credentials.path(), os.O_WRONLY | os.O_CREAT, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(text)
    with pytest.raises(credentials.CredentialsError) as refused:
        credentials.load()
    assert TOKEN not in str(refused.value)


@pytest.mark.parametrize("token", ["", "a b", "x\ny", "x" * 300, "töken"])
def test_a_token_that_could_not_be_sent_is_never_saved(home: Path, token: str) -> None:
    from mcgyvr.rig import credentials

    with pytest.raises(ValueError):
        credentials.save(credentials.Credentials(hub=HUB, token=token))
    assert not credentials.path().exists()


def test_what_is_shown_of_a_token_is_its_id_never_its_secret() -> None:
    from mcgyvr.rig import credentials

    shown = credentials.shown(TOKEN)
    assert "mhr_0123456789abcdef" in shown
    assert "s" * 43 not in shown and "sss" not in shown
    odd = credentials.shown("opaque-token-of-another-shape")
    assert "opaque" not in odd and "shape" not in odd


def test_a_relative_config_folder_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcgyvr.fleet.roots import FolderError
    from mcgyvr.rig import credentials

    monkeypatch.setenv("MCGYVR_HOME", "relative/folder")
    with pytest.raises(FolderError):
        credentials.path()
