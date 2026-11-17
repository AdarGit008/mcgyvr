"""A setup that opted in to ruff with none installed is refused before any work.

``gate.ruff: true`` is written only by setup's yes to ruff, which installs it.
A run under that key on a machine with no ruff used to be accepted with lint
and format skipped ("ruff not installed — lint skipped" is an environment
issue, not a finding) and delivered. It is refused now, before a sandbox is
opened or anything is dispatched, on the floor and on the climb (and so before
delivery's re-gate), with a line naming ruff, its install command and the
switch that runs without it.

What does not move: ``gate.ruff`` unset (every config written before setup
asked) keeps the quiet skip, ``false`` keeps its note, and ``true`` with ruff
installed runs as before.

Ruff is hidden the literal way: every ``PATH`` entry holding a ``ruff`` is
replaced by a directory of links to everything else in it, so ``git``, ``sh``
and ``python`` still resolve and only ruff does not.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from mcgyvr.config import Config, parse
from mcgyvr.contract import loads
from tests import livejournal as lj

needs_ruff = pytest.mark.skipif(
    shutil.which("ruff") is None,
    reason="the case with ruff installed needs a ruff on PATH",
)

FLEET = """\
units:
  cheap:
    address: http://127.0.0.1:9
    model: any-model
"""

#: A floor contract whose program is in process, so it needs no ruff itself
#: and only the gate's lint and format rungs would.
RENAME = """
id: rename-x
task_type: code
operation: rename_symbol
task: Rename x to y.
target: src/pkg/messy.py
rename:
  from: x
  to: y
scope:
  allow: ["src/**"]
"""


def _hide_ruff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    entries = os.environ.get("PATH", "").split(os.pathsep)
    kept: list[str] = []
    for index, entry in enumerate(entries):
        if not entry or shutil.which("ruff", path=entry) is None:
            kept.append(entry)
            continue
        shadow = tmp_path / "path" / str(index)
        shadow.mkdir(parents=True)
        for item in Path(entry).iterdir():
            if item.name not in ("ruff", "ruff.exe"):
                (shadow / item.name).symlink_to(item)
        kept.append(str(shadow))
    monkeypatch.setenv("PATH", os.pathsep.join(kept))
    assert shutil.which("ruff") is None, "ruff is still on PATH"
    assert shutil.which("git") is not None, "hiding ruff hid git too"


def _setup(ruff: bool | None, *, gate: bool | None = None) -> Config:
    policy = "ladder: [cheap]\n"
    lines = []
    if gate is not None:
        lines.append(f"  enabled: {str(gate).lower()}")
    if ruff is not None:
        lines.append(f"  ruff: {str(ruff).lower()}")
    if lines:
        policy += "gate:\n" + "\n".join(lines) + "\n"
    return parse(FLEET, policy)


def _issue(config: Config | None, target: str = "src/pkg/messy.py") -> object:
    from mcgyvr.drive import missing_gate_tool

    return missing_gate_tool(config, replace(loads(RENAME), target=target))


# --- the check ---------------------------------------------------------------


def test_an_opt_in_is_told_apart_from_a_setup_that_never_asked() -> None:
    """Unset has no value of its own and still reads as on everywhere else."""
    from mcgyvr.config import stages

    assert _setup(True).get("gate.ruff") is True
    assert _setup(False).get("gate.ruff") is False
    assert _setup(None).get("gate.ruff") is None
    assert stages(_setup(None))["repair"], "unset no longer reads as on"


def test_opted_in_with_no_ruff_names_ruff_its_install_and_the_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _hide_ruff(tmp_path, monkeypatch)

    issue = _issue(_setup(True))

    assert issue is not None, "gate.ruff true with no ruff was not refused"
    said = str(issue)
    assert "ruff is not installed" in said, said
    assert "uv tool install ruff" in said, said
    assert "already installed" in said, said
    assert "uv tool update-shell" in said, said
    assert "gate.ruff: false" in said, said


@pytest.mark.parametrize(
    "target",
    [
        "src/pkg/messy.py",
        "src/pkg/stub.pyi",
        "src/**",
        "src/pkg/*",
        "**/*.pyi",
        "src/*.p*",
        "src/pkg/mess?.py",
    ],
)
def test_a_change_that_may_hold_python_is_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    _hide_ruff(tmp_path, monkeypatch)

    assert _issue(_setup(True), target) is not None, target


@pytest.mark.parametrize(
    ("config", "target"),
    [
        (None, "src/pkg/messy.py"),
        (_setup(None), "src/pkg/messy.py"),
        (_setup(False), "src/pkg/messy.py"),
        (_setup(True, gate=False), "src/pkg/messy.py"),
        (_setup(True), "src/app.js"),
        (_setup(True), "src/**/*.ts"),
        (_setup(True), "README.md"),
        (_setup(True), "docs/*.md"),
        (_setup(True), "docs/**/*.md"),
        (_setup(True), "src/*.js"),
    ],
    ids=[
        "no-config",
        "unset",
        "opted-out",
        "gate-off",
        "javascript",
        "typescript-glob",
        "not-code",
        "markdown-glob",
        "markdown-tree",
        "javascript-glob",
    ],
)
def test_nothing_is_said_where_the_gate_would_not_run_ruff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: Config | None,
    target: str,
) -> None:
    _hide_ruff(tmp_path, monkeypatch)

    assert _issue(config, target) is None


@needs_ruff
def test_nothing_is_said_when_ruff_is_installed() -> None:
    assert _issue(_setup(True)) is None


# --- through the CLI ---------------------------------------------------------


def _run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contract_text: str,
    ruff: bool | None,
    *replies: str,
) -> tuple[int, list[str], Path, Path]:
    sent = lj.scripted(monkeypatch, *replies)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "setup", journal_dir=journal)
    if ruff is not None:
        lj.append_policy(config, f"gate:\n  ruff: {str(ruff).lower()}\n")
    contract = lj.make_contract(tmp_path / "c.yaml", contract_text)
    code = lj.main(lj.run_args(contract, repo, config))
    return code, sent, repo, journal


def _refused(
    code: int,
    sent: list[str],
    repo: Path,
    journal: Path,
    err: str,
    tmp_path: Path,
) -> None:
    assert code != 0, err
    assert "ruff is not installed" in err, err
    assert "uv tool install ruff" in err, err
    assert "uv tool update-shell" in err, err
    assert "gate.ruff: false" in err, err
    assert sent == [], "a model was dispatched"
    assert (repo / "src/pkg/messy.py").read_text(encoding="utf-8") == "x = 0\n"
    assert lj.git(repo, "rev-list", "--count", "HEAD").strip() == "1"
    assert lj.rows(journal) == [], "an attempt was journalled"
    result = json.loads(lj.result_of(tmp_path / "c.yaml").read_text("utf-8"))
    assert result["outcome"] == "error", result
    assert "uv tool install ruff" in result["detail"], result


def test_the_climb_with_no_ruff_is_refused_and_nothing_is_dispatched(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _hide_ruff(tmp_path, monkeypatch)

    code, sent, repo, journal = _run(
        tmp_path, monkeypatch, lj.MODEL_CONTRACT, True, lj.GOOD_REPLY
    )

    _refused(code, sent, repo, journal, capsys.readouterr().err, tmp_path)


def test_the_floor_with_no_ruff_is_refused_and_nothing_runs(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _hide_ruff(tmp_path, monkeypatch)

    code, sent, repo, journal = _run(tmp_path, monkeypatch, RENAME, True)

    printed = capsys.readouterr()
    assert "rename_symbol" not in printed.out, printed.out
    _refused(code, sent, repo, journal, printed.err, tmp_path)


def test_a_pattern_that_cannot_name_python_meets_the_runs_own_error(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A rename over `docs/*.md` fails on its own terms, as it always did."""
    _hide_ruff(tmp_path, monkeypatch)
    sent = lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    (repo / "docs").mkdir()
    (repo / "docs" / "guide.md").write_text("# x\n", encoding="utf-8")
    lj.git(repo, "add", "-A")
    lj.git(repo, "commit", "-q", "-m", "docs")
    config = lj.make_config(tmp_path / "setup", journal_dir=tmp_path / "journal")
    lj.append_policy(config, "gate:\n  ruff: true\n")
    markdown = RENAME.replace("target: src/pkg/messy.py", "target: docs/*.md")
    contract = lj.make_contract(
        tmp_path / "c.yaml", markdown.replace('"src/**"', '"docs/**"')
    )

    code = lj.main(lj.run_args(contract, repo, config))

    err = capsys.readouterr().err
    assert code != 0, err
    assert "ruff is not installed" not in err, err
    assert sent == [], "a model was dispatched"


@pytest.mark.parametrize("ruff", [None, False], ids=["unset", "opted-out"])
def test_without_the_opt_in_a_missing_ruff_still_runs_as_before(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    ruff: bool | None,
) -> None:
    _hide_ruff(tmp_path, monkeypatch)

    code, sent, _, _ = _run(
        tmp_path, monkeypatch, lj.MODEL_CONTRACT, ruff, lj.GOOD_REPLY
    )

    printed = capsys.readouterr()
    assert code == 0, printed
    assert len(sent) == 1, "the climb did not dispatch"
    assert "ruff is not installed" not in printed.err, printed.err
    noted = "gate.ruff is false" in printed.err
    assert noted is (ruff is False), printed.err


@needs_ruff
def test_opted_in_with_ruff_installed_runs_as_before(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, sent, _, _ = _run(
        tmp_path, monkeypatch, lj.MODEL_CONTRACT, True, lj.GOOD_REPLY
    )

    printed = capsys.readouterr()
    assert code == 0, printed
    assert len(sent) == 1, "the climb did not dispatch"
    assert "ruff is not installed" not in printed.err, printed.err


def test_a_batch_with_a_part_refused_on_ruff_is_refused_whole_before_any_part_starts(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Refused part by part, the parts ahead of it, or beside it under
    `--jobs`, would run and deliver: the batch is refused before any starts."""
    from mcgyvr.cli.commands import delegate as command

    _hide_ruff(tmp_path, monkeypatch)
    sent = lj.scripted(monkeypatch)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "setup", journal_dir=journal)
    lj.append_policy(config, "gate:\n  ruff: true\n")
    folder = tmp_path / "contracts"
    folder.mkdir()
    for cid, new in (("rename-a", "y"), ("rename-b", "z")):
        text = RENAME.replace("id: rename-x", f"id: {cid}")
        text = text.replace("to y.", f"to {new}.").replace("to: y", f"to: {new}")
        (folder / f"{cid}.yaml").write_text(text)
    started: list[str] = []

    def watched(args: object) -> int:
        started.append(str(getattr(args, "contract", "")))
        return 0

    monkeypatch.setattr(command, "_run", watched)

    code = lj.main(
        [
            "direct",
            str(folder),
            "--repo",
            str(repo),
            "--sandbox",
            "tempdir",
            "--config",
            str(config),
        ]
    )

    err = capsys.readouterr().err
    assert code == 1, err
    assert started == [], "a part of the batch started"
    assert "ruff is not installed" in err, err
    assert "uv tool install ruff" in err, err
    assert "refused whole" in err, err
    assert sent == [], "a model was dispatched"
    assert lj.git(repo, "rev-list", "--count", "HEAD").strip() == "1"
    assert not list((journal / "trees").glob("*.json")), "the tree was read"
