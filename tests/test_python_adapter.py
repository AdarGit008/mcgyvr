"""The Python adapter is the reference implementation of the gate's #35 contract.

The load-bearing property under test is attribution: a hazard, a lint warning
or a formatting nit that the worker did not introduce must never fail the
change. Every check here is paired — the same defect on an added line fails,
on a pre-existing line does not.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from mcgyvr.gate.adapter import ToolFailedError, ToolUnavailableError
from mcgyvr.gate.adapters import PythonAdapter
from mcgyvr.gate.changeset import FileChange

ADAPTER = PythonAdapter()


def change(path: str, added: set[int]) -> FileChange:
    return FileChange(
        path=path,
        status="A",
        added_lines=frozenset(added),
        is_binary=False,
    )


def write(repo: Path, path: str, text: str) -> None:
    dest = repo / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def test_owns_python_files_only() -> None:
    assert ADAPTER.owns("src/app.py")
    assert ADAPTER.owns("stubs/app.pyi")
    assert not ADAPTER.owns("src/app.js")
    assert not ADAPTER.owns("README.md")


def test_syntax_error_is_reported_with_a_line(tmp_path: Path) -> None:
    write(tmp_path, "broken.py", "def f(:\n    pass\n")
    findings = ADAPTER.check_syntax(change("broken.py", {1}), tmp_path)
    assert len(findings) == 1
    assert findings[0].check == "syntax"
    assert findings[0].line == 1


def test_clean_file_passes_syntax(tmp_path: Path) -> None:
    write(tmp_path, "ok.py", "def f() -> int:\n    return 1\n")
    assert ADAPTER.check_syntax(change("ok.py", {1, 2}), tmp_path) == []


def test_mutable_default_flagged_only_when_added(tmp_path: Path) -> None:
    write(tmp_path, "m.py", "def f(a=[]):\n    return a\n")

    added = ADAPTER.structural_checks(change("m.py", {1}), tmp_path)
    assert [f.code for f in added] == ["MUT-DEFAULT"]

    pre_existing = ADAPTER.structural_checks(change("m.py", {2}), tmp_path)
    assert pre_existing == [], (
        "a hazard on a line the worker didn't add is out of scope"
    )


def test_bare_except_flagged_when_added(tmp_path: Path) -> None:
    write(tmp_path, "e.py", "try:\n    x = 1\nexcept:\n    pass\n")
    findings = ADAPTER.structural_checks(change("e.py", {3}), tmp_path)
    assert [f.code for f in findings] == ["BARE-EXCEPT"]


def test_wildcard_import_flagged_when_added(tmp_path: Path) -> None:
    write(tmp_path, "w.py", "from os import *\n")
    findings = ADAPTER.structural_checks(change("w.py", {1}), tmp_path)
    assert [f.code for f in findings] == ["WILDCARD-IMPORT"]


def test_dict_and_set_defaults_are_hazards(tmp_path: Path) -> None:
    write(tmp_path, "d.py", "def f(a={}, b=set()):\n    return a, b\n")
    findings = ADAPTER.structural_checks(change("d.py", {1}), tmp_path)
    assert len(findings) == 2


def test_structural_checks_are_silent_on_syntax_error(tmp_path: Path) -> None:
    write(tmp_path, "b.py", "def (:\n")
    assert ADAPTER.structural_checks(change("b.py", {1}), tmp_path) == []


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
def test_lint_attributes_to_added_lines(tmp_path: Path) -> None:
    # An unused import on line 1 (F401); a clean function on lines 3-4.
    write(tmp_path, "u.py", "import os\n\ndef f() -> int:\n    return 1\n")

    flagged = ADAPTER.lint([change("u.py", {1})], tmp_path)
    assert any(f.code == "F401" and f.line == 1 for f in flagged)

    not_flagged = ADAPTER.lint([change("u.py", {3, 4})], tmp_path)
    assert not_flagged == [], "a pre-existing lint issue is not the worker's"


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
def test_format_flags_only_reflowed_added_lines(tmp_path: Path) -> None:
    write(tmp_path, "f.py", "x=1\ny = 2\n")  # line 1 needs reformatting

    on_added = ADAPTER.format_check([change("f.py", {1})], tmp_path)
    assert [f.check for f in on_added] == ["format"]
    assert on_added[0].line == 1

    off_added = ADAPTER.format_check([change("f.py", {2})], tmp_path)
    assert off_added == [], "formatter reflowing a pre-existing line is not a failure"


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
def test_well_formatted_file_passes(tmp_path: Path) -> None:
    write(tmp_path, "g.py", "x = 1\ny = 2\n")
    assert ADAPTER.format_check([change("g.py", {1, 2})], tmp_path) == []


def test_lint_raises_when_tool_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing tool is an environment fault named by tool, not a rejection."""
    write(tmp_path, "a.py", "x = 1\n")
    monkeypatch.setattr("mcgyvr.gate.adapter.shutil.which", lambda _: None)
    with pytest.raises(ToolUnavailableError) as excinfo:
        ADAPTER.lint([change("a.py", {1})], tmp_path)
    assert excinfo.value.tool == "ruff"


def test_lint_of_no_owned_files_is_empty_and_needs_no_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mcgyvr.gate.adapter.shutil.which", lambda _: None)
    assert ADAPTER.lint([change("README.md", {1})], tmp_path) == []


# --- a ruff that cannot run (#261) ---------------------------------------
#
# Nothing here is faked. ruff is really invoked, really fails, and really
# writes the empty stdout that used to score as a clean pass — which is the
# only way to know the fix is keyed on what the tool actually does. The lever
# is a `pyproject.toml` ruff cannot parse, because that is one of the three
# incidents this project has already had, not a hypothetical.

_UNPARSEABLE_CONFIG = "this is not toml at all [[[\n"


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
def test_a_ruff_that_cannot_start_is_a_fault_not_a_clean_lint(tmp_path: Path) -> None:
    write(tmp_path, "pyproject.toml", _UNPARSEABLE_CONFIG)
    # an unused import: a real finding, if the linter ran
    write(tmp_path, "a.py", "import os\n")
    with pytest.raises(ToolFailedError) as excinfo:
        ADAPTER.lint([change("a.py", {1})], tmp_path)
    assert excinfo.value.tool == "ruff"
    assert excinfo.value.exit_code == 2
    assert excinfo.value.detail, "the operator is told what to fix, in ruff's own words"


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
def test_a_ruff_that_cannot_start_is_a_fault_in_the_format_rung_too(
    tmp_path: Path,
) -> None:
    write(tmp_path, "pyproject.toml", _UNPARSEABLE_CONFIG)
    write(tmp_path, "a.py", "x   =    1\n")  # would reflow, if the formatter ran
    with pytest.raises(ToolFailedError) as excinfo:
        ADAPTER.format_check([change("a.py", {1})], tmp_path)
    assert excinfo.value.tool == "ruff"


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
def test_the_same_file_is_rejected_when_ruff_can_start(tmp_path: Path) -> None:
    """The control: without the broken config, the rung finds what it was blind to."""
    write(tmp_path, "a.py", "import os\n")
    assert [f.code for f in ADAPTER.lint([change("a.py", {1})], tmp_path)] == ["F401"]


def test_locate_test_command_by_convention(tmp_path: Path) -> None:
    assert ADAPTER.locate_test_command(tmp_path) is None
    (tmp_path / "tests").mkdir()
    assert ADAPTER.locate_test_command(tmp_path) == ["pytest"]


def test_locate_test_command_by_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    assert ADAPTER.locate_test_command(tmp_path) == ["pytest"]


def test_owned_drops_deletions_and_binaries() -> None:
    changes = [
        change("keep.py", {1}),
        FileChange("gone.py", "D", frozenset(), False),
        FileChange("blob.py", "M", frozenset(), True),
        change("skip.md", {1}),
    ]
    owned = ADAPTER.owned(changes)
    assert [c.path for c in owned] == ["keep.py"]


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
def test_a_colour_forcing_shell_cannot_silence_the_format_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`FORCE_COLOR` in the developer's shell must not turn a gate off.

    Every adapter reads its tool's output as structured text — this one reads a
    unified diff by its leading `-` and `+`. A colourising tool writes ANSI
    escapes ahead of exactly those characters, so the finding is not
    mis-parsed into a different finding: it disappears. A gate that stops
    reporting because of an environment variable, while still exiting cleanly,
    is the one failure mode a gate must not have.
    """
    monkeypatch.setenv("FORCE_COLOR", "3")
    write(tmp_path, "f.py", "x=1\ny = 2\n")

    findings = ADAPTER.format_check([change("f.py", {1})], tmp_path)

    assert [f.check for f in findings] == ["format"], (
        "the reflowed line is still reported when the shell forces colour"
    )
