"""A config someone named and that is broken stops the run, by name.

The deterministic floor runs without a config and must go on doing so: a
``format`` contract dispatches nothing, needs no ladder, and an install with no
``mcgyvr.yaml`` is a supported install. So ``mcgyvr direct`` on a bare install,
where nothing is named and nothing is found, runs the contract and says nothing
about the config it does not have.

"No config here" and "the config in front of you does not parse" are two very
different situations, and the line is drawn where the operator drew it. A path
someone typed (``--config``) or exported (``$MCGYVR_CONFIG``) is a naming: if it
is not there, does not parse, is not text or fails the schema, that is an
error, exit 1, said on stderr with the path and the reason, *before* anything
runs. Running the floor anyway would hand the operator a run under a directory
they never chose, with a note they may not read. A broken ``mcgyvr.yaml`` whose
``journal.dir`` points the journal somewhere else would silently journal under
the schema default.

Nothing is written by a refused run: no result at ``--result``, no copy at
``--record``, and the working tree is as it was.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import (
    CONFIG_PATH_ENV,
    ConfigFileError,
    ConfigMissingError,
)
from mcgyvr.config import load as load_config
from tests import livejournal as lj

FORMAT = """
id: tidy
task_type: code
operation: format
task: Reformat the module.
target: src/pkg/messy.py
scope:
  allow: ["src/**"]
"""

#: YAML that does not parse: an unclosed flow mapping.
UNPARSEABLE = "version: 1\nsources: {workstation:\n"

#: Not text at all: a UTF-16 byte order mark in front of otherwise fine YAML,
#: which is what an editor told to save as UTF-16 leaves behind.
NOT_UTF8 = b"\xff\xfeversion: 1\n"

#: YAML that parses and is not a config: ``units.local.address`` is empty.
OFF_SCHEMA = """\
units:
  local:
    address: ''
    model: qwen2.5-coder:7b
    rig: nowhere
ladder:
- local
journal:
  dir: /nowhere/configured
"""

needs_ruff = pytest.mark.skipif(
    shutil.which("ruff") is None,
    reason="the floor under test is a real ruff; there is nothing to fake here",
)


def misformatted(root: Path) -> Path:
    """A repo whose target ``ruff format`` has something to do to."""
    repo = lj.make_repo(root)
    (repo / "src" / "pkg" / "messy.py").write_text("x=0\n", encoding="utf-8")
    lj.git(repo, "commit", "-qam", "misformatted")
    return repo


def floor_args(contract: Path, repo: Path, *extra: str) -> list[str]:
    """``direct`` on the floor, with no ``--config`` unless a test passes one."""
    return [
        "direct",
        str(contract),
        "--repo",
        str(repo),
        "--sandbox",
        "tempdir",
        "--result",
        str(lj.result_of(contract)),
        *extra,
    ]


def refused(out: Any, repo: Path, contract: Path, *named: Path) -> None:
    """The run stopped before it started: exit 1 is the caller's, the rest here."""
    for path in named:
        assert str(path) in out.err, out.err
    assert out.out == "", out.out
    assert not lj.result_of(contract).exists()
    assert lj.git(repo, "status", "--porcelain").strip() == ""


@needs_ruff
def test_a_config_that_does_not_parse_stops_the_run_and_is_named(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The floor would have run; the operator is told which config it did not use."""
    repo = misformatted(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(UNPARSEABLE, encoding="utf-8")

    code = lj.main(floor_args(contract, repo, "--config", str(config)))

    out = capsys.readouterr()
    assert code == 1, f"stdout: {out.out}\nstderr: {out.err}"
    refused(out, repo, contract, config)
    assert "expected the node content" in out.err, out.err


@needs_ruff
def test_a_config_that_fails_the_schema_stops_the_run_too(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Its ``journal.dir`` is not one this run could honestly write under."""
    repo = misformatted(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(OFF_SCHEMA, encoding="utf-8")

    code = lj.main(floor_args(contract, repo, "--config", str(config)))

    out = capsys.readouterr()
    assert code == 1, f"stdout: {out.out}\nstderr: {out.err}"
    refused(out, repo, contract, config)
    assert not Path("/nowhere/configured").exists()


@needs_ruff
def test_no_config_anywhere_is_the_silent_case_the_floor_is_built_for(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing config is not a defect on this path, so it is not even a note.

    The silence has to be earned by nobody having named a path, which is why
    this drives the default probe: no ``--config``, no ``$MCGYVR_CONFIG``, no
    ``mcgyvr.yaml`` in the working directory. A ``--config`` pointed at a file
    that is not there is the case the two below say must stop the run.
    """
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    repo = misformatted(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)

    code = lj.main(floor_args(contract, repo))

    out = capsys.readouterr()
    assert code == 0, f"stdout: {out.out}\nstderr: {out.err}"
    probe = home / ".mcgyvr" / "config" / "mcgyvr.yaml"
    assert str(probe) not in out.out + out.err, out
    assert not any("without a config" in line for line in out.out.splitlines())
    assert lj.result_of(contract).is_file()


@needs_ruff
def test_a_config_named_on_the_command_line_and_absent_stops_the_run(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--config`` at a path that is not there is a typo, not a bare install."""
    repo = misformatted(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    absent = tmp_path / "nowhere" / "mcgyvr.yaml"

    code = lj.main(floor_args(contract, repo, "--config", str(absent)))

    out = capsys.readouterr()
    assert code == 1, f"stdout: {out.out}\nstderr: {out.err}"
    refused(out, repo, contract, absent)


@needs_ruff
def test_a_config_named_in_the_environment_and_absent_stops_the_run(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """And ``$MCGYVR_CONFIG`` is as much a naming as the flag is."""
    repo = misformatted(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    absent = tmp_path / "nowhere" / "mcgyvr.yaml"
    monkeypatch.setenv("MCGYVR_CONFIG", str(absent))

    code = lj.main(floor_args(contract, repo))

    out = capsys.readouterr()
    assert code == 1, f"stdout: {out.out}\nstderr: {out.err}"
    refused(out, repo, contract, absent)


def test_a_named_config_that_is_absent_is_not_told_to_name_one(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The remedy differs with who chose the path, so the sentence does too.

    Three situations, not two. "Run ``mcgyvr setup``, or set
    ``$MCGYVR_CONFIG`` to point at an existing file" is the answer to "I have
    no config", and it is right only where neither has been done. Said to
    someone who has just set exactly that variable, it is advice to do again
    what did not work — and what they are one step from is ``init``, which
    writes to that very path. Said to someone who typed ``--config``, only a
    different path helps.

    Answering both with "name one that is there" would, on a fresh install with
    the documented ``export MCGYVR_CONFIG=...`` in place, withhold the one
    command that fixes it.
    """
    absent = tmp_path / "nowhere" / "mcgyvr.yaml"
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigMissingError) as bare:
        load_config()
    assert "mcgyvr setup" in str(bare.value)
    assert CONFIG_PATH_ENV in str(bare.value)

    monkeypatch.setenv(CONFIG_PATH_ENV, str(absent))
    with pytest.raises(ConfigMissingError) as from_env:
        load_config()
    assert "mcgyvr setup" in str(from_env.value)
    assert CONFIG_PATH_ENV not in str(from_env.value)
    assert str(absent) in str(from_env.value)

    with pytest.raises(ConfigMissingError) as from_flag:
        load_config(absent)
    assert "Name one that is there" in str(from_flag.value)
    assert CONFIG_PATH_ENV not in str(from_flag.value)
    assert str(absent) in str(from_flag.value)


@needs_ruff
def test_a_config_that_is_not_text_stops_the_run_and_is_not_a_traceback(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Present and undecodable is present and unusable, not an unhandled error.

    ``UnicodeDecodeError`` is a ``ValueError`` and not an ``OSError`` or a YAML
    error, so ``load`` has to name it as a config that cannot be read.
    """
    repo = misformatted(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    config = tmp_path / "mcgyvr.yaml"
    config.write_bytes(NOT_UTF8)

    code = lj.main(floor_args(contract, repo, "--config", str(config)))

    out = capsys.readouterr()
    assert code == 1, f"stdout: {out.out}\nstderr: {out.err}"
    refused(out, repo, contract, config)
    assert "Traceback" not in out.err


def test_a_config_that_is_not_text_fails_the_loader_as_a_config_error(
    tmp_path: Path,
) -> None:
    """And it fails that way for every command that loads one, not just ``direct``."""
    config = tmp_path / "mcgyvr.yaml"
    config.write_bytes(NOT_UTF8)

    with pytest.raises(ConfigFileError) as raised:
        load_config(config)
    assert not isinstance(raised.value, ConfigMissingError)
    assert str(config) in str(raised.value)


def test_a_broken_config_is_still_fatal_where_a_ladder_is_needed(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The note is the floor's answer only: a climb without a ladder is an error."""
    sent = lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "impl.yaml")
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(UNPARSEABLE, encoding="utf-8")

    code = lj.main(lj.run_args(contract, repo, config))

    out = capsys.readouterr()
    assert code == 1, f"stdout: {out.out}\nstderr: {out.err}"
    assert str(config) in out.err, out.err
    assert sent == []


@needs_ruff
def test_a_refused_run_writes_nothing_wherever_its_result_and_record_point(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--result`` and ``--record`` are promises of a run that never started."""
    repo = misformatted(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(UNPARSEABLE, encoding="utf-8")
    record = tmp_path / "record"
    elsewhere = tmp_path / "elsewhere" / "answer.json"

    code = lj.main(
        floor_args(
            contract,
            repo,
            "--config",
            str(config),
            "--record",
            str(record),
            "--result",
            str(elsewhere),
        )
    )

    out = capsys.readouterr()
    assert code == 1, f"stdout: {out.out}\nstderr: {out.err}"
    refused(out, repo, contract, config)
    assert not elsewhere.exists()
    assert lj.rows(record) == []
    assert lj.results(record) == []
