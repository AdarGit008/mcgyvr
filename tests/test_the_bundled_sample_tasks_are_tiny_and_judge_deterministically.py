"""The bundled sample tasks ship with the package, are tiny, and judge the same way twice.

Plan section 8.2 (P7b): coding samples one shipped mini contract -- a
one-function bug fix in a throwaway repository bundled with the product --
green when the deterministic gate passes on any rung; agent samples one
shipped grounded contract, green when the reply is grounded and passes the
safety check. Chat is judged by a completion per unit and ships no contract.

Promises, read from the package's own data (``importlib.resources``), so a
wheel install has what a checkout has:

* each bundle is a contract the product loads, of its use case's task type,
  and a coding contract declares the reply cap its type derives;
* materialized, its repository is a git repository with one commit holding
  exactly the bundle's files, and the contract names a target in it;
* the coding demonstration fails on the file as shipped and passes on the
  reference fix, the same way on a second run; the agent's reference reply is
  grounded in its source and an uncited one is not.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest

USE_CASES = ("coding", "agent")


def _bundle(use_case: str):  # type: ignore[no-untyped-def]
    from mcgyvr.fleet import bundled

    found = bundled.bundle(use_case)
    assert found is not None, use_case
    return found


def test_the_bundles_are_package_data() -> None:
    from importlib import resources

    for use_case in USE_CASES:
        assert (resources.files("mcgyvr") / "samples" / f"{use_case}.yaml").is_file()


@pytest.mark.parametrize("use_case", USE_CASES)
def test_each_bundle_is_a_contract_of_its_use_case(use_case: str) -> None:
    from mcgyvr import contract

    found = _bundle(use_case)
    loaded = contract.loads(found.contract_text)
    assert found.use_case == use_case
    assert contract.task_type(loaded.task_type).use_case == use_case
    assert loaded.target in {**found.files, **found.reference}
    if use_case == "coding":
        assert loaded.max_output_tokens_declared
        assert loaded.max_output_tokens == contract.output_cap(loaded.task_type)


@pytest.mark.parametrize("use_case", ["chat", "media-gen"])
def test_a_use_case_judged_without_a_contract_ships_none(use_case: str) -> None:
    from mcgyvr.fleet import bundled

    assert bundled.bundle(use_case) is None


@pytest.mark.parametrize("use_case", USE_CASES)
def test_a_materialized_bundle_is_a_repository_of_exactly_its_files(
    tmp_path: Path, use_case: str
) -> None:
    from mcgyvr.fleet import bundled

    found = _bundle(use_case)
    made = bundled.materialize(found, tmp_path / use_case)

    tracked = subprocess.run(
        ["git", "-C", str(made.repo), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert sorted(tracked) == sorted(found.files)
    assert made.contract.read_text(encoding="utf-8") == found.contract_text
    assert not made.contract.is_relative_to(made.repo), (
        "the contract is not a file of the repository it changes"
    )


def _demonstrate(repo: Path, command: str) -> int:
    argv = shlex.split(command)
    if argv[0] == "python3":
        argv[0] = sys.executable
    return subprocess.run(argv, cwd=repo, capture_output=True, check=False).returncode


def test_the_coding_demonstration_fails_as_shipped_and_passes_on_the_fix(
    tmp_path: Path,
) -> None:
    from mcgyvr import contract
    from mcgyvr.fleet import bundled

    found = _bundle("coding")
    (command,) = contract.loads(found.contract_text).demonstration
    for attempt in range(2):
        made = bundled.materialize(found, tmp_path / f"run-{attempt}")
        assert _demonstrate(made.repo, command) != 0, "the bug is there as shipped"
        for name, text in found.reference.items():
            (made.repo / name).write_text(text, encoding="utf-8")
        assert _demonstrate(made.repo, command) == 0, "the fix passes"


def test_the_agent_reference_is_grounded_and_an_uncited_reply_is_not(
    tmp_path: Path,
) -> None:
    from mcgyvr import contract
    from mcgyvr.gate.output import grounded

    found = _bundle("agent")
    loaded = contract.loads(found.contract_text)
    assert set(loaded.sources) <= set(found.files)
    (target,) = found.reference
    answer = tmp_path / target
    answer.write_text(found.reference[target], encoding="utf-8")
    assert grounded(answer, loaded.sources) == []
    assert grounded(answer, loaded.sources) == []

    answer.write_text("The sky was green. It was Tuesday.\n", encoding="utf-8")
    assert len(grounded(answer, loaded.sources)) == 2
