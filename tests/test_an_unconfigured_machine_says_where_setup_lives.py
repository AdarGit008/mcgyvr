"""A machine nobody has set up still fails toward SETUP.md, not into silence.

Plan v4 (2026-09-09), actions 13, 14 and 30 through 34. Actions 4 and 5 take
Step 0 out of `SKILL.md`, which was the only in-context route an agent had
back to setup; these actions are what replace it.

Actions 13 and 14: Step 2 (`mcgyvr contract CONTRACT.yaml`) and Step 3
(`mcgyvr run CONTRACT.yaml ...`) are the two commands a Step-0-less skill
still points an agent at, in order, on every machine including one nobody has
run `mcgyvr init` on. They are not the same command. Step 3 needs a ladder:
`_run` already refuses a model-executed contract when no config loads, but
names only `str(config_error)`, and from here it names where `SETUP.md` lives
too. Step 2 needs nothing: `_contract` does not consult a config, and must
not start — a contract names no model, rung, tier or host, so validating one
is exactly the work an orchestrator does knowing nothing about the ladder.
Action 14 is that: Step 2 validates with no config and never mentions setup.

Actions 30 through 34 are `install.sh`. 30: a `SKILL.md` that does not parse
as frontmatter, whose `name` is not the directory it lands in, or whose
`description` is out of bounds, is refused — and refused on the source,
before the first `cp`. Verifying the copy read the bytes a harness would
load, but it read them one `cp` too late: the file that failed was already
installed, with no record beside it, and a missing record is exactly what the
next run reads as "installed before this script kept one" and overwrites
without asking. That the bytes which landed are the bytes that were checked
is a digest comparison, made as each file is copied. 31: an argument it does
not recognise gets one line naming `SETUP.md`, not a maintained document per
harness. 32: it refuses to silently overwrite an installed copy a person has
hand-edited, without `--force`, and says which file differs — every file it
installed, the reference files among them. 33 is 32's other half: a refusal
that cannot tell a hand edit from an ordinary `SKILL.md` upgrade would block
the very upgrade action 4 makes, on every machine that already has the old,
Step-0-carrying file installed. It is driven twice — once where a record
exists, and once on the machine that has none. 34:
`install.sh`'s stdout is a list of paths, `SETUP.md`'s among them since
action 7 keeps it out of the installed copies, and never a file's contents —
stdout is the only part of running it that can reach an agent's context.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests import livejournal as lj

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / "skills" / "mcgyvr"
SKILL_MD = SKILL_DIR / "SKILL.md"
INSTALL_SH = SKILL_DIR / "install.sh"

# Named by action 1: `skills/mcgyvr/SETUP.md`, beside the skill it is not
# part of. Checked as a substring rather than the absolute path, so this
# holds however a caller renders it (bare, or with a repo prefix).
SETUP_PATH_FRAGMENT = "skills/mcgyvr/SETUP.md"

CLAUDE_SKILL = Path(".claude") / "skills" / "mcgyvr" / "SKILL.md"
PI_SKILL = Path(".pi") / "agent" / "skills" / "mcgyvr" / "SKILL.md"

# The Agent Skills layout both harnesses read: the reference files sit in a
# `references/` directory beside SKILL.md, and SKILL.md points at them
# skill-relative. Action 27 moved the nine examples there.
EXAMPLES = Path("references") / "examples.md"
CLAUDE_EXAMPLES = CLAUDE_SKILL.parent / EXAMPLES
PI_EXAMPLES = PI_SKILL.parent / EXAMPLES


# --- shared idiom, copied from tests/test_skill_packaging.py ---------------


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


def _install_copy(tmp_path: Path, skill_md_text: str) -> Path:
    """A private copy of install.sh beside a SKILL.md this test controls.

    install.sh locates SKILL.md next to its own ``BASH_SOURCE``, so copying
    both into one throwaway directory drives it against content the repo's
    own SKILL.md must never carry (a broken frontmatter, a mismatched name,
    an over-long description).
    """
    src = tmp_path / "skill_src"
    src.mkdir()
    (src / "install.sh").write_bytes(INSTALL_SH.read_bytes())
    (src / "SKILL.md").write_text(skill_md_text, encoding="utf-8")
    return src


def _run_install_from(
    script_dir: Path, home: Path, *args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script_dir / "install.sh"), *args],
        cwd=script_dir,
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
        timeout=60,
    )


def _skill_md(
    *,
    name: str = "mcgyvr",
    description: str = "test fixture skill",
    body: str = "Body.",
    frontmatter_closed: bool = True,
) -> str:
    lines = ["---", f"name: {name}", f"description: {description}"]
    if frontmatter_closed:
        lines.append("---")
    lines += ["", body]
    return "\n".join(lines) + "\n"


# --- actions 13, 14: the two commands a bare machine still reaches ---------


@pytest.fixture
def unconfigured_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A HOME and a cwd where no config, of any kind, resolves."""
    home = tmp_path / "home"
    home.mkdir()
    lj.clean_env(monkeypatch, home)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return home


@pytest.fixture
def unconfigured_home_with_session(
    unconfigured_home: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """The same bare machine, with the session `run` requires to start at all."""
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(unconfigured_home, "s1")
    return unconfigured_home


def test_mcgyvr_run_with_no_config_names_the_setup_document(
    tmp_path: Path,
    unconfigured_home_with_session: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Step 3, on a bare machine, points back to where setup actually lives.

    `_run` already refuses a model-executed contract when
    `config is None and not contract.is_deterministic`; today it prints only
    `str(config_error)`, which says `mcgyvr init` but never where the fuller
    instructions are. With Step 0 gone from `SKILL.md`, this is the error an
    agent following Step 3 is left with.
    """
    repo = lj.make_repo(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(["run", str(contract), "--repo", str(repo), "--sandbox", "tempdir"])

    err = capsys.readouterr().err
    assert code != 0, err
    assert SETUP_PATH_FRAGMENT in err, err


def test_mcgyvr_contract_validates_with_no_config_and_never_mentions_setup(
    tmp_path: Path,
    unconfigured_home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Step 2 validates a contract on a machine with no config, and says so.

    An earlier draft of this test asked `_contract` to refuse when no config
    loads, and it was wrong. A contract names no model, no rung, no tier and
    no host (`contract.py:461-647`); it is authored and validated by an
    orchestrator that knows nothing about the ladder, and that is the asset
    the whole plan exists to protect. Making Step 2 consult a config would
    make the ladder a precondition of writing a contract about it, which is
    the opposite of what the plan is for.

    So the seam is Step 3, not Step 2: `mcgyvr run` needs a ladder and names
    `SETUP.md` when there is none, and `mcgyvr contract` exits 0 here without
    ever having asked. It does not mention setup, because it needed none.
    """
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(["contract", str(contract)])

    out, err = capsys.readouterr()
    assert code == 0, err
    assert "valid" in out, out
    assert SETUP_PATH_FRAGMENT not in out + err, out + err


# --- action 30: install.sh verifies the skill, before it copies it ----------


def test_install_refuses_a_copied_skill_whose_frontmatter_does_not_parse(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    src = _install_copy(tmp_path, _skill_md(frontmatter_closed=False))

    result = _run_install_from(src, home)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "frontmatter" in (result.stdout + result.stderr).lower()


def test_install_refuses_a_copied_skill_whose_name_does_not_match_its_directory(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    src = _install_copy(tmp_path, _skill_md(name="not-mcgyvr"))

    result = _run_install_from(src, home)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "name" in (result.stdout + result.stderr).lower()


def test_install_refuses_a_copied_skill_whose_description_is_out_of_bounds(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    src = _install_copy(tmp_path, _skill_md(description="x" * 1025))

    result = _run_install_from(src, home)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "description" in (result.stdout + result.stderr).lower()


def test_a_refused_skill_is_not_installed_anywhere(tmp_path: Path) -> None:
    """The point of checking the source rather than the copy.

    A `SKILL.md` that fails is refused before the first `cp`, so a machine
    that has never had the skill still has not, and a machine that had one
    still has the one it had. Verifying after copying left the file that
    failed installed, and — because the run stopped before writing a record —
    left it there with no `.mcgyvr-installed` beside it, which the next run
    reads as an old install and overwrites silently. That is the case
    check_installed's comment says cannot happen.
    """
    home = tmp_path / "home"
    home.mkdir()
    src = _install_copy(tmp_path, _skill_md(name="not-mcgyvr"))

    result = _run_install_from(src, home)

    assert result.returncode != 0, result.stdout + result.stderr
    landed = sorted(str(p.relative_to(home)) for p in home.rglob("*") if p.is_file())
    assert landed == [], landed


# --- action 27's other half: the references travel with the skill -----------


def test_install_places_the_reference_examples_beside_the_installed_skill(
    tmp_path: Path,
) -> None:
    """The installed tree is the Agent Skills layout, references included.

    Action 27 moved the nine examples out of `SKILL.md` into
    `skills/mcgyvr/references/examples.md`, and `SKILL.md` keeps one pointer
    line to them. A script that copies only `SKILL.md` leaves that pointer
    aimed at a file that is not there: an agent whose machine INSTALLED the
    skill, rather than cloning this repository, cannot reach a single example.
    So `references/` is installed too, and byte for byte — the examples load
    through the contract validator, and a copy that is not the checked one is
    not the shape that was checked.
    """
    repo_examples = SKILL_DIR / EXAMPLES
    assert repo_examples.exists(), "skills/mcgyvr/references/examples.md must exist"
    home = tmp_path / "home"
    home.mkdir()

    result = _run_install(home)

    assert result.returncode == 0, result.stdout + result.stderr
    for target in (CLAUDE_EXAMPLES, PI_EXAMPLES):
        landed = home / target
        assert landed.exists(), f"expected {target} under HOME"
        assert landed.read_bytes() == repo_examples.read_bytes()


def test_uninstall_removes_the_installed_reference_files_too(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    assert _run_install(home).returncode == 0
    for target in (CLAUDE_EXAMPLES, PI_EXAMPLES):
        assert (home / target).exists()

    result = _run_install(home, "--uninstall")

    assert result.returncode == 0, result.stdout + result.stderr
    for target in (CLAUDE_EXAMPLES, PI_EXAMPLES):
        assert not (home / target).exists(), target
        assert not (home / target).parent.exists(), f"{target}: references/ stayed"


def test_an_edited_reference_file_is_refused_the_way_an_edited_skill_is(
    tmp_path: Path,
) -> None:
    """Action 32 covers everything installed, not only `SKILL.md`.

    The record beside each installed copy names every file this script wrote
    there, so a hand edit to an installed example is the same refusal a hand
    edit to the installed skill is — and, like it, leaves the edit alone.
    """
    home = tmp_path / "home"
    home.mkdir()
    assert _run_install(home).returncode == 0
    installed = home / CLAUDE_EXAMPLES
    edited = installed.read_bytes() + b"\n<!-- hand-edited -->\n"
    installed.write_bytes(edited)

    result = _run_install(home)

    assert result.returncode != 0, result.stdout + result.stderr
    combined = result.stdout + result.stderr
    assert str(installed) in combined, combined
    assert installed.read_bytes() == edited, "unforced install touched an edit"


# --- action 31: an argument install.sh does not recognise -------------------


def test_an_unrecognised_argument_names_the_setup_document_in_one_line(
    tmp_path: Path,
) -> None:
    """Renamed to say what it checks.

    `install.sh` takes no harness argument: it installs into both harnesses
    it knows and reads nothing about a third from its command line. What
    action 31 is implemented as, and what this drives, is the `*)` arm of its
    argument `case` — any word it does not understand, `codex` among them,
    gets the one line naming `SETUP.md` and no per-harness document. The test
    said "harness" and checked an argument; naming the argument is the
    smaller of the two changes, and detecting harnesses would be the second
    installable plan v4 ruled out ("Not doing": Hermes and Codex install
    targets, deferred by PR 377 and still deferred).
    """
    home = tmp_path / "home"
    home.mkdir()

    result = _run_install(home, "codex")

    combined = result.stdout + result.stderr
    lines = [line for line in combined.splitlines() if line.strip()]
    assert len(lines) == 1, combined
    assert SETUP_PATH_FRAGMENT in combined, combined


# --- actions 32, 33: refuse a hand edit, never an upgrade -------------------


def test_install_refuses_to_overwrite_a_hand_edited_copy_without_force(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    assert _run_install(home).returncode == 0

    installed = home / CLAUDE_SKILL
    edited = installed.read_bytes() + b"\n<!-- hand-edited -->\n"
    installed.write_bytes(edited)

    result = _run_install(home)

    assert result.returncode != 0, result.stdout + result.stderr
    combined = result.stdout + result.stderr
    assert str(installed) in combined, combined
    assert installed.read_bytes() == edited, "unforced install touched an edit"


def test_the_no_force_refusal_does_not_block_an_upgrade_that_changes_the_source(
    tmp_path: Path,
) -> None:
    """32's refusal is for a hand edit, never for the repo's own SKILL.md
    changing between two runs of install.sh — which is exactly the shape
    action 4 takes to remove Step 0. A refusal that could not tell the two
    apart would keep every machine that already has the old, Step-0-carrying
    file on it forever, which is what would defeat action 4.

    Both halves are proved here, in one test: the hand edit is refused
    first, to show this action does not ask for that protection to be
    weakened; only then does the source itself change, with nobody having
    touched the installed copy, and that must go through unforced.
    """
    home = tmp_path / "home"
    home.mkdir()
    src = _install_copy(tmp_path, _skill_md(description="old"))
    assert _run_install_from(src, home).returncode == 0
    installed = home / CLAUDE_SKILL

    edited = installed.read_bytes() + b"\n<!-- hand-edited -->\n"
    installed.write_bytes(edited)
    refused = _run_install_from(src, home)
    assert refused.returncode != 0, refused.stdout + refused.stderr
    assert installed.read_bytes() == edited, "the hand edit must still be protected"

    installed.write_bytes((src / "SKILL.md").read_bytes())
    (src / "SKILL.md").write_text(_skill_md(description="new"), encoding="utf-8")

    upgraded = _run_install_from(src, home)

    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
    assert installed.read_bytes() == (src / "SKILL.md").read_bytes()


def test_a_machine_carrying_the_old_skill_with_no_record_upgrades_unforced(
    tmp_path: Path,
) -> None:
    """The machine action 33 is actually about, which nothing tested.

    The test above installs first — so a `.mcgyvr-installed` record exists —
    and only then changes the source. The case the plan feared has no record
    at all: a machine that installed the skill before this script kept one,
    carrying the pre-change, Step-0-carrying `SKILL.md`. There, "installed
    differs from source" is the only thing that can be seen, and it is
    equally true of the hand edit and of the upgrade. If that is refused,
    action 32 defeats action 4 on every machine that already has the skill.

    The old file is taken from `git show main:skills/mcgyvr/SKILL.md` rather
    than fabricated, so what is driven is the upgrade those machines make.
    """
    old = subprocess.run(
        ["git", "show", "main:skills/mcgyvr/SKILL.md"],
        cwd=REPO,
        capture_output=True,
        timeout=60,
    )
    assert old.returncode == 0, old.stderr.decode()
    assert b"mcgyvr init" in old.stdout, (
        "main's SKILL.md must still be the Step-0-carrying one this upgrade "
        "is for; if it is not, this test is no longer driving action 33"
    )

    home = tmp_path / "home"
    home.mkdir()
    installed = home / CLAUDE_SKILL
    installed.parent.mkdir(parents=True)
    installed.write_bytes(old.stdout)
    record = installed.parent / ".mcgyvr-installed"
    assert not record.exists(), "the machine this is about has no record"

    result = _run_install(home)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "--force" not in result.stdout + result.stderr
    assert installed.read_bytes() == SKILL_MD.read_bytes()
    assert (home / CLAUDE_EXAMPLES).read_bytes() == (SKILL_DIR / EXAMPLES).read_bytes()
    assert record.exists(), "the upgrade must leave the record it was missing"


# --- action 34: stdout is paths, never contents -----------------------------


def test_install_stdout_names_setup_md_and_never_dumps_file_contents(
    tmp_path: Path,
) -> None:
    """The paths it wrote, `SETUP.md`'s among them, and no file's contents.

    What action 34 keeps out of a context is a file's contents — the
    frontmatter, and the body — so that, and not "every line is a path", is
    what this asserts. `Invoke it with /mcgyvr; it does not load itself.` is
    one instruction to the operator who ran the script, and the only thing
    that says the skill does not load itself; it is not a file's contents and
    it stays.

    The contents half is proved against a `SKILL.md` this test writes, whose
    frontmatter and body carry markers nothing else says, so it holds whatever
    the repo's own `SKILL.md` comes to say.
    """
    home = tmp_path / "home"
    home.mkdir()

    result = _run_install(home)

    assert result.returncode == 0, result.stdout + result.stderr
    assert SETUP_PATH_FRAGMENT in result.stdout, result.stdout
    assert SKILL_MD.read_text(encoding="utf-8") not in result.stdout

    marked_home = tmp_path / "marked_home"
    marked_home.mkdir()
    src = _install_copy(
        tmp_path,
        _skill_md(description="DESCRIPTION-MARKER", body="BODY-MARKER"),
    )

    marked = _run_install_from(src, marked_home)

    assert marked.returncode == 0, marked.stdout + marked.stderr
    assert SETUP_PATH_FRAGMENT in marked.stdout, marked.stdout
    assert "DESCRIPTION-MARKER" not in marked.stdout, marked.stdout
    assert "BODY-MARKER" not in marked.stdout, marked.stdout
    assert "---" not in marked.stdout, marked.stdout
    assert (src / "SKILL.md").read_text(encoding="utf-8") not in marked.stdout
