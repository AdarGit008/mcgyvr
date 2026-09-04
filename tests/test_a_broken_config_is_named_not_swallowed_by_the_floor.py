"""A config that is there and broken is named, even where it is not needed.

The deterministic floor runs without a config and must go on doing so: a
``format`` contract dispatches nothing, needs no ladder, and an install with no
``mcgyvr.yaml`` is a supported install. So ``run`` catches
:class:`~mcgyvr.config.ConfigError`, keeps it, and only raises it on the path
that needs a ladder.

That made two very different situations identical. "No config here" and "the
config in front of you does not parse" are the same exception family, and the
floor said nothing about either. A run with a malformed ``mcgyvr.yaml`` — one
whose ``journal.dir`` points its whole journal somewhere else — went to the
schema default in silence, and the operator's only clue was a result file in a
directory they had configured away from.

Missing is still silent, because the floor is built for it. Present and
unreadable is a ``note:`` naming what is wrong, on stdout beside the floor's
other notes: nothing failed, and the run is still worth doing, but the config
the operator wrote is not the one this run used. :class:`ConfigMissingError` is
what tells the two apart, so the answer is the config module's rather than a
second guess at the file system here.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests import livejournal as lj

FORMAT = """
id: tidy
task_type: format
task: Reformat the module.
target: src/pkg/messy.py
scope:
  allow: ["src/**"]
"""

#: YAML that does not parse: an unclosed flow mapping.
UNPARSEABLE = "version: 1\nsources: {workstation:\n"

#: YAML that parses and is not a config: ``ladder.tiers`` names no source.
OFF_SCHEMA = """
version: 1
sources: {}
ladder:
  tiers:
    - name: local
      source: nowhere
      model: qwen2.5-coder:7b
journal:
  dir: /nowhere/configured
"""

needs_ruff = pytest.mark.skipif(
    shutil.which("ruff") is None,
    reason="the floor under test is a real ruff; there is nothing to fake here",
)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


def misformatted(root: Path) -> Path:
    """A repo whose target ``ruff format`` has something to do to."""
    repo = lj.make_repo(root)
    (repo / "src" / "pkg" / "messy.py").write_text("x=0\n", encoding="utf-8")
    lj.git(repo, "commit", "-qam", "misformatted")
    return repo


def floor_args(contract: Path, repo: Path, *extra: str) -> list[str]:
    """``run`` on the floor, with no ``--config`` unless a test passes one."""
    return [
        "run",
        str(contract),
        "--repo",
        str(repo),
        "--sandbox",
        "tempdir",
        *extra,
    ]


@needs_ruff
def test_a_config_that_does_not_parse_is_named_on_the_floor(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The run still happens; the operator is told which config it did not use."""
    repo = misformatted(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(UNPARSEABLE, encoding="utf-8")

    code = lj.main(floor_args(contract, repo, "--config", str(config)))

    out = capsys.readouterr()
    assert code == 0, f"stdout: {out.out}\nstderr: {out.err}"
    noted = [line for line in out.out.splitlines() if line.startswith("note: ")]
    assert any(str(config) in line for line in noted), (
        f"a config that is there and does not parse was swallowed.\n"
        f"stdout: {out.out}\nstderr: {out.err}"
    )


@needs_ruff
def test_a_config_that_fails_the_schema_is_named_too(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """And its ``journal.dir`` is visibly not the one this run wrote under.

    The defect in one line: the result lands under the schema default while the
    file the operator wrote says somewhere else, and nothing on the way there
    mentions it.
    """
    repo = misformatted(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(OFF_SCHEMA, encoding="utf-8")

    code = lj.main(floor_args(contract, repo, "--config", str(config)))

    out = capsys.readouterr()
    assert code == 0, f"stdout: {out.out}\nstderr: {out.err}"
    assert any(
        line.startswith("note: ") and str(config) in line
        for line in out.out.splitlines()
    ), f"stdout: {out.out}\nstderr: {out.err}"
    result = lj.result_path(out.out)
    assert home in result.parents, result


@needs_ruff
def test_no_config_at_all_is_the_silent_case_the_floor_is_built_for(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing config is not a defect on this path, so it is not a note."""
    repo = misformatted(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    absent = tmp_path / "nowhere" / "mcgyvr.yaml"

    code = lj.main(floor_args(contract, repo, "--config", str(absent)))

    out = capsys.readouterr()
    assert code == 0, f"stdout: {out.out}\nstderr: {out.err}"
    assert not any(str(absent) in line for line in out.out.splitlines()), out.out


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
