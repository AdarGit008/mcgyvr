"""The handoff names the command that prints the unit's key, never the key.

At the end of a setup that started servers, and of every door `serve up`, the
endpoint, key and model of the unit served first are written to
``provider.env`` and printed. The key stays in that file (and in the unit's own
key file): the screen names ``mcgyvr fleet key <unit>``, with ``--config`` when
the bare command would read another setup, and that command, run through the
real parser, prints the key ``provider.env`` holds. A unit that asks no key keeps
the line it always had. A key ``mcgyvr fleet key`` would refuse to print (the
unit states ``expose: local`` and a key file is left at its address) is said
to be not printed, and no command that refuses is named.
"""

from __future__ import annotations

import json
import re
import shlex
import stat
import sys
from pathlib import Path

import pytest
import yaml

from mcgyvr import handoff, unitkey
from mcgyvr.cli import main
from mcgyvr.cli.commands import setup
from mcgyvr.config import CONFIG_PATH_ENV
from mcgyvr.exits import Exit
from mcgyvr.fleet.roots import DATA_ENV, fleets_dir, live_file
from tests import onedoor
from tests.doors import CONFIG_VAR, UNITS, compose_file, dev_config

#: A host that is another machine, so a unit there is `expose: lan` by its address.
HOST = "gpu-box.example"
PORT = 8080
UNIT = "coder"
#: An invented key of the shape `unitkey` makes.
A_KEY = "k" * 43
#: The api-key line that names a command: the command, then the file named as before.
HINT = re.compile(
    r"api-key:  `(?P<command>.+)` prints it {8}\(also exported in (?P<file>.+)\)"
)
#: The api-key line of a unit that asks no key, as it was before this change.
NO_KEY = "api-key:  (none — the unit asks for no key)        (also exported in {})"


def _setup_dir(folder: Path, *, expose: str | None = None) -> Path:
    unit: dict[str, object] = {"address": f"http://{HOST}:{PORT}", "model": "m/1"}
    if expose is not None:
        unit["expose"] = expose
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "fleet.yaml").write_text(
        yaml.safe_dump({"units": {UNIT: unit}}), encoding="utf-8"
    )
    (folder / "policy.yaml").write_text(
        yaml.safe_dump({"ladder": [UNIT]}), encoding="utf-8"
    )
    return folder


def _api_key_line(out: str) -> str:
    (line,) = [line for line in out.splitlines() if line.startswith("api-key:")]
    return line


def _exported_key(provider_env: Path) -> str:
    (line,) = [
        line
        for line in provider_env.read_text(encoding="utf-8").splitlines()
        if line.startswith(f"export {handoff.API_KEY_ENV}=")
    ]
    return shlex.split(line)[1].partition("=")[2]


def _run(command: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    """The printed command, through the product's own parser and handler."""
    argv = shlex.split(command)
    assert argv[:3] == ["mcgyvr", "fleet", "key"], command
    code = main(argv[1:])
    return code, capsys.readouterr().out


# --- the line itself ------------------------------------------------------------


@pytest.mark.parametrize("command", [None, "mcgyvr fleet key coder"])
def test_a_unit_that_asks_no_key_keeps_the_line_it_had(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], command: str | None
) -> None:
    provider = handoff.Provider(endpoint="http://box1:8080/v1", api_key=None, model="m")
    exported = tmp_path / "provider.env"
    handoff.print_provider(provider, exported, command)

    assert capsys.readouterr().out.splitlines()[1] == NO_KEY.format(exported)


def test_a_key_no_command_prints_is_said_to_be_not_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    provider = handoff.Provider(
        endpoint="http://box1:8080/v1", api_key=A_KEY, model="m"
    )
    exported = tmp_path / "provider.env"
    handoff.print_provider(provider, exported)

    out, err = capsys.readouterr()
    assert A_KEY not in out + err
    assert out.splitlines()[1] == (
        f"api-key:  (not printed here)        (also exported in {exported})"
    )


# --- setup's handoff --------------------------------------------------------------


def test_setup_names_fleet_key_with_its_config_and_that_command_prints_the_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    staged = _setup_dir(tmp_path / "staged")
    unitkey.ensure(HOST, PORT)
    key = unitkey.load(HOST, PORT)
    assert key is not None

    setup._handoff(staged)

    out, err = capsys.readouterr()
    assert key not in out + err
    line = _api_key_line(out)
    hint = HINT.fullmatch(line)
    assert hint is not None, line
    assert hint["command"] == f"mcgyvr fleet key {UNIT} --config {staged}"
    provider_env = staged / handoff.PROVIDER_FILENAME
    assert hint["file"] == str(provider_env)

    code, printed = _run(hint["command"], capsys)
    assert code == Exit.OK
    assert printed == f"{key}\n"
    assert _exported_key(provider_env) == key, "provider.env still holds the key"
    if sys.platform != "win32":
        assert stat.S_IMODE(provider_env.stat().st_mode) == 0o600


def test_setup_that_is_the_live_fleet_names_the_bare_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    live = _setup_dir(fleets_dir() / "flt@2026-11-18")
    live_file().parent.mkdir(parents=True, exist_ok=True)
    live_file().write_text(json.dumps({"fleet": live.name}), encoding="utf-8")
    unitkey.ensure(HOST, PORT)
    key = unitkey.load(HOST, PORT)

    setup._handoff(live)

    hint = HINT.fullmatch(_api_key_line(capsys.readouterr().out))
    assert hint is not None
    assert hint["command"] == f"mcgyvr fleet key {UNIT}"
    assert _run(hint["command"], capsys) == (Exit.OK, f"{key}\n")


def test_a_setup_mcgyvr_config_names_is_still_passed_to_the_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    staged = _setup_dir(tmp_path / "named")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(staged))
    unitkey.ensure(HOST, PORT)

    setup._handoff(staged)

    hint = HINT.fullmatch(_api_key_line(capsys.readouterr().out))
    assert hint is not None
    assert hint["command"] == f"mcgyvr fleet key {UNIT} --config {staged}"
    monkeypatch.delenv(CONFIG_PATH_ENV)
    assert _run(hint["command"], capsys) == (Exit.OK, f"{unitkey.load(HOST, PORT)}\n")


def test_a_key_fleet_key_refuses_names_no_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A unit that states `expose: local` with a key file left from when it was
    # `lan`: provider.env exports that key as before, and `fleet key` refuses
    # the unit, so the screen names no command.
    staged = _setup_dir(tmp_path / "staged", expose="local")
    unitkey.ensure(HOST, PORT)
    key = unitkey.load(HOST, PORT)
    assert key is not None

    setup._handoff(staged)

    out, err = capsys.readouterr()
    assert key not in out + err
    assert "fleet key" not in out
    provider_env = staged / handoff.PROVIDER_FILENAME
    assert _api_key_line(out) == (
        f"api-key:  (not printed here)        (also exported in {provider_env})"
    )
    assert _exported_key(provider_env) == key
    refused = main(["fleet", "key", UNIT, "--config", str(staged)])
    assert refused == Exit.REFUSED, "the command the line leaves out refuses"


# --- the door's serve up ----------------------------------------------------------

DOOR_HOST = "box1"
DOOR_PORT = 8001


def _keyed_compose(root: Path) -> Path:
    """One service on DOOR_PORT whose env_file is its key file, as emit writes it."""
    path = compose_file(root, ("mcgyvr-box1-a-8001",))
    text = yaml.safe_load(path.read_text(encoding="utf-8"))
    text["services"]["svc0"]["env_file"] = [str(unitkey.path(DOOR_HOST, DOOR_PORT))]
    path.write_text(yaml.safe_dump(text), encoding="utf-8")
    return path


def _keyed_door(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, expose: str | None = None
) -> tuple[Path, str, Path, str, str]:
    root = onedoor.fixture_repo(tmp_path)
    # The door's data folder is `<root>/data`; the key is made there, where the
    # step and `fleet key` both read it.
    monkeypatch.setenv(DATA_ENV, str(root / "data"))
    unitkey.ensure(DOOR_HOST, DOOR_PORT)
    key = unitkey.load(DOOR_HOST, DOOR_PORT)
    assert key is not None
    compose = _keyed_compose(root)
    onedoor.serving(onedoor.stubs_dir(root), ("mcgyvr-box1-a-8001",))
    dev = dev_config(tmp_path / "dev.yaml")
    if expose is not None:
        stated = yaml.safe_load(dev.read_text(encoding="utf-8"))
        stated["units"]["only"]["expose"] = expose
        dev.write_text(yaml.safe_dump(stated), encoding="utf-8")
    result = onedoor.serve_door(root, "up", compose, env_extra={CONFIG_VAR: str(dev)})
    assert result.returncode == 0, (result.stdout, result.stderr)
    return root, key, dev, result.stdout, result.stderr


def test_serve_up_names_fleet_key_and_that_command_prints_the_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, key, dev, out, err = _keyed_door(tmp_path, monkeypatch)

    assert key not in out + err
    hint = HINT.fullmatch(_api_key_line(out))
    assert hint is not None, out
    # The dev config's unit `only` answers at http://box1:8001.
    assert hint["command"] == f"mcgyvr fleet key only --config {dev}"
    provider_env = root / "data" / handoff.PROVIDER_FILENAME
    assert hint["file"] == str(provider_env)

    assert _run(hint["command"], capsys) == (Exit.OK, f"{key}\n")
    assert _exported_key(provider_env) == key


def test_serve_up_of_a_key_fleet_key_refuses_names_no_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The config the run is under states `expose: local` on the unit, and the
    # service still names a key file: `fleet key` refuses the unit.
    root, key, dev, out, err = _keyed_door(tmp_path, monkeypatch, expose="local")

    assert key not in out + err
    assert "fleet key" not in out
    provider_env = root / "data" / handoff.PROVIDER_FILENAME
    assert _api_key_line(out) == (
        f"api-key:  (not printed here)        (also exported in {provider_env})"
    )
    assert _exported_key(provider_env) == key
    refused = main(["fleet", "key", "only", "--config", str(dev)])
    assert refused == Exit.REFUSED, "the command the line leaves out refuses"


def test_serve_up_of_a_unit_that_asks_no_key_keeps_the_line_it_had(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    compose = compose_file(root)
    dev = dev_config(tmp_path / "dev.yaml")
    onedoor.serving(onedoor.stubs_dir(root), UNITS)
    result = onedoor.serve_door(root, "up", compose, env_extra={CONFIG_VAR: str(dev)})

    assert result.returncode == 0, (result.stdout, result.stderr)
    provider_env = root / "data" / handoff.PROVIDER_FILENAME
    assert _api_key_line(result.stdout) == NO_KEY.format(provider_env)
