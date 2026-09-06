"""A config says whether it is the live setup or a development one, and the
default is live.

Dev and prod are one tree on two hosts today: the same config shape, no word
in it saying which is which, and a run that cannot say what it was. The owner's
rulings (2026-09-06): the default is prod — ``~/.mcgyvr/config/mcgyvr.yaml`` is
the unnamed fallback, a ``dev.yaml`` is only ever reached through
``$MCGYVR_CONFIG``, and forgetting the variable must land on prod. And live
outranks dev, always: a run made under a dev config does not start or stop the
live ladder.

What must be observably true:

* a ``profile:`` key is read from the config, ``live`` or ``dev``, and a file
  that says nothing is ``live`` — the safe value is the one you get for free;
* a value that is neither is refused by the loader naming both;
* the schema version does not move: a version-1 file without the key still
  loads, and a version-1 file with it is still version 1;
* ``mcgyvr init`` writes the key at the schema's default, so the file says
  what it is rather than leaving the reader to know the default;
* the door hands every gate and the step the profile the config declares
  (``RUN_PROFILE``), settled at gate 1 before any rig is read; with no config
  at all it is ``live``;
* a ``serve up``/``serve down`` under a dev profile is refused at gate 1, with
  no rig read and nothing written, naming the profile and the rule;
* a config that is there and cannot be read is refused at gate 1 too: a run
  whose config cannot be read cannot say which profile it ran under.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests import onedoor
from tests.red_port.conftest import required

CONFIG_VAR = "MCGYVR_CONFIG"

BASE_CONFIG = """\
version: 1
sources:
  local:
    base_url: "http://localhost:8080"
    api: openai
    max_parallel: 1
ladder:
  tiers:
    - name: only
      source: local
      model: "a-model"
sandbox:
  mode: tempdir
"""


def _parse(text: str) -> Any:
    from mcgyvr.config import parse

    return parse(text)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --- the schema ----------------------------------------------------------------


def test_a_config_that_says_nothing_is_live() -> None:
    config = _parse(BASE_CONFIG)
    assert config.get("profile") == "live", config.data


def test_dev_is_read_and_a_third_value_is_refused_naming_both() -> None:
    from mcgyvr.config import ConfigSchemaError

    assert _parse("profile: dev\n" + BASE_CONFIG).get("profile") == "dev"
    with pytest.raises(ConfigSchemaError) as refused:
        _parse("profile: prod\n" + BASE_CONFIG)
    said = str(refused.value)
    assert "live" in said and "dev" in said, said


def test_the_schema_version_does_not_move_for_a_key_with_a_default() -> None:
    """A version-1 file without the key reads under version 1, and so does one
    with it: a new optional key is readable by the existing version."""
    from mcgyvr.config import SCHEMA_VERSION

    assert SCHEMA_VERSION == 1
    assert _parse(BASE_CONFIG).get("version") == 1
    assert _parse("profile: live\n" + BASE_CONFIG).get("version") == 1


def test_init_writes_the_profile_at_the_schemas_default() -> None:
    from mcgyvr import config
    from mcgyvr.detect import Detection
    from mcgyvr.initialize import build
    from mcgyvr.propose import Proposal

    spec = next((f for f in config.SCHEMA if f.name == "profile"), None)
    assert spec is not None, "profile is not a key of the schema"
    assert spec.default == "live"
    written = required(
        "write the profile into a fresh config so the file says what it is",
        lambda: build(Detection(), Proposal())["profile"],
    )
    assert written == spec.default


# --- the door ------------------------------------------------------------------

CAMPAIGN = "profile-probe"


def _probe(root: Path, env_file: Path) -> onedoor.Scenario:
    """A campaign step that records the profile the door handed it."""
    after = f"printf 'RUN_PROFILE=%s\\n' \"${{RUN_PROFILE:-}}\" >> '{env_file}'\n"
    step = onedoor.add_step(
        root, CAMPAIGN, "1-probe.sh", onedoor.probe_step(env_file, after=after)
    )
    return onedoor.Scenario(campaign=CAMPAIGN, step=str(step))


def test_the_step_is_handed_the_profile_the_config_declares(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    dev = _write(tmp_path, "dev.yaml", "profile: dev\n" + BASE_CONFIG)
    env_file = tmp_path / "env.txt"
    done = onedoor.door(root, _probe(root, env_file), env_extra={CONFIG_VAR: str(dev)})
    assert done.returncode == 0, done.stderr[-1500:]
    handed = onedoor.read_env_file(env_file)
    assert handed.get("RUN_PROFILE") == "dev", handed


def test_with_no_config_at_all_the_run_is_live(tmp_path: Path) -> None:
    """Forgetting the variable lands on prod: HOME holds no config, the cwd
    holds none, and nothing is named."""
    root = onedoor.fixture_repo(tmp_path)
    env_file = tmp_path / "env.txt"
    done = onedoor.door(root, _probe(root, env_file))
    assert done.returncode == 0, done.stderr[-1500:]
    handed = onedoor.read_env_file(env_file)
    assert handed.get("RUN_PROFILE") == "live", handed


def test_a_dev_profile_does_not_touch_the_live_ladder(tmp_path: Path) -> None:
    """``serve up`` under a dev config: refused at gate 1, no rig read."""
    from tests.test_the_door_serves_a_ladder_and_leaves_it_up import compose_file

    root = onedoor.fixture_repo(tmp_path)
    dev = _write(tmp_path, "dev.yaml", "profile: dev\n" + BASE_CONFIG)
    result = onedoor.serve_door(
        root, "up", compose_file(root), env_extra={CONFIG_VAR: str(dev)}
    )
    assert result.returncode == 2, (result.stdout, result.stderr[-1500:])
    assert "dev" in result.stderr and "live" in result.stderr, result.stderr
    assert onedoor.ssh_log(root) == [], "a rig was read before the refusal"
    assert onedoor.written_under_records(root) == [], "a refused run wrote"


def test_a_config_that_cannot_be_read_is_refused_before_any_rig(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    broken = _write(tmp_path, "broken.yaml", "version: [1\n")
    done = onedoor.door(
        root, _probe(root, tmp_path / "env.txt"), env_extra={CONFIG_VAR: str(broken)}
    )
    assert done.returncode == 2, (done.returncode, done.stderr[-1500:])
    assert str(broken) in done.stderr, done.stderr
    assert onedoor.ssh_log(root) == [], "a rig was read before the refusal"
    assert onedoor.written_under_records(root) == []
