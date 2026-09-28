"""mcgyvr is packaged as a skill for Claude CLI and pi, at ``skills/mcgyvr/``.

The contract is the Agent Skills standard both harnesses implement: a
``SKILL.md`` with valid frontmatter, an install script that places it into
``~/.claude/skills`` and ``~/.pi/agent/skills``, a safe first-install default,
and an onboarding path wired to the existing ``mcgyvr`` CLI.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / "skills" / "mcgyvr"
SKILL_MD = SKILL_DIR / "SKILL.md"
INSTALL_SH = SKILL_DIR / "install.sh"

# The two supported harnesses, relative to a user's HOME. Hermes and Codex are
# out of scope this session; nothing about them is asserted.
CLAUDE_SKILL = Path(".claude") / "skills" / "mcgyvr" / "SKILL.md"
PI_SKILL = Path(".pi") / "agent" / "skills" / "mcgyvr" / "SKILL.md"


def _frontmatter(path: Path) -> dict[str, object]:
    """The YAML frontmatter of a SKILL.md, which must open the file."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "frontmatter must open the file"
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    assert end is not None, "frontmatter must be closed by a second ---"
    doc = yaml.safe_load("\n".join(lines[1:end]))
    assert isinstance(doc, dict), "frontmatter must be a YAML mapping"
    return doc


def _body(path: Path) -> str:
    return path.read_text(encoding="utf-8").split("---", 2)[2]


def _run_install(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    assert INSTALL_SH.exists(), "skills/mcgyvr/install.sh must exist"
    return subprocess.run(
        ["bash", str(INSTALL_SH), *args],
        cwd=SKILL_DIR,
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
        timeout=60,
    )


# --- the skill artifact ---------------------------------------------------


def test_skill_markdown_exists() -> None:
    assert SKILL_MD.exists(), "skills/mcgyvr/SKILL.md must exist"


def test_skill_directory_matches_the_name() -> None:
    # Claude CLI requires the skill name to match its parent directory; the
    # shared SKILL.md must satisfy the stricter of the two harnesses.
    assert SKILL_DIR.is_dir(), "skills/mcgyvr/ must exist"
    assert SKILL_DIR.name == "mcgyvr"


def test_frontmatter_names_the_skill() -> None:
    assert SKILL_MD.exists(), "skills/mcgyvr/SKILL.md must exist"
    frontmatter = _frontmatter(SKILL_MD)
    assert frontmatter.get("name") == "mcgyvr"
    name = str(frontmatter["name"])
    assert 1 <= len(name) <= 64
    assert name == name.lower()


def test_description_is_present_and_bounded() -> None:
    assert SKILL_MD.exists(), "skills/mcgyvr/SKILL.md must exist"
    description = _frontmatter(SKILL_MD).get("description")
    assert isinstance(description, str) and description.strip()
    assert len(description) <= 1024


def test_first_install_does_not_auto_invoke() -> None:
    # The safe default: an agent that silently offloads work on day one is a bad
    # first impression. The skill must be explicitly invocable, not auto-loaded.
    assert SKILL_MD.exists(), "skills/mcgyvr/SKILL.md must exist"
    assert _frontmatter(SKILL_MD).get("disable-model-invocation") is True


def test_skill_positions_the_agent_as_orchestrator() -> None:
    # The doctrine: the agent stays the orchestrator; mcgyvr owns everything
    # below the task contract. Asserted as the two words that define the split.
    assert SKILL_MD.exists(), "skills/mcgyvr/SKILL.md must exist"
    described = str(_frontmatter(SKILL_MD).get("description", ""))
    text = (_body(SKILL_MD) + " " + described).lower()
    assert "orchestrat" in text
    assert "offload" in text


# --- install into both harnesses ------------------------------------------


def test_install_script_is_present_and_executable() -> None:
    assert INSTALL_SH.exists(), "skills/mcgyvr/install.sh must exist"
    assert INSTALL_SH.stat().st_mode & 0o111, "install.sh must be executable"


def test_install_places_the_skill_in_both_harnesses(tmp_path: Path) -> None:
    assert SKILL_MD.exists(), "skills/mcgyvr/SKILL.md must exist"
    home = tmp_path / "home"
    home.mkdir()

    result = _run_install(home)

    assert result.returncode == 0, result.stderr
    for target in (CLAUDE_SKILL, PI_SKILL):
        landed = home / target
        assert landed.exists(), f"expected {target} under HOME"
        assert landed.read_bytes() == SKILL_MD.read_bytes()


def test_install_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    assert _run_install(home).returncode == 0

    before = {p: (home / p).read_bytes() for p in (CLAUDE_SKILL, PI_SKILL)}
    again = _run_install(home)

    assert again.returncode == 0, again.stderr
    after = {p: (home / p).read_bytes() for p in (CLAUDE_SKILL, PI_SKILL)}
    assert before == after


def test_install_reports_what_it_did(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    result = _run_install(home)

    assert result.returncode == 0, result.stderr
    report = result.stdout.lower()
    assert report.strip(), "install must report what it did"
    assert "claude" in report
    assert "pi" in report


def test_uninstall_removes_both_and_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    assert _run_install(home).returncode == 0

    first = _run_install(home, "--uninstall")
    assert first.returncode == 0, first.stderr
    for target in (CLAUDE_SKILL, PI_SKILL):
        assert not (home / target).exists()

    second = _run_install(home, "--uninstall")
    assert second.returncode == 0, "uninstalling twice must not be an error"


# --- the onboarding path the skill documents and relies on ----------------


def test_skill_body_no_longer_documents_first_run_onboarding() -> None:
    # An agent authoring a contract does not read `mcgyvr init` or
    # `mcgyvr pool` here — that onboarding path is SETUP.md, beside the skill
    # it is not part of.
    assert SKILL_MD.exists(), "skills/mcgyvr/SKILL.md must exist"
    body = _body(SKILL_MD)
    assert "mcgyvr init" not in body
    assert "mcgyvr pool" not in body


def test_skill_body_no_longer_documents_the_levers() -> None:
    """Sources, ladder and budgets are config levers a machine's owner reads
    about in SETUP.md; the skill an agent reads to author a contract does not
    name them as levers.

    Matched as lever *usage* — the bulleted `` - `lever` — ... `` form a setup
    step introduces a lever with — and not as a raw substring, as the sibling
    check in ``tests/test_setup_leaves_the_skill.py`` does. A raw
    `"ladder" not in body` is unsatisfiable rather than strict: the outcome
    literal `ladder_spent` must be present in the body
    (``tests/test_the_skill_does_not_explain_the_ladder.py`` keeps it on its
    closed exception list).
    """
    assert SKILL_MD.exists(), "skills/mcgyvr/SKILL.md must exist"
    body = _body(SKILL_MD)
    for lever in ("ladder", "sources", "budgets"):
        assert not re.search(rf"^- `{lever}` ", body, re.MULTILINE), lever


def test_cli_exposes_the_onboarding_verbs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The skill's instructions must target verbs that actually exist.
    from mcgyvr.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    for verb in ("init", "pool", "config", "detect", "capabilities", "catalog"):
        assert verb in help_text


# --- the CLI the skill drives ---------------------------------------------


def _install_constant(name: str) -> str:
    """A constant read out of install.sh, so these tests cannot drift from it.

    The script is the single place the command and the floor are written; a
    literal copied into this file would be a second one, going stale the day
    mcgyvr reaches PyPI and ``CLI_INSTALL`` becomes ``uv tool install mcgyvr``.
    """
    text = INSTALL_SH.read_text(encoding="utf-8")
    match = re.search(rf'^{name}="(.*)"$', text, re.MULTILINE)
    assert match is not None, f"install.sh must define {name}"
    return match.group(1)


def _may_hold_mcgyvr(directory: str) -> bool:
    """Whether ``directory`` might hold an ``mcgyvr`` — unknown counts as yes.

    A PATH entry this user cannot stat is a real case, not a hypothetical:
    ``/root/.local/bin`` is on PATH on the development machine and raises
    ``PermissionError``. It cannot be proved free of an ``mcgyvr``, and a test
    about the binary being absent must not leave a directory on PATH that
    might still supply one.
    """
    try:
        return (Path(directory) / "mcgyvr").exists()
    except OSError:
        return True


def _path_without_mcgyvr() -> str:
    """The ambient PATH with every directory holding an ``mcgyvr`` removed.

    This suite runs inside the project's own venv, which has a real ``mcgyvr``
    on PATH — so a test about the binary being absent has to take it off, and
    a test about a stand-in has to be sure the stand-in is the one found.
    """
    kept = [
        d
        for d in os.environ.get("PATH", "").split(os.pathsep)
        if d and not _may_hold_mcgyvr(d)
    ]
    return os.pathsep.join(kept)


def _shim(bin_dir: Path, script: str) -> str:
    """Write an ``mcgyvr`` stand-in and return a PATH that finds it first."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "mcgyvr"
    shim.write_text(script, encoding="utf-8")
    shim.chmod(0o755)
    return f"{bin_dir}{os.pathsep}{_path_without_mcgyvr()}"


def _reporting(bin_dir: Path, reported: str) -> str:
    """A stand-in reporting ``reported`` the way the real CLI does: the
    ``mcgyvr <version>`` line first, then the config it resolved."""
    return _shim(
        bin_dir,
        f'#!/usr/bin/env bash\necho "mcgyvr {reported}"\necho "config: none"\n',
    )


def _run_install_with_path(
    home: Path, path: str, *args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(INSTALL_SH), *args],
        cwd=SKILL_DIR,
        env={**os.environ, "HOME": str(home), "PATH": path},
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_install_stdout_says_how_to_get_the_cli(tmp_path: Path) -> None:
    """The one line naming how to obtain the binary the skill drives.

    Setup instructions stay out of SKILL.md (ruled), and a skill that is
    instructions for driving a CLI is useless on a machine with no CLI. This
    is the one line on stdout that closes that, and it is exactly one line.
    """
    home = tmp_path / "home"
    home.mkdir()

    result = _run_install(home)

    assert result.returncode == 0, result.stderr
    command = _install_constant("CLI_INSTALL")
    assert command.startswith("uv tool install "), command
    cli_lines = [ln for ln in result.stdout.splitlines() if ln.startswith("cli: ")]
    assert cli_lines == [f"cli: {command}"], result.stdout


def test_no_mcgyvr_on_path_warns_and_still_installs(tmp_path: Path) -> None:
    """The ordinary first case, and the one refusing would strand.

    Somebody installing the skill is usually installing it in order to get
    started, so "no binary yet" is not a broken machine. The skill lands and
    the script says what is missing; it never fails.
    """
    home = tmp_path / "home"
    home.mkdir()

    result = _run_install_with_path(home, _path_without_mcgyvr())

    assert result.returncode == 0, result.stderr
    for target in (CLAUDE_SKILL, PI_SKILL):
        assert (home / target).exists(), f"warning must not stop install: {target}"
    assert "no mcgyvr on PATH" in result.stderr, result.stderr
    assert _install_constant("CLI_INSTALL") in result.stderr, result.stderr


def test_an_older_mcgyvr_warns_and_still_installs(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = _reporting(tmp_path / "bin", "0.0.9")

    result = _run_install_with_path(home, path)

    assert result.returncode == 0, result.stderr
    assert (home / CLAUDE_SKILL).exists(), "a warning must not stop the install"
    assert "0.0.9" in result.stderr, result.stderr
    assert _install_constant("MIN_VERSION") in result.stderr, result.stderr


def test_an_uninstalled_mcgyvr_is_named_as_having_no_version(tmp_path: Path) -> None:
    """``0.0.0+uninstalled`` is what ``src/mcgyvr/__init__.py`` reports for a
    tree that was never installed. It is not a version, and it is said to be
    that rather than reported as merely old."""
    home = tmp_path / "home"
    home.mkdir()
    path = _reporting(tmp_path / "bin", "0.0.0+uninstalled")

    result = _run_install_with_path(home, path)

    assert result.returncode == 0, result.stderr
    assert (home / CLAUDE_SKILL).exists(), "a warning must not stop the install"
    assert "never installed" in result.stderr, result.stderr


def test_an_mcgyvr_that_cannot_state_its_version_warns_and_still_installs(
    tmp_path: Path,
) -> None:
    """``set -euo pipefail`` is in force: a non-zero ``--version`` must not
    abort an install that had already succeeded."""
    home = tmp_path / "home"
    home.mkdir()
    path = _shim(tmp_path / "bin", "#!/usr/bin/env bash\nexit 1\n")

    result = _run_install_with_path(home, path)

    assert result.returncode == 0, result.stderr
    assert (home / CLAUDE_SKILL).exists(), "a warning must not stop the install"
    assert "did not report a version" in result.stderr, result.stderr


@pytest.mark.parametrize(
    "reported",
    [
        "0.1.0",
        # The shape a real dev build has: a PEP 440 pre-release plus local
        # build metadata. Naive string comparison reads this as older than
        # `0.1.0` on the `+g...` tail; stripping the local part and comparing
        # with `sort -V` reads it as newer, which it is.
        "0.1.1.dev376+ga624cdc2",
        "0.2.0",
    ],
)
def test_a_new_enough_mcgyvr_is_not_warned_about(tmp_path: Path, reported: str) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = _reporting(tmp_path / "bin", reported)

    result = _run_install_with_path(home, path)

    assert result.returncode == 0, result.stderr
    assert result.stderr == "", result.stderr
