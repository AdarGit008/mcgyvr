"""A config names no profile: the door settles which config a run is under, and
the default is live.

The default is prod — the live fleet folder is the unnamed fallback, another
setup is only ever reached through ``$MCGYVR_CONFIG`` or ``--config``, and
forgetting the variable lands on prod. There is one kind of run (owner,
2026-10-15: the dev side is the lab's); what a run under another setup may
serve is pinned in ``tests/test_a_staged_setup_may_serve_any_launch_spec.py``, not
here.

What must be observably true:

* a ``profile:`` key is refused by the loader, as any key the schema does not
  know is;
* the schema version does not move: a ``version`` key is refused;
* the door hands every gate and the step the config the run is under
  (``RUN_CONFIG``), settled at gate 1 before any rig is read; with no config
  at all it is ``none``;
* a config that is there and cannot be read is refused at gate 1 too: a run
  whose config cannot be read cannot say which fleet it ran under.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests import onedoor

CONFIG_VAR = "MCGYVR_CONFIG"

BASE_CONFIG = """\
units:
  only:
    address: http://localhost:8080
    model: a-model
    rig: local
ladder:
- only
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


def test_a_profile_key_is_refused() -> None:
    from mcgyvr.config import ConfigSchemaError

    for value in ("live", "dev"):
        with pytest.raises(ConfigSchemaError, match="profile"):
            _parse(f"profile: {value}\n" + BASE_CONFIG)


def test_a_version_key_is_retired() -> None:
    """A config no longer carries a version; the fleet vocabulary is the shape."""
    from mcgyvr.config import ConfigSchemaError

    with pytest.raises(ConfigSchemaError, match=r"version|fleet"):
        _parse("version: 1\n" + BASE_CONFIG)


# --- the door ------------------------------------------------------------------

CAMPAIGN = "config-probe"


def _probe(root: Path, env_file: Path) -> onedoor.Scenario:
    """A campaign step that records the config the door handed it."""
    after = f"printf 'RUN_CONFIG=%s\\n' \"${{RUN_CONFIG:-}}\" >> '{env_file}'\n"
    step = onedoor.add_step(
        root, CAMPAIGN, "1-probe.sh", onedoor.probe_step(env_file, after=after)
    )
    return onedoor.Scenario(folder=CAMPAIGN, step=str(step))


def test_the_step_is_handed_the_config_it_runs_under(tmp_path: Path) -> None:
    root = onedoor.fixture_repo(tmp_path)
    dev = _write(tmp_path, "dev.yaml", BASE_CONFIG)
    env_file = tmp_path / "env.txt"
    done = onedoor.door(root, _probe(root, env_file), env_extra={CONFIG_VAR: str(dev)})
    assert done.returncode == 0, done.stderr[-1500:]
    handed = onedoor.read_env_file(env_file)
    # A config named as one file is read from the folder it sits in.
    assert handed.get("RUN_CONFIG") == str(dev.resolve().parent), handed


def test_with_no_config_at_all_the_run_is_under_none(tmp_path: Path) -> None:
    """Forgetting the variable lands on prod: HOME holds no config, the cwd
    holds none, and nothing is named."""
    root = onedoor.fixture_repo(tmp_path)
    env_file = tmp_path / "env.txt"
    done = onedoor.door(root, _probe(root, env_file))
    assert done.returncode == 0, done.stderr[-1500:]
    handed = onedoor.read_env_file(env_file)
    assert handed.get("RUN_CONFIG") == "none", handed


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


# --- what an adversarial pass found -----------------------------------------------


def test_a_relative_config_path_is_read_where_the_operator_typed_it(
    tmp_path: Path,
) -> None:
    """The gates run with the run root as their working directory; a relative
    ``MCGYVR_CONFIG`` must still mean the file beside the shell that typed it,
    which is what ``mcgyvr`` itself would load."""
    checkout = onedoor.fixture_repo(tmp_path / "checkout")
    elsewhere = onedoor.fixture_repo(tmp_path / "elsewhere")
    _write(checkout, "dev.yaml", BASE_CONFIG)
    env_file = tmp_path / "env.txt"
    done = onedoor.door(
        checkout, _probe(elsewhere, env_file), env_extra={CONFIG_VAR: "dev.yaml"}
    )
    assert done.returncode == 0, done.stderr[-1500:]
    assert onedoor.read_env_file(env_file).get("RUN_CONFIG") == str(checkout.resolve())


def test_a_list_as_a_key_is_a_config_error_and_not_a_type_error() -> None:
    from mcgyvr.config import ConfigSchemaError

    with pytest.raises(ConfigSchemaError):
        _parse("[dev]: x\n" + BASE_CONFIG)
