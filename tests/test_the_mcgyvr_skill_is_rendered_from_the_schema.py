"""The /mcgyvr skill is rendered from the schema, so an agent never guesses a field.

An agent that authors contracts learns the fields today by being rejected one
key at a time. The owner's ruling (2026-09-03): the schema reaches the agent
as a step of one passive, always-on ``/mcgyvr`` skill — not a flag, not a
second skill — and the skill is generated the way the config reference is,
from the ``Field`` declarations the validator walks, so a documented key and
a validated key cannot drift.

Three things hold. Every field in ``contract.SCHEMA``, nested ones included,
is named in the skill. Every example the skill carries loads through
``contract.load`` — an example that does not validate teaches the wrong
thing. And ``make docs-check`` refuses a committed skill that differs from
what the schema renders, the same guard the config reference has.
"""

from __future__ import annotations

from pathlib import Path

from mcgyvr import docgen
from mcgyvr.contract import SCHEMA, Field, load


def _names(fields: tuple[Field, ...], prefix: str = "") -> list[str]:
    out: list[str] = []
    for field in fields:
        out.append(f"{prefix}{field.name}")
        out += _names(field.block, f"{prefix}{field.name}.")
    return out


def test_every_schema_field_is_named_in_the_skill() -> None:
    text = docgen.render_skill()
    assert text.startswith("---\nname: mcgyvr\n"), text[:80]
    for name in _names(SCHEMA):
        assert f"`{name}`" in text, name


def test_every_example_in_the_skill_loads_as_a_contract(tmp_path: Path) -> None:
    assert docgen.EXAMPLES, "the skill carries no examples"
    for task_type, text in docgen.EXAMPLES.items():
        path = tmp_path / f"{task_type}.yaml"
        path.write_text(text, encoding="utf-8")
        contract = load(path)
        assert contract.task_type == task_type


def test_the_skill_walks_the_run_and_the_replan(tmp_path: Path) -> None:
    text = docgen.render_skill()
    for needle in (
        "mcgyvr contract",
        "mcgyvr run",
        "result:",
        "findings",
        "--commit",
    ):
        assert needle in text, needle


def test_docs_check_refuses_a_skill_that_drifted(tmp_path: Path) -> None:
    reference = tmp_path / "config-reference.md"
    skill = tmp_path / "SKILL.md"
    reference.write_text(docgen.render_reference(), encoding="utf-8")
    skill.write_text("stale\n", encoding="utf-8")
    argv = ["--check", "--output", str(reference), "--skill-output", str(skill)]
    assert docgen.main(argv) == 1
    skill.write_text(docgen.render_skill(), encoding="utf-8")
    assert docgen.main(argv) == 0
