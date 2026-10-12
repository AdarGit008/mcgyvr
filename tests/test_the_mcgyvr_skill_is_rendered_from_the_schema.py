"""The /mcgyvr skill is rendered from the schema, so an agent never guesses a field.

The schema reaches the agent as a step of one explicitly-invoked ``/mcgyvr``
skill — not a flag, not a second skill — and the skill is generated the way the
config reference is, from the ``Field`` declarations the validator walks, so a
documented key and a validated key cannot drift. The skill is that one
instruction, generated from ``contract.SCHEMA``, and setup is not part of it:
what a machine's owner does once, before any contract is authored, is
``skills/mcgyvr/SETUP.md``, rendered from ``config.SCHEMA`` and never installed
into a harness.

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
    for name, text in docgen.EXAMPLES.items():
        path = tmp_path / f"{name}.yaml"
        path.write_text(text, encoding="utf-8")
        contract = load(path)
        assert contract.kind.name == name


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
    skill.write_text("stale\n", encoding="utf-8")
    argv = ["--check", "--output", str(reference), "--skill-output", str(skill)]
    assert docgen.main(argv) == 1
    skill.write_text(docgen.render_skill(), encoding="utf-8")
    assert docgen.main(argv) == 0
    assert not reference.exists()  # rendered for its check, then deleted


# --- the `code` example runs against the stub it describes -------------------

_STUB = """\
def chunk(items, size):
    raise NotImplementedError
"""

_TEST_CHUNK = """\
import sys

sys.path.insert(0, "src")

from pkg.chunk import chunk


def test_chunk_groups_in_order():
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
"""


def _stub_repo(root: Path) -> Path:
    """The repository the `code` example's task describes: `chunk` is a stub."""
    import subprocess

    repo = root / "repo"
    (repo / "src" / "pkg").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "pkg" / "chunk.py").write_text(_STUB, encoding="utf-8")
    (repo / "tests" / "test_chunk.py").write_text(_TEST_CHUNK, encoding="utf-8")
    (repo / ".gitignore").write_text(".pytest_cache/\n__pycache__/\n", encoding="utf-8")
    identity = [
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t.invalid",
    ]
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run(["git", *identity, "-C", str(repo), *args], check=True)
    return repo


def test_the_code_example_passes_preflight_against_the_stub_it_describes(
    tmp_path: Path,
) -> None:
    """Its fail-before test is a demonstration, so the preflight accepts it.

    The example asks for `chunk` to be implemented, so the test it names fails
    on the unchanged tree. Under `acceptance` that is refused before a model is
    asked (`acceptance-baseline-failing`); under `demonstration` it is exactly
    what the slot expects.
    """
    from mcgyvr.contract import loads
    from mcgyvr.gate.acceptance import Acceptance
    from mcgyvr.sandbox.tempdir import TempDirSandbox

    contract = loads(docgen.EXAMPLES["code"])
    assert contract.demonstration, "the example's fail-first test is a demonstration"
    repo = _stub_repo(tmp_path)
    with TempDirSandbox(repo) as sandbox:
        issue = Acceptance(
            sandbox,
            contract.acceptance_commands,
            demonstrations=contract.demonstration_commands,
        ).precondition()
    assert issue is None, issue


def test_a_fail_first_test_under_acceptance_is_refused_with_the_slot_to_use(
    tmp_path: Path,
) -> None:
    """The shape the example used to have is refused, and told where it goes."""
    from mcgyvr.contract import loads
    from mcgyvr.gate.acceptance import Acceptance
    from mcgyvr.sandbox.tempdir import TempDirSandbox

    contract = loads(docgen.EXAMPLES["code"])
    commands = contract.acceptance_commands + contract.demonstration_commands
    repo = _stub_repo(tmp_path)
    with TempDirSandbox(repo) as sandbox:
        issue = Acceptance(sandbox, commands).precondition()
    assert issue is not None
    assert issue.reason == "acceptance-baseline-failing"
    assert "`demonstration`" in issue.message, issue.message
