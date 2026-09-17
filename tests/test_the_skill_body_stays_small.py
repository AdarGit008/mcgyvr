"""The skill sheds its examples, the shed cannot be checked vacuously, and shrinks.

The action numbers label the tests below. Action 27: the nine task-type
examples live in ``skills/mcgyvr/references/examples.md``, not in
``skills/mcgyvr/SKILL.md``; ``SKILL.md`` keeps one pointer line, and the
examples still load through the contract loader — the guarantee
``tests/test_the_mcgyvr_skill_is_rendered_from_the_schema.py`` holds on
``docgen.EXAMPLES`` does not weaken because the text is in a second file.

Action 28: ``SKILL.md`` carries no examples, so a guard that greps it for
``task_type: {name}`` checks none, and its assertion — "no non-runnable type's example
is offered" — is vacuously true whether or not anything is wrong. This file
asserts, from outside ``tests/red_port/test_dod_every_task_type_runs.py``
(read here, never edited), that the file that guard reads is named in it and
actually carries the examples it claims to check.

Action 29: the ``SKILL.md`` body sits under a byte budget (see the constant).
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

#: A byte budget for a body that carries no ladder prose and no inline
#: examples, but does carry what an orchestrator needs: a distinct gloss and
#: remedy per `outcome`, the two outcomes no different contract can move,
#: `--config`, and what declaring `risk: high` causes. Raising it is a
#: decision to be argued for.
MAX_SKILL_BODY_BYTES = 18_300


def _body(path: Path) -> str:
    """SKILL.md after its frontmatter, matching test_skill_packaging.py's ``_body``."""
    return path.read_text(encoding="utf-8").split("---", 2)[2]


def test_the_examples_leave_skill_md_for_a_references_file(tmp_path: Path) -> None:
    """Action 27: the nine examples live in skills/mcgyvr/references/examples.md.

    SKILL.md keeps one pointer line, not the fenced yaml itself, and the
    examples validate through the contract loader — copying one from that
    file is copying a shape known to validate.
    """
    skill_text = SKILL_MD.read_text(encoding="utf-8")
    assert "```yaml" not in skill_text, (
        "SKILL.md carries fenced yaml examples inline; they belong in "
        f"{EXAMPLES_MD.relative_to(REPO)}, with one pointer line left"
    )
    pointer = str(EXAMPLES_MD.relative_to(REPO))
    assert pointer in skill_text, f"SKILL.md names no pointer to {pointer}"
    assert EXAMPLES_MD.is_file(), f"{EXAMPLES_MD} does not exist"
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

    ``test_dod_every_task_type_runs.py`` is read here, never edited. This pins
    two things the guard needs: that it names the file the examples actually
    live in, and that the file actually carries every example the guard
    claims to check. A guard that names the right path but reads a file
    missing its examples is exactly as vacuous as one reading SKILL.md, which
    carries none.
    """
    guard_source = DOD_GUARD.read_text(encoding="utf-8")
    assert "examples.md" in guard_source, (
        "test_dod_every_task_type_runs.py only reads SKILL.md, which carries "
        "no examples, so the guard's grep checks none and its assertion "
        "holds vacuously for every task type"
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

    ``MAX_SKILL_BODY_BYTES`` is a budget set from the shrunk body's size,
    never invented first to make this test pass. Growing past it is a
    decision to be argued for, not a diff nobody noticed.
    """
    body_bytes = len(_body(SKILL_MD).encode("utf-8"))
    assert body_bytes <= MAX_SKILL_BODY_BYTES, (
        f"SKILL.md body is {body_bytes} bytes, over the "
        f"{MAX_SKILL_BODY_BYTES} it is budgeted; something else has to leave "
        "the skill, or the budget has to be argued up"
    )
