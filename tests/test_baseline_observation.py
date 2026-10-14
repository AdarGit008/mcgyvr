"""The baseline-observation locator: read the declaration, run once, and
derive `demonstration` / `acceptance` from the red/green split instead of a
model-invented command.

The locator answers one question the decomposer must not let a model answer:
*how does this repository run its tests, and which of those tests are red at
baseline?* A model can name a command it has never run; the repository's own
declaration, run once, can only name what is there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.orchestrator.baseline import (
    BaselineObservation,
    locate_baseline,
    locate_runner,
)
from mcgyvr.orchestrator.decompose import Proposal, RecordedProposer, decompose
from mcgyvr.orchestrator.index import build_index
from tests.livejournal import git


def _pytest_repo(tmp_path: Path) -> Path:
    """A repo declaring pytest in `[project.optional-dependencies].dev` with one
    failing test and one passing test at baseline."""
    root = tmp_path / "demo"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "demo"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.12"\n'
        "\n"
        "[project.optional-dependencies]\n"
        'dev = ["pytest>=8"]\n',
        encoding="utf-8",
    )
    (root / "demo.py").write_text(
        "def value() -> int:\n    return 0\n", encoding="utf-8"
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_demo.py").write_text(
        "def test_failing() -> None:\n"
        "    assert False\n"
        "\n"
        "\n"
        "def test_passing() -> None:\n"
        "    assert True\n",
        encoding="utf-8",
    )
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return root


def _declining_repo(tmp_path: Path) -> Path:
    """A repo with no test-runner declaration at all."""
    root = tmp_path / "plain"
    root.mkdir()
    (root / "demo.py").write_text(
        "def value() -> int:\n    return 0\n", encoding="utf-8"
    )
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return root


# --- the locator reads the declaration, then the run ------------------------


def test_the_locator_reads_the_red_green_split_from_the_declared_runner(
    tmp_path: Path,
) -> None:
    observation = locate_baseline(_pytest_repo(tmp_path))

    assert observation is not None
    assert observation.runner == ("pytest",)
    assert observation.red == ("tests/test_demo.py::test_failing",)
    assert observation.green == ("tests/test_demo.py::test_passing",)


def test_the_runner_command_is_the_declared_invocation_not_a_guess(
    tmp_path: Path,
) -> None:
    """`[project.optional-dependencies].dev` is a declaration; no `tests/`
    directory needs to exist for it to be read."""
    root = tmp_path / "declared"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "declared"\n'
        'version = "0.1.0"\n'
        "\n"
        "[project.optional-dependencies]\n"
        'dev = ["pytest>=8"]\n',
        encoding="utf-8",
    )
    (root / "demo.py").write_text(
        "def value() -> int:\n    return 0\n", encoding="utf-8"
    )

    assert locate_runner(root) == ("pytest",)


def test_a_uv_managed_project_prefers_uv_run_pytest(tmp_path: Path) -> None:
    """`[dependency-groups]` is uv's own spelling, so the runner fronts uv."""
    root = tmp_path / "uvmanaged"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        "[project]\n"
        'name = "uvmanaged"\n'
        'version = "0.1.0"\n'
        "\n"
        "[dependency-groups]\n"
        'dev = ["pytest>=8"]\n',
        encoding="utf-8",
    )

    assert locate_runner(root) == ("uv", "run", "pytest")


def test_a_repo_without_a_runner_declaration_declines_cleanly(tmp_path: Path) -> None:
    assert locate_baseline(_declining_repo(tmp_path)) is None


@pytest.mark.parametrize(
    ("manifest", "expected"),
    [
        (
            "package.json",
            '{"scripts": {"test": "jest"}}\n',
        ),
        (
            "Cargo.toml",
            '[package]\nname = "demo"\nversion = "0.1.0"\n',
        ),
        (
            "go.mod",
            "module demo\n\ngo 1.22\n",
        ),
    ],
)
def test_the_other_languages_are_detected_from_their_declaration(
    tmp_path: Path, manifest: str, expected: str
) -> None:
    root = tmp_path / "other"
    root.mkdir()
    (root / manifest).write_text(expected, encoding="utf-8")

    if manifest == "package.json":
        assert locate_runner(root) == ("npm", "test")
    elif manifest == "Cargo.toml":
        assert locate_runner(root) == ("cargo", "test")
    else:
        assert locate_runner(root) == ("go", "test", "./...")


# --- the decomposer turns the run into demonstration / acceptance -----------


def test_decompose_derives_demonstration_and_acceptance_from_the_run(
    tmp_path: Path,
) -> None:
    index = build_index(_pytest_repo(tmp_path))
    proposal = Proposal(
        task_type="code",
        max_output_tokens=1024,
        task="demo.value() should return the real value, not a placeholder.",
        target="demo.py",
        stop_conditions=("the intended value is ambiguous",),
    )

    (built,) = decompose(
        index, "fix the value", propose=RecordedProposer((proposal,))
    ).contracts

    assert built.demonstration == ("pytest tests/test_demo.py::test_failing",)
    assert built.acceptance == ("pytest --deselect=tests/test_demo.py::test_failing",)
    assert built.evidence_names == ("gate", "failing_test_first", "tests_pass")


def test_the_proposers_own_commands_flow_through_when_there_is_no_runner(
    tmp_path: Path,
) -> None:
    """No declaration: decompose still works, and nothing overrules the model."""
    index = build_index(_declining_repo(tmp_path))
    proposal = Proposal(
        task_type="code",
        max_output_tokens=1024,
        task="fix the value",
        target="demo.py",
        stop_conditions=("the intent is ambiguous",),
        demonstration=("pytest -q tests/test_demo.py::test_x",),
        acceptance=("pytest -q",),
    )

    (built,) = decompose(
        index, "fix it", propose=RecordedProposer((proposal,))
    ).contracts

    assert built.demonstration == ("pytest -q tests/test_demo.py::test_x",)
    assert built.acceptance == ("pytest -q",)


def test_a_proposal_declaring_its_own_commands_is_never_overruled(
    tmp_path: Path,
) -> None:
    index = build_index(_pytest_repo(tmp_path))
    proposal = Proposal(
        task_type="code",
        max_output_tokens=1024,
        task="fix the value",
        target="demo.py",
        stop_conditions=("the intent is ambiguous",),
        demonstration=("python -m pytest tests/test_demo.py::test_failing",),
        acceptance=("python -m pytest -q",),
    )

    (built,) = decompose(
        index, "fix it", propose=RecordedProposer((proposal,))
    ).contracts

    assert built.demonstration == ("python -m pytest tests/test_demo.py::test_failing",)
    assert built.acceptance == ("python -m pytest -q",)


def test_the_observation_is_handed_to_the_proposer(tmp_path: Path) -> None:
    index = build_index(_pytest_repo(tmp_path))
    proposer = RecordedProposer(
        (
            Proposal(
                task_type="code",
                max_output_tokens=1024,
                task="fix the value",
                target="demo.py",
                stop_conditions=("the intent is ambiguous",),
            ),
        )
    )

    decompose(index, "fix it", propose=proposer)

    (evidence,) = proposer.seen
    assert evidence.baseline is not None
    assert isinstance(evidence.baseline, BaselineObservation)
    assert evidence.baseline.red == ("tests/test_demo.py::test_failing",)
