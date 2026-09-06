"""RED tests: mcgyvr packaged as a skill for Claude CLI and pi.

Zero implementation expected. Every test here fails until the skill lands at
``skills/mcgyvr/``. The contract is the Agent Skills standard both harnesses
implement: a ``SKILL.md`` with valid frontmatter, an install script that places
it into ``~/.claude/skills`` and ``~/.pi/agent/skills``, a safe first-install
default, and an onboarding path wired to the existing ``mcgyvr`` CLI.
"""

from __future__ import annotations

import os
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
    end = next(
        (i for i in range(1, len(lines)) if lines[i].strip() == "---"), None
    )
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
    text = (_body(SKILL_MD) + " " + str(_frontmatter(SKILL_MD).get("description", ""))).lower()
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
        assert landed.read_text(encoding="utf-8") == SKILL_MD.read_text(encoding="utf-8")


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


def test_skill_documents_the_first_run_onboarding() -> None:
    assert SKILL_MD.exists(), "skills/mcgyvr/SKILL.md must exist"
    body = _body(SKILL_MD)
    assert "mcgyvr init" in body
    assert "mcgyvr pool" in body


def test_skill_documents_the_levers() -> None:
    # The one config file a user edits: its sources, ladder and budgets are the
    # knobs the skill must teach a first-time user to read with `mcgyvr pool`.
    assert SKILL_MD.exists(), "skills/mcgyvr/SKILL.md must exist"
    body = _body(SKILL_MD)
    for lever in ("ladder", "sources", "budgets"):
        assert lever in body


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
