"""The skill sheds its examples, the shed cannot be checked vacuously, and shrinks.

Plan actions 27-29 (2026-09-09, "mcgyvr separation — plan v4"). Action 27: the
nine task-type examples move out of ``skills/mcgyvr/SKILL.md`` into
``skills/mcgyvr/references/examples.md``; ``SKILL.md`` keeps one pointer line,
and the examples must still load through the contract loader — the guarantee
``tests/test_the_mcgyvr_skill_is_rendered_from_the_schema.py`` already holds on
``docgen.EXAMPLES`` must not weaken because the text moved to a second file.

Action 28: ``tests/red_port/test_dod_every_task_type_runs.py`` greps
``SKILL.md`` for ``task_type: {name}``. Once 27 lands, that string is nowhere
in ``SKILL.md`` any more, so the grep matches nothing for every name and the
guard's assertion — "no non-runnable type's example is offered" — is
vacuously true whether or not anything is wrong. This file asserts, from
outside that guard (it is read here, never edited — the repoint is the GREEN
step's job), that the file it must be repointed at both is named in it and
actually carries the examples it claims to check.

Action 29: the ``SKILL.md`` body sits under a byte budget. The number was a
placeholder that could not pass until actions 19-27 had run, so the mechanism
was pinned without anyone being able to satisfy it by picking a number instead
of doing the shrinking; it is now the measured size (see the constant).
"""

from __future__ import annotations

import re
from pathlib import Path

from mcgyvr import docgen
from mcgyvr.contract import load

REPO = Path(__file__).resolve().parent.parent
SKILL_MD = REPO / "skills" / "mcgyvr" / "SKILL.md"
EXAMPLES_MD = REPO / "skills" / "mcgyvr" / "references" / "examples.md"
DOD_GUARD = REPO / "tests" / "red_port" / "test_dod_every_task_type_runs.py"

YAML_FENCE = re.compile(r"```yaml\n(.*?)```", re.DOTALL)

#: Chosen after actions 19-27 landed, not before (the plan: "Choose the number
#: after 19-27 have run. Do not choose it first."). The body measured 16,702
#: bytes with the ladder prose deleted and the nine examples moved out — down
#: from 20,355 — and then 18,206 once the review of 2026-09-09 put back what
#: the scrub had taken from an orchestrator: a distinct gloss and remedy per
#: `outcome`, the two outcomes no different contract can move, `--config`, and
#: what declaring `risk: high` causes. That growth was argued for; this number
#: is raised deliberately to hold it and no more.
#:
#: The headroom is 94 bytes. The previous comment claimed 298 bytes was "less
#: than one Keys-table row" and was simply wrong — the shortest row in the
#: table (`verification`) is 113 bytes, and `scope.forbid` is ~190. 94 is under
#: the shortest row that exists, so a schema key added without anything else
#: shrinking still fails here, which is the decision this number exists to
#: force. Tightened rather than re-justified.
MAX_SKILL_BODY_BYTES = 18_300


def _body(path: Path) -> str:
    """SKILL.md after its frontmatter, matching test_skill_packaging.py's ``_body``."""
    return path.read_text(encoding="utf-8").split("---", 2)[2]


def test_the_examples_leave_skill_md_for_a_references_file(tmp_path: Path) -> None:
    """Action 27: the nine examples move to skills/mcgyvr/references/examples.md.

    SKILL.md keeps one pointer line, not the fenced yaml itself, and the
    moved examples still validate through the contract loader — copying one
    from the new file must still be copying a shape known to validate.
    """
    skill_text = SKILL_MD.read_text(encoding="utf-8")
    assert "```yaml" not in skill_text, (
        "SKILL.md still carries fenced yaml examples inline; action 27 moves "
        f"them to {EXAMPLES_MD.relative_to(REPO)}, leaving one pointer line"
    )
    pointer = str(EXAMPLES_MD.relative_to(REPO))
    assert pointer in skill_text, f"SKILL.md names no pointer to {pointer}"
    assert EXAMPLES_MD.is_file(), f"{EXAMPLES_MD} does not exist yet"
    examples_text = EXAMPLES_MD.read_text(encoding="utf-8")
    for task_type in docgen.EXAMPLES:
        assert f"task_type: {task_type}" in examples_text, task_type
    blocks = YAML_FENCE.findall(examples_text)
    assert len(blocks) == len(docgen.EXAMPLES), (
        f"expected {len(docgen.EXAMPLES)} fenced yaml examples in "
        f"{EXAMPLES_MD.relative_to(REPO)}, found {len(blocks)}"
    )
    for block in blocks:
        path = tmp_path / "example.yaml"
        path.write_text(block, encoding="utf-8")
        contract = load(path)
        assert contract.task_type in docgen.EXAMPLES


def test_the_dod_guard_cannot_pass_while_checking_nothing() -> None:
    """Action 28: a vacuous pass of the DoD guard must be impossible.

    ``test_dod_every_task_type_runs.py`` is read here, never edited; the
    repoint onto the new file is the GREEN step's job. This pins two things
    that repoint must both do: name the file the examples actually live in
    after action 27, and have that file actually carry every example the
    guard claims to check. A guard that only names the right path but reads
    a file missing its examples is exactly as vacuous as one still reading
    the now-emptied SKILL.md section.
    """
    guard_source = DOD_GUARD.read_text(encoding="utf-8")
    assert "examples.md" in guard_source, (
        "test_dod_every_task_type_runs.py still only reads SKILL.md; once "
        "action 27 lands that file no longer carries `task_type: {name}` "
        "lines, so the guard's grep matches nothing and its assertion holds "
        "vacuously for every task type"
    )
    assert EXAMPLES_MD.is_file(), (
        f"{EXAMPLES_MD} must exist and hold real examples, or a guard "
        "repointed at it would still be checking nothing"
    )
    examples_text = EXAMPLES_MD.read_text(encoding="utf-8")
    for task_type in docgen.EXAMPLES:
        assert f"task_type: {task_type}" in examples_text, (
            f"{EXAMPLES_MD} is missing the {task_type} example; a guard "
            "reading this file would pass without having checked it"
        )


def test_the_skill_body_stays_under_its_byte_budget() -> None:
    """Action 29: the SKILL.md body sits under a byte budget written into the test.

    ``MAX_SKILL_BODY_BYTES`` was measured once actions 19-27 had run and
    shrunk the body for real — never invented first to make this test pass.
    Growing past it is a decision to be argued for, not a diff nobody noticed.
    """
    body_bytes = len(_body(SKILL_MD).encode("utf-8"))
    assert body_bytes <= MAX_SKILL_BODY_BYTES, (
        f"SKILL.md body is {body_bytes} bytes, over the "
        f"{MAX_SKILL_BODY_BYTES} it is budgeted; something else has to leave "
        "the skill, or the budget has to be argued up"
    )
