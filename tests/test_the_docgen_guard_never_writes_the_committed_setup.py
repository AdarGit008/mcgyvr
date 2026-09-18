"""The docgen guard makes its point without mutating the checkout's SETUP.md.

``tests/test_docgen.py``'s
``test_running_the_docgen_tests_does_not_rewrite_the_committed_documents``
proves that no docgen test regenerates the committed documents in place,
because that would repair, in the working tree, the drift ``make docs-check``
exists to fail on. It proves it with a sentinel comment and an inner pytest
run of up to 600 s.

If that sentinel sat in the tracked file, then for the whole window
``skills/mcgyvr/SETUP.md`` on disk would not be what git has, while
``addopts = "-q -n auto"`` in ``pyproject.toml`` has the rest of the suite
running in other processes. Two of them read that file:

* ``tests/test_the_setup_document_is_rendered_and_drift_checked.py::
  test_setup_markdown_on_disk_is_byte_identical_to_render_setup`` reads
  ``SETUP_PATH`` and compares it to ``docgen.render_setup()``.
* ``tests/test_the_mcgyvr_skill_is_rendered_from_the_schema.py::
  test_docs_check_refuses_a_skill_that_drifted`` calls ``docgen.main`` with
  ``--check`` and no ``--setup-output``, so the document its second pass
  expects to be current is the committed one.

Whether they land inside such a window is a matter of which worker gets which
test. What is asserted here instead is the property, at the one moment it is
decidable: the committed file is read at the point the guard invokes its inner
run, which is the start of the window and the moment a truncating change would
already be on disk. Nothing is raced, and a guard that never reaches an inner
run is not missed silently — it leaves nothing read, and that is asserted
against.

A test must not write the checkout's tracked files.
"""

from __future__ import annotations

import inspect
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import docgen
from tests import test_docgen

#: The tracked document the guard must leave untouched.
SETUP = docgen.REPO_ROOT / "skills" / "mcgyvr" / "SETUP.md"

#: The guard under test, reached through its module so that it is free to
#: change how it plants the sentinel without this file following it.
#: Typed as taking anything, because what fixtures it asks for is its own
#: business.
GUARD: Callable[..., None] = (
    test_docgen.test_running_the_docgen_tests_does_not_rewrite_the_committed_documents
)


def _run_the_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, at_the_inner_run: Any
) -> list[list[str]]:
    """Run the guard, calling ``at_the_inner_run`` where it starts its inner run.

    The inner run is stubbed rather than executed: it is the same suite again,
    up to 600 s of it, and what is being observed is the state of the checkout
    at the moment it is launched, not its verdict. A zero return code and empty
    output are what a clean inner run gives, so the guard's own assertions
    about it still hold and the only thing that can fail is the observation.

    A ``tmp_path`` is passed if the guard asks for a fixture by that name, so
    this file does not have to change with the guard's signature.
    """
    commands: list[list[str]] = []

    def watching(command: list[str], *args: Any, **kwargs: Any) -> Any:
        commands.append(list(command))
        at_the_inner_run()
        return subprocess.CompletedProcess(command, 0, "", "")

    # ``test_docgen`` calls ``subprocess.run`` through the module, so patching
    # the module's own attribute is what its call site sees.
    monkeypatch.setattr(subprocess, "run", watching)
    if "tmp_path" in inspect.signature(GUARD).parameters:
        GUARD(tmp_path=tmp_path)
    else:
        GUARD()
    return commands


def _assert_it_ran_the_docgen_tests(commands: list[list[str]]) -> None:
    """The guard reached its inner run, and the inner run is the one it claims.

    Without this an observation that was never taken — a guard that returns
    before launching anything — would leave every assertion below true of an
    empty list and the file would pass while proving nothing.
    """
    assert commands, (
        "the guard launched no inner run, so there was no moment to read "
        "skills/mcgyvr/SETUP.md at and this proves nothing about what it writes"
    )
    for command in commands:
        assert "pytest" in command, command
        assert any(part.endswith("tests/test_docgen.py") for part in command), command
        assert "--deselect" in command, command


def test_the_committed_setup_is_untouched_when_the_guard_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """What another xdist worker reads while the guard holds its sentinel."""
    committed = SETUP.read_bytes()
    seen: list[bytes] = []

    commands = _run_the_guard(
        monkeypatch, tmp_path, lambda: seen.append(SETUP.read_bytes())
    )

    _assert_it_ran_the_docgen_tests(commands)
    assert seen
    for got in seen:
        assert got == committed, (
            "a worker that read skills/mcgyvr/SETUP.md while the docgen guard "
            f"was running read {len(got)} bytes where the committed file has "
            f"{len(committed)}: the guard wrote the tracked file, so for the "
            "length of its inner run the document on disk is not the one "
            "render_setup() renders"
        )
    assert SETUP.read_bytes() == committed


def test_a_docs_check_that_lands_mid_guard_still_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The second victim, run at the moment it would be running for real.

    ``docgen.main(["--check", ...])`` with no ``--setup-output`` checks the
    committed ``SETUP.md``; the other two kept documents are pointed at current
    renderings under ``tmp_path`` so that this run has nothing else it could
    refuse. Zero, or the committed document is not what the schema renders.
    """
    skill = tmp_path / "SKILL.md"
    skill.write_text(docgen.render_skill(), encoding="utf-8")
    examples = tmp_path / "examples.md"
    examples.write_text(docgen.render_examples(), encoding="utf-8")
    argv = [
        "--check",
        "--output",
        str(tmp_path / "config-reference.md"),
        "--skill-output",
        str(skill),
        "--examples-output",
        str(examples),
    ]
    verdicts: list[int] = []

    commands = _run_the_guard(
        monkeypatch, tmp_path, lambda: verdicts.append(docgen.main(argv))
    )

    _assert_it_ran_the_docgen_tests(commands)
    assert verdicts
    for verdict in verdicts:
        assert verdict == 0, (
            "`docgen --check` refused the committed skills/mcgyvr/SETUP.md "
            "while the docgen guard's inner run was starting: the guard's "
            "sentinel is in the tracked file, and any worker running "
            "test_docs_check_refuses_a_skill_that_drifted in that window "
            "fails on it"
        )
