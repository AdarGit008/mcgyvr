"""RED tests: Step 0 leaves the skill; setup moves to SETUP.md.

Plan v4, ruled 2026-09-09: one package, one seam, two documents. `SKILL.md`
is what an agent reads to author a contract; `SETUP.md` is what a machine's
owner reads to stand the ladder up. Nothing an agent loads to author a
contract may name a setup verb, a config lever, or the ladder — the
assertable property the plan holds to. `SETUP.md` is rendered from
`config.SCHEMA`, lives beside the skill it is not part of
(`skills/mcgyvr/SETUP.md`), and `install.sh` never copies it into either
harness.

Zero implementation expected. Every test here fails until Step 0 is cut out
of `SKILL.md` and `docgen.render_setup()` lands.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from pathlib import Path

from mcgyvr import docgen

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / "skills" / "mcgyvr"
SKILL_MD = SKILL_DIR / "SKILL.md"
SETUP_MD = SKILL_DIR / "SETUP.md"
INSTALL_SH = SKILL_DIR / "install.sh"

CLAUDE_DIR = Path(".claude") / "skills" / "mcgyvr"
PI_DIR = Path(".pi") / "agent" / "skills" / "mcgyvr"

#: The setup verbs Step 0 names today (action 4).
SETUP_VERBS: tuple[str, ...] = (
    "init",
    "pool",
    "detect",
    "capabilities",
    "emit",
    "scan",
)

#: The three keys Step 0 calls "the levers" (action 5).
LEVERS: tuple[str, ...] = ("sources", "ladder", "budgets")


def _body(path: Path) -> str:
    return path.read_text(encoding="utf-8").split("---", 2)[2]


def _verb_hits(text: str) -> list[str]:
    """Setup verbs named in ``text``, matched whole-word so `detect` does not
    fire on `detected`."""
    return [v for v in SETUP_VERBS if re.search(rf"\b{v}\b", text)]


def _lever_bullet_hits(text: str) -> list[str]:
    """Levers introduced BY NAME as config levers — the bulleted
    `` - `lever` — ... `` lines Step 0 uses.

    Not a raw substring check: `ladder_spent` legitimately contains "ladder"
    (action 25's exception list), so matching lever *usage* rather than any
    occurrence of the word is what action 5 asks for.
    """
    return [lv for lv in LEVERS if re.search(rf"^- `{lv}` ", text, re.MULTILINE)]


def _sentences(text: str) -> set[str]:
    """``text`` split into sentences, whitespace-normalised, trivia dropped."""
    flat = " ".join(text.split())
    pieces = re.split(r"(?<=[.!?])\s+", flat)
    return {p.strip() for p in pieces if len(p.strip()) > 15}


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


# --- Step 0 leaves SKILL.md ------------------------------------------------


def test_skill_body_names_no_setup_verb() -> None:
    """SKILL.md sends an agent to author a contract; it names no setup verb."""
    assert SKILL_MD.exists(), "skills/mcgyvr/SKILL.md must exist"
    hits = _verb_hits(_body(SKILL_MD))
    assert hits == [], f"SKILL.md still names setup verb(s): {hits}"


def test_skill_body_names_no_lever_as_a_config_lever() -> None:
    """SKILL.md never introduces sources, ladder or budgets as config levers."""
    assert SKILL_MD.exists(), "skills/mcgyvr/SKILL.md must exist"
    hits = _lever_bullet_hits(_body(SKILL_MD))
    assert hits == [], f"SKILL.md still names lever(s) as config levers: {hits}"


# --- SETUP.md carries what Step 0 left behind -------------------------------


def test_setup_md_carries_the_first_run_onboarding_path() -> None:
    """SETUP.md carries `mcgyvr init` -> `mcgyvr pool` and the three levers."""
    assert SETUP_MD.exists(), "skills/mcgyvr/SETUP.md must exist"
    text = SETUP_MD.read_text(encoding="utf-8")
    init_at = text.find("mcgyvr init")
    pool_at = text.find("mcgyvr pool")
    assert init_at != -1, "SETUP.md must document `mcgyvr init`"
    assert pool_at != -1, "SETUP.md must document `mcgyvr pool`"
    assert init_at < pool_at, "`mcgyvr init` must come before `mcgyvr pool`"
    for lever in LEVERS:
        assert lever in text, f"SETUP.md must document the `{lever}` lever"


def test_setup_md_is_rendered_from_config_schema_not_hand_written() -> None:
    """SETUP.md opens with the same generated-code marker the config
    reference does — proof it is a projection of `config.SCHEMA`, not
    hand-written prose."""
    assert SETUP_MD.exists(), "skills/mcgyvr/SETUP.md must exist"
    text = SETUP_MD.read_text(encoding="utf-8")
    assert text.startswith(docgen.MARKER), (
        "SETUP.md must open with docgen.MARKER, the provenance mark the "
        "config reference renders with — proof it is rendered from "
        "config.SCHEMA and not hand-written"
    )


# --- install.sh never ships SETUP.md ----------------------------------------


def test_install_sh_does_not_copy_setup_md_into_either_harness(
    tmp_path: Path,
) -> None:
    assert SETUP_MD.exists(), "skills/mcgyvr/SETUP.md must exist"
    home = tmp_path / "home"
    home.mkdir()
    result = _run_install(home)
    assert result.returncode == 0, result.stderr
    for target in (CLAUDE_DIR, PI_DIR):
        installed = home / target
        assert not (installed / "SETUP.md").exists(), (
            f"install.sh copied SETUP.md into {installed}; SETUP.md lives "
            "beside the skill it is not part of and must not be installed"
        )


def test_installed_files_name_no_setup_verb_or_lever(tmp_path: Path) -> None:
    """After install.sh runs, nothing under HOME names a setup verb or a
    lever — checked against installed bytes, not repo bytes."""
    home = tmp_path / "home"
    home.mkdir()
    result = _run_install(home)
    assert result.returncode == 0, result.stderr
    for target in (CLAUDE_DIR, PI_DIR):
        installed_dir = home / target
        for installed_file in installed_dir.rglob("*"):
            if not installed_file.is_file():
                continue
            text = installed_file.read_text(encoding="utf-8")
            verb_hits = _verb_hits(text)
            lever_hits = _lever_bullet_hits(text)
            assert verb_hits == [], f"{installed_file} names verb(s): {verb_hits}"
            assert lever_hits == [], f"{installed_file} names lever(s): {lever_hits}"


# --- the two documents do not restate each other ----------------------------


def test_no_sentence_appears_in_both_documents() -> None:
    """SKILL.md and SETUP.md were split, not duplicated: no sentence appears
    in both."""
    assert SKILL_MD.exists(), "skills/mcgyvr/SKILL.md must exist"
    assert SETUP_MD.exists(), "skills/mcgyvr/SETUP.md must exist"
    skill_sentences = _sentences(_body(SKILL_MD))
    setup_sentences = _sentences(SETUP_MD.read_text(encoding="utf-8"))
    shared = skill_sentences & setup_sentences
    assert shared == set(), f"sentence(s) duplicated across both documents: {shared}"


# --- the 2026-09-03 ruling, narrowed a third time ---------------------------


def test_docgen_module_docstring_says_setup_is_not_part_of_the_skill() -> None:
    """The 2026-09-03 ruling, narrowed a third time: setup is not part of the
    skill mcgyvr generates from contract.SCHEMA."""
    doc = docgen.__doc__ or ""
    assert "setup is not part of" in doc.lower(), (
        "docgen.py's module docstring must narrow the 2026-09-03 ruling a "
        "third time: the skill is one instruction generated from "
        "contract.SCHEMA, and setup is not part of it"
    )


def test_schema_rendering_test_docstring_says_setup_is_not_part_of_the_skill() -> None:
    """The same narrowing lives in the schema-rendering test's docstring too
    — another concern owns that file, so this reads its text rather than
    editing it."""
    path = REPO / "tests" / "test_the_mcgyvr_skill_is_rendered_from_the_schema.py"
    assert path.exists(), f"{path} must exist"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    doc = ast.get_docstring(tree) or ""
    assert "setup is not part of" in doc.lower(), (
        f"{path}'s module docstring must narrow the 2026-09-03 ruling a "
        "third time too: setup is not part of the skill"
    )
