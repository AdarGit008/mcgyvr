"""Every command that reads the setup takes it as ``--config`` (e2e run 2, R9).

``mcgyvr run --config ~/setup`` worked, while ``mcgyvr local_pool --config
~/setup`` and ``mcgyvr config --config ~/setup`` failed with ``unrecognized
arguments: --config``: those two took the setup as a positional, ``catalog`` as
``--against``, and ``sandbox``, ``fleet alerts`` and the ``rig`` agent read it
with no way to name it at all. The owner's decision: every command that reads
the setup accepts ``--config`` with the meaning and precedence ``run`` gives it
— the setup directory (or one merged file), winning over ``$MCGYVR_CONFIG``,
the working directory and the live fleet.

The first test walks the parser itself, so a command added later is held to
this without anyone remembering to: it either takes ``--config`` or is listed
below, by name, as reading no setup, with the reason. The rest run a few of
the commands that used to refuse the flag, against a setup that is neither in
the working directory nor named by the environment.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from mcgyvr.cli import build_parser, main

#: Commands that read no setup, and why — so they take no ``--config``. A
#: command is listed by its words as typed (``fleet lock``), and only a leaf:
#: a group (``fleet``, ``rig``) runs nothing of its own.
READS_NO_CONFIG = {
    "capabilities": "the shipped estimates table, nothing configured",
    "contract": "validates a contract file on its own",
    "detect": "probes this machine and the hosts named on the line",
    "scan": "measures a machine and writes its own record",
    "recommend": "places a profile on the rigs named on the line",
    "attach": "attaches a repository; no ladder is involved",
    "index": "indexes a repository",
    "resolve": "resolves a target against a repository's index",
    "read": "reads regions of a repository",
    "fleet lock": "reads the files it is given as the required --fleet/--policy",
    "fleet promote": (
        "reads the dev setup it is given as the required --setup; the default "
        "chain could land on the live fleet, which promote never reads from"
    ),
    "fleet use": "names a promoted folder live; reads the promoted folders only",
    "fleet tag": "renames a promoted folder",
    "fleet probe": "probes the live fleet by its lock, by definition not a setup",
    "rig status": "reads the kept credentials and the agent's last state",
    "rig leave": "forgets the kept credentials",
    "rig share": "reads and writes the rig's own sharing file",
}

#: Aliases are the same command under a second name, not a second command.
_ALIASES = {"caps": "capabilities"}

FLEET = """\
units:
  cheap:
    address: http://127.0.0.1:9
    model: any-model
"""


def _leaves(
    parser: argparse.ArgumentParser, words: tuple[str, ...] = ()
) -> dict[str, argparse.ArgumentParser]:
    """Every runnable command, by its words as typed, aliases folded."""
    found: dict[str, argparse.ArgumentParser] = {}
    groups = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not groups:
        return {" ".join(words): parser}
    for group in groups:
        for name, sub in group.choices.items():
            if name in _ALIASES:
                continue
            found.update(_leaves(sub, (*words, name)))
    return found


def _takes_config(parser: argparse.ArgumentParser) -> bool:
    return any("--config" in action.option_strings for action in parser._actions)


def test_every_command_that_reads_a_config_takes_dash_dash_config() -> None:
    commands = _leaves(build_parser())

    missing = sorted(
        name
        for name, parser in commands.items()
        if name not in READS_NO_CONFIG and not _takes_config(parser)
    )

    assert not missing, (
        f"these commands take no --config: {missing}. A command that reads the "
        "setup takes it as --config, as `run` does; one that reads none is "
        "listed in READS_NO_CONFIG with the reason"
    )


def test_the_exempt_list_names_only_real_commands_that_take_no_config() -> None:
    """The list cannot rot: a renamed command, or one given --config, leaves it."""
    commands = _leaves(build_parser())

    assert set(READS_NO_CONFIG) <= set(commands), set(READS_NO_CONFIG) - set(commands)
    assert not [name for name in READS_NO_CONFIG if _takes_config(commands[name])]


def test_the_walk_sees_the_commands_that_already_took_it() -> None:
    commands = _leaves(build_parser())

    for name in ("run", "sessions", "delegate", "emit", "mcorch serve"):
        assert _takes_config(commands[name]), name


@pytest.fixture
def elsewhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A setup outside the working directory, which nothing else names."""
    setup = tmp_path / "setup"
    setup.mkdir()
    (setup / "fleet.yaml").write_text(FLEET, encoding="utf-8")
    (setup / "policy.yaml").write_text("ladder: [cheap]\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.delenv("MCGYVR_CONFIG", raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MCGYVR_HOME", str(home / ".mcgyvr"))
    return setup


@pytest.mark.parametrize("command", ["config", "local_pool"])
def test_config_and_local_pool_read_the_setup_dash_dash_config_names(
    command: str, elsewhere: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([command, "--config", str(elsewhere)]) == 0
    assert "cheap" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["config", "local_pool"])
def test_dash_dash_config_wins_over_the_environment(
    command: str,
    elsewhere: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MCGYVR_CONFIG", str(tmp_path / "nothing-here"))

    assert main([command, "--config", str(elsewhere)]) == 0
    assert "cheap" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["config", "local_pool"])
def test_the_positional_spelling_still_works(
    command: str, elsewhere: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([command, str(elsewhere)]) == 0
    assert "cheap" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["config", "local_pool"])
def test_two_different_setups_on_one_line_are_refused(
    command: str,
    elsewhere: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exited:
        main([command, str(tmp_path / "other"), "--config", str(elsewhere)])

    assert exited.value.code == 2
    assert "names two setups" in capsys.readouterr().err


def test_catalog_resolves_against_the_setup_dash_dash_config_names(
    elsewhere: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["catalog", "--against", str(elsewhere)]) == 0
    against = capsys.readouterr().out

    assert main(["catalog", "--config", str(elsewhere)]) == 0
    assert capsys.readouterr().out == against


def test_sandbox_reads_the_mode_from_the_setup_dash_dash_config_names(
    elsewhere: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (elsewhere / "policy.yaml").write_text(
        "ladder: [cheap]\nsandbox:\n  mode: tempdir\n", encoding="utf-8"
    )
    repo = tmp_path / "work"

    assert main(["sandbox", "--repo", str(repo), "--config", str(elsewhere)]) == 0
    assert "tempdir" in capsys.readouterr().out


def test_a_missing_setup_named_by_dash_dash_config_is_an_error_not_a_default(
    elsewhere: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "work"

    code = main(["sandbox", "--repo", str(repo), "--config", str(tmp_path / "no")])

    assert code == 1
    assert str(tmp_path / "no") in capsys.readouterr().err


@pytest.mark.parametrize("verb", ["join", "run"])
def test_the_rig_agent_shares_the_units_of_the_setup_dash_dash_config_names(
    verb: str,
    elsewhere: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.rig import credentials, verbs

    monkeypatch.setenv("MCGYVR_DATA", str(tmp_path / "data"))
    hub = "https://hub.example.com"
    token = "mhr_0123456789abcdef_" + "s" * 43
    if verb == "run":
        credentials.save(credentials.Credentials(hub=hub, token=token))
    handed: list[object] = []

    def agent(kept: object, config: Path | None = None) -> int:
        handed.append(config)
        return 0

    monkeypatch.setattr(verbs, "run_agent", agent)
    argv = ["rig", "join", hub, "--token", token] if verb == "join" else ["rig", "run"]

    assert main([*argv, "--config", str(elsewhere)]) == 0
    assert handed == [elsewhere]


def test_fleet_alerts_refuses_a_setup_dash_dash_config_names_that_is_not_there(
    elsewhere: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = tmp_path / "journal"
    journal.mkdir()
    missing = tmp_path / "no"

    code = main(
        ["fleet", "alerts", "--journal", str(journal), "--config", str(missing)]
    )

    assert code == 1
    assert str(missing) in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "dest"),
    [
        (["setup", "--config", "x"], "path"),
        (["setup", "x"], "path"),
        (["catalog", "--config", "x"], "against"),
        (["catalog", "--against", "x", "--config", "x"], "against"),
        (["catalog", "--against", "--config", "x"], "against"),
        (["config", "--config", "x", "x"], "path"),
    ],
)
def test_the_older_spelling_and_the_flag_land_in_one_place(
    argv: list[str], dest: str
) -> None:
    assert getattr(build_parser().parse_args(argv), dest) == "x"


@pytest.mark.parametrize(
    "argv",
    [
        ["setup", "x", "--config", "y"],
        ["catalog", "--against", "x", "--config", "y"],
        ["catalog", "--config", "y", "--against", "x"],
    ],
)
def test_two_setups_are_refused_whichever_comes_first(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exited:
        build_parser().parse_args(argv)

    assert exited.value.code == 2
    assert "names two setups" in capsys.readouterr().err
