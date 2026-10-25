"""A test module that cannot be collected names the missing symbol, as data.

pytest's report files a collection error under the module, with the
exception it raised. The interpreter words a NameError, an ImportError, a
ModuleNotFoundError and an AttributeError the same way every time, with the
missing name quoted in a fixed place, so that name is read as data —
:func:`mcgyvr.gate.junit.symbol_of` matches the whole exception line against
those fixed wordings and nothing else. Any other exception, or a sentence that
only looks like one of them, gives no symbol: a name is never picked out of
free text.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mcgyvr.gate.acceptance import Acceptance
from mcgyvr.gate.junit import parse, symbol_of
from mcgyvr.gate.runner import GateResult
from mcgyvr.notes import FailureNotes
from mcgyvr.sandbox.tempdir import TempDirSandbox
from tests._helpers import git


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {"pyproject.toml": "[tool.pytest.ini_options]\n", **files}
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(
        repo,
        "-c",
        "user.email=t@t.invalid",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "-m",
        "base",
    )
    return repo


def test_each_uncollectable_module_is_a_note_naming_what_is_missing(
    tmp_path: Path,
) -> None:
    repo = _repo(
        tmp_path,
        {
            "tests/test_imports.py": "from os import not_a_thing\n\n\n"
            "def test_x():\n    pass\n",
            "tests/test_names.py": "undefined_here\n\n\ndef test_x():\n    pass\n",
            "tests/test_modules.py": "import no_such_module_q\n\n\n"
            "def test_x():\n    pass\n",
        },
    )
    command = (sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider")
    with TempDirSandbox(repo) as sandbox:
        report = Acceptance(sandbox, (command,)).run()

    record = FailureNotes.of_gate(
        GateResult(findings=report.findings), rung="r", family="local", attempt=1
    )
    assert record is not None

    by_path = {note.path: note for note in record.notes}
    assert {path: note.symbol for path, note in by_path.items()} == {
        "tests/test_imports.py": "not_a_thing",
        "tests/test_names.py": "undefined_here",
        "tests/test_modules.py": "no_such_module_q",
    }
    for note in record.notes:
        # A module is not a test, and a collection error has no line of its own.
        assert (note.code, note.test_id, note.line) == ("collection-error", None, None)
        assert note.exit_code == 2
    assert "ModuleNotFoundError: No module named 'no_such_module_q'" in (
        by_path["tests/test_modules.py"].message
    )


@pytest.mark.parametrize(
    ("line", "symbol"),
    [
        ("NameError: name 'shelf_rows' is not defined", "shelf_rows"),
        ("NameError: name 'rows' is not defined. Did you mean: 'row'?", "rows"),
        ("ModuleNotFoundError: No module named 'pkg.sub'", "pkg.sub"),
        (
            "ImportError: cannot import name 'fam' from 'stock.sku' (stock/sku.py)",
            "fam",
        ),
        ("ImportError: cannot import name 'fam' from 'stock.sku'", "fam"),
        ("AttributeError: module 'stock.sku' has no attribute 'fam'", "fam"),
        ("AttributeError: 'Shelf' object has no attribute 'rows'", "rows"),
        (
            "AttributeError: type object 'Shelf' has no attribute 'rows'. "
            "Did you mean: 'row'?",
            "rows",
        ),
        ("AssertionError: assert 3 == 4", None),
        ("RuntimeError: name 'x' is not defined", None),
        ("ValueError: No module named 'x'", None),
        ("NameError: the name 'x' is not defined here, I think", None),
        ("assert None == 'sku_family'", None),
        ("", None),
    ],
)
def test_only_the_fixed_wordings_give_a_symbol(line: str, symbol: str | None) -> None:
    assert symbol_of(line) == symbol


def test_a_report_written_to_break_the_reader_names_no_line() -> None:
    """The report is written by code the change controls: a line that is not
    a plain number is no line, and never stops the gate."""
    case = (
        '<testsuite><testcase classname="t" name="test_a" file="t.py" '
        'line="{line}"><failure message="boom">E   boom</failure></testcase>'
        "</testsuite>"
    )
    for line in ("²", "9" * 5000, "-1", "x"):
        (failing,) = parse(case.format(line=line))
        assert failing.line is None
    assert parse('<!DOCTYPE x [<!ENTITY a "b">]><testsuite/>') == ()
    assert parse("not xml") == ()
