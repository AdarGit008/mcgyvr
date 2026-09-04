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

"Missing" is narrower than it first looked, and the tests below draw the line
where the operator does. A default location nobody named and nothing wrote to
is the supported bare install: silence. A path someone typed — ``--config``, or
``$MCGYVR_CONFIG`` — and that is not there is a typo, not an install, and
saying nothing about it hands the operator a run under a directory they never
chose. So only the implicit probe is silent.

The note is one line, and every fact on it is true of the run that printed it.
A YAML parse error is several lines long and used to spill out of its own
prefix, so the reason is flattened into the note rather than printed under it.
And what the note adds — where this run's answer is going — is read off the
result destination itself, which ``--result`` moves and which is the only thing
that lands at all on the floor, where nothing is dispatched and so nothing is
journaled. Going, not gone: the note is printed before the run, so arrival is
not yet a fact it has, and a ``--result`` that cannot be written left it
reporting a file that was never created.

That destination is stated twice when ``--record`` is also given, and the
floor's own note went on naming the recorded directory as the one that gets the
result file after ``--result`` had moved it elsewhere. One run may not print two
notes that disagree, so the second reads the same flag as the first.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from mcgyvr.config import (
    CONFIG_PATH_ENV,
    JOURNAL_DIR_DEFAULT,
    ConfigFileError,
    ConfigMissingError,
)
from mcgyvr.config import load as load_config
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

#: Not text at all: a UTF-16 byte order mark in front of otherwise fine YAML,
#: which is what an editor told to save as UTF-16 leaves behind.
NOT_UTF8 = b"\xff\xfeversion: 1\n"

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


def notes(stdout: str) -> list[str]:
    """The ``note:`` lines a run printed, in order."""
    return [line for line in stdout.splitlines() if line.startswith("note: ")]


def config_note(stdout: str, config: Path) -> str:
    """The one note this run wrote about ``config``."""
    about = [line for line in notes(stdout) if str(config) in line]
    assert len(about) == 1, stdout
    return about[0]


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
def test_no_config_anywhere_is_the_silent_case_the_floor_is_built_for(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing config is not a defect on this path, so it is not a note.

    The silence has to be earned by nobody having named a path, which is why
    this drives the default probe — no ``--config``, no ``$MCGYVR_CONFIG``, no
    ``mcgyvr.yaml`` in the working directory. This test used to point
    ``--config`` at a file that is not there and assert silence, which is the
    very case the two below say must be spoken about: it was asserting the
    defect.
    """
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    repo = misformatted(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)

    code = lj.main(floor_args(contract, repo))

    out = capsys.readouterr()
    assert code == 0, f"stdout: {out.out}\nstderr: {out.err}"
    probe = home / ".config" / "mcgyvr" / "config.yaml"
    assert not any(str(probe) in line for line in out.out.splitlines()), out.out
    assert not any("without a config" in line for line in notes(out.out)), out.out


@needs_ruff
def test_a_config_named_on_the_command_line_and_absent_is_named_too(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--config`` at a path that is not there is a typo, not a bare install."""
    repo = misformatted(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    absent = tmp_path / "nowhere" / "mcgyvr.yaml"

    code = lj.main(floor_args(contract, repo, "--config", str(absent)))

    out = capsys.readouterr()
    assert code == 0, f"stdout: {out.out}\nstderr: {out.err}"
    assert config_note(out.out, absent)


@needs_ruff
def test_a_config_named_in_the_environment_and_absent_is_named_too(
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
    assert code == 0, f"stdout: {out.out}\nstderr: {out.err}"
    assert config_note(out.out, absent)


def test_a_named_config_that_is_absent_is_not_told_to_name_one(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The remedy differs with who chose the path, so the sentence does too.

    Three situations, not two. "Run ``mcgyvr init``, or set
    ``$MCGYVR_CONFIG`` to point at an existing file" is the answer to "I have
    no config", and it is right only where neither has been done. Said to
    someone who has just set exactly that variable, it is advice to do again
    what did not work — and what they are one step from is ``init``, which
    writes to that very path. Said to someone who typed ``--config``, only a
    different path helps.

    This used to lump the last two together and answer both with "name one
    that is there", which on a fresh install with the documented
    ``export MCGYVR_CONFIG=...`` in place withholds the one command that fixes
    it.
    """
    absent = tmp_path / "nowhere" / "mcgyvr.yaml"
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigMissingError) as bare:
        load_config()
    assert "mcgyvr init" in str(bare.value)
    assert CONFIG_PATH_ENV in str(bare.value)

    monkeypatch.setenv(CONFIG_PATH_ENV, str(absent))
    with pytest.raises(ConfigMissingError) as from_env:
        load_config()
    assert "mcgyvr init" in str(from_env.value)
    assert CONFIG_PATH_ENV not in str(from_env.value)
    assert str(absent) in str(from_env.value)

    with pytest.raises(ConfigMissingError) as from_flag:
        load_config(absent)
    assert "Name one that is there" in str(from_flag.value)
    assert CONFIG_PATH_ENV not in str(from_flag.value)
    assert str(absent) in str(from_flag.value)


@needs_ruff
def test_a_config_that_is_not_text_is_named_and_not_a_traceback(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Present and undecodable is present and unusable, not an unhandled error.

    ``UnicodeDecodeError`` is a ``ValueError``, so it went past both of
    ``load``'s excepts and out of the process: no note, no ``result:`` line and
    no exit code, from the one situation this whole file exists to make
    speakable.
    """
    repo = misformatted(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    config = tmp_path / "mcgyvr.yaml"
    config.write_bytes(NOT_UTF8)

    code = lj.main(floor_args(contract, repo, "--config", str(config)))

    out = capsys.readouterr()
    assert code == 0, f"stdout: {out.out}\nstderr: {out.err}"
    assert config_note(out.out, config)
    assert lj.result_path(out.out).is_file()


def test_a_config_that_is_not_text_fails_the_loader_as_a_config_error(
    tmp_path: Path,
) -> None:
    """And it fails that way for every command that loads one, not just ``run``."""
    config = tmp_path / "mcgyvr.yaml"
    config.write_bytes(NOT_UTF8)

    with pytest.raises(ConfigFileError) as raised:
        load_config(config)
    assert not isinstance(raised.value, ConfigMissingError)
    assert str(config) in str(raised.value)


@needs_ruff
def test_the_note_names_where_this_run_actually_landed(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The note's one added fact has to be true of the run that printed it.

    It used to be the journal dir, which under ``--result`` is a directory this
    run never writes to, and which on the floor gets nothing at all — nothing
    is dispatched, so nothing is journaled. What does land is the result file,
    and where it lands is what the note names.
    """
    repo = misformatted(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(UNPARSEABLE, encoding="utf-8")
    elsewhere = tmp_path / "elsewhere" / "answer.json"

    code = lj.main(
        floor_args(contract, repo, "--config", str(config), "--result", str(elsewhere))
    )

    out = capsys.readouterr()
    assert code == 0, f"stdout: {out.out}\nstderr: {out.err}"
    assert lj.result_path(out.out) == elsewhere
    note = config_note(out.out, config)
    assert str(elsewhere) in note, note
    assert str(Path(JOURNAL_DIR_DEFAULT).expanduser()) not in note, note


@needs_ruff
def test_a_multi_line_config_error_stays_inside_its_note(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A YAML error is several lines; a note that loses its prefix is not one.

    The continuation lines carried the rest of the reason and the clause saying
    where the run went, unprefixed, reading as output from the run itself
    rather than as a remark about a file it could not use.
    """
    repo = misformatted(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(UNPARSEABLE, encoding="utf-8")

    code = lj.main(floor_args(contract, repo, "--config", str(config)))

    out = capsys.readouterr()
    assert code == 0, f"stdout: {out.out}\nstderr: {out.err}"
    spilled = [
        line
        for line in out.out.splitlines()
        if "expected the node content" in line and not line.startswith("note: ")
    ]
    assert not spilled, f"stdout: {out.out}"
    assert "expected the node content" in config_note(out.out, config)


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
def test_the_two_notes_one_run_prints_agree_about_where_the_result_went(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One run, two notes, one destination.

    The floor prints a second note when ``--record`` names a journal dir it
    will not journal to, and that note went on saying the named directory
    "gets this run's result file" after ``--result`` had moved the one file
    that is written out of it entirely. Two notes two lines apart then told the
    operator two different places, and only one of them matched the ``result:``
    line under both.
    """
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
    assert code == 0, f"stdout: {out.out}\nstderr: {out.err}"
    assert lj.result_path(out.out) == elsewhere
    about_record = [line for line in notes(out.out) if str(record) in line]
    assert len(about_record) == 1, out.out
    assert "gets this run's result file" not in about_record[0], about_record[0]
    assert str(elsewhere) in about_record[0], about_record[0]
    assert not record.exists(), sorted(record.rglob("*"))


@needs_ruff
def test_the_note_says_where_the_result_is_sent_not_that_it_arrived(
    tmp_path: Path, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The note is printed before the run, so it may not report the run's end.

    Its destination is settled by then and its arrival is not: ``--result`` at
    a path that cannot be written leaves the run exiting 1 with no file, after
    a note that had already said the result landed there. The note keeps the
    fact it actually has — where this run is sending its answer — and the
    failure is stderr's to report.
    """
    repo = misformatted(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "tidy.yaml", FORMAT)
    config = tmp_path / "mcgyvr.yaml"
    config.write_text(UNPARSEABLE, encoding="utf-8")
    blocked = tmp_path / "blocked"
    blocked.mkdir()

    code = lj.main(
        floor_args(contract, repo, "--config", str(config), "--result", str(blocked))
    )

    out = capsys.readouterr()
    assert code == 1, f"stdout: {out.out}\nstderr: {out.err}"
    assert "could not be written" in out.err, out.err
    note = config_note(out.out, config)
    assert str(blocked) in note, note
    assert "lands at" not in note, note
