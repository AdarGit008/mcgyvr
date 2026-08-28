"""The gate's Python reader, over the byte convention the repository chose.

mcgyvr reads and writes file content through ``utf-8``/``surrogateescape`` on
purpose, and documents it at :mod:`mcgyvr.pending`. The 2026-08-29 pressure
test (§3, pattern A) found every *writer* the port added crashing on content
that carries a surrogate escape. The writers have been fixed; one reader had
not been looked at.

:func:`mcgyvr.gate.adapters.python._read` is already written to the convention
— it decodes with ``errors="surrogateescape"``, so a file holding a byte like
``0xFF`` arrives as a string containing ``\\udcff``. What it hands that string
to is ``ast.parse``, and ``compile()`` cannot be handed a surrogate at all: it
raises ``UnicodeEncodeError``, which is not ``SyntaxError`` and so walked
straight out of the adapter, out of :meth:`~mcgyvr.gate.Gate.run`, and into the
caller. The gate crashed instead of judging, upstream of delivery.

So the assertions here are about the *verdict*, not only about the absence of a
traceback. Two of them are load-bearing in opposite directions:

* the file must produce a ``syntax`` finding — a file the parser cannot accept
  is exactly what that rung reports, and it is what stops the file reaching
  lint, ``ruff``, and the sandboxed rungs downstream of it;
* the gate must **not** return an empty list. Swallowing the condition into
  "nothing to say" would let a file no checker ever read pass the gate, which
  is the same defect as the ones this sweep was opened for.

Everything is driven through a real ``ChangeSet`` over a real git repository,
because the question is whether such a file survives *detection* as scannable
text at all: git calls a file binary on a NUL byte, not on invalid UTF-8, so
``0xFF`` alone reaches the adapter as an ordinary text change with attributed
added lines. A hand-built :class:`~mcgyvr.gate.changeset.FileChange` would
assert that without establishing it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mcgyvr.gate.adapters import JavaScriptAdapter, PythonAdapter
from mcgyvr.gate.changeset import ChangeSet, FileChange
from mcgyvr.gate.runner import Gate
from mcgyvr.gate.semantic import STAGING_DIR, SemanticCheck, SemanticReport
from mcgyvr.sandbox.tempdir import TempDirSandbox

# A byte that is not valid UTF-8 anywhere, and is not NUL — so git carries the
# file as text and `_read`'s surrogateescape turns it into `\udcff`.
_UNDECODABLE = b"\xff"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.invalid", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A committed repository whose base holds one boring module."""
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "base.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def _change(repo: Path, name: str) -> FileChange:
    """The detected change for ``name``, as the gate would see it."""
    for change in ChangeSet.detect(repo):
        if change.path == name:
            return change
    raise AssertionError(f"{name} was not detected as changed")


def _write_undecodable_module(repo: Path, name: str = "worker.py") -> FileChange:
    """A worker-added Python file whose second line holds a non-UTF-8 byte."""
    (repo / name).write_bytes(b'MARKER = 1\nLABEL = "a' + _UNDECODABLE + b'b"\n')
    change = _change(repo, name)
    # The premise of every test below: git attributed both lines to the worker
    # and did not write the file off as binary, so the adapter really is asked
    # to read it.
    assert not change.is_binary
    assert change.added_lines == frozenset({1, 2})
    return change


# --- the adapter --------------------------------------------------------


def test_syntax_rung_reports_an_undecodable_byte_instead_of_crashing(
    repo: Path,
) -> None:
    change = _write_undecodable_module(repo)

    findings = PythonAdapter().check_syntax(change, repo)

    assert [f.check for f in findings] == ["syntax"]
    assert findings[0].path == "worker.py"
    # Located, not merely reported. The rung attributes a finding to a line
    # wherever it can know one, and the offending byte's position is known.
    assert findings[0].line == 2
    assert "utf-8" in (findings[0].message or "")


def test_structural_rung_defers_to_the_syntax_rung(repo: Path) -> None:
    """Silent here is right — and only here, because syntax already spoke."""
    change = _write_undecodable_module(repo)

    assert PythonAdapter().structural_checks(change, repo) == []


def test_a_valid_file_is_still_read_and_judged(repo: Path) -> None:
    """The guard must not swallow files that decode perfectly well."""
    (repo / "clean.py").write_bytes(b"VALUE = 2\n")
    (repo / "hazard.py").write_bytes(b"def f(x=[]):\n    return x\n")
    adapter = PythonAdapter()

    assert adapter.check_syntax(_change(repo, "clean.py"), repo) == []
    hazards = adapter.structural_checks(_change(repo, "hazard.py"), repo)
    assert [f.code for f in hazards] == ["MUT-DEFAULT"]


# --- the gate -----------------------------------------------------------


def test_gate_refuses_a_module_holding_an_undecodable_byte(repo: Path) -> None:
    """The whole run, which is where the crash actually escaped to."""
    _write_undecodable_module(repo)

    result = Gate().run(ChangeSet.detect(repo))

    assert not result.accepted
    assert [f.check for f in result.findings] == ["syntax"]
    # Not an environment issue and not an inconclusive rung: the gate reached a
    # verdict about the change, it did not fail to run.
    assert result.environment_issues == ()
    assert result.inconclusive == ()


def test_the_gate_does_not_pass_a_file_it_could_not_parse(repo: Path) -> None:
    """The failure mode this fix must not become.

    Returning ``[]`` from the syntax rung would leave the file in
    ``syntax_clean``, and every downstream rung reads it with the same
    ``surrogateescape`` decoder or hands it to the same tools. Acceptance is
    the property under test, so it is asserted directly rather than inferred
    from the finding list.
    """
    _write_undecodable_module(repo)
    (repo / "fine.py").write_text("OTHER = 3\n", encoding="utf-8")

    result = Gate().run(ChangeSet.detect(repo))

    assert not result.accepted
    assert {f.path for f in result.findings} == {"worker.py"}


# --- the neighbouring readers --------------------------------------------


def test_javascript_adapter_is_unaffected(repo: Path) -> None:
    """The JS path parses *bytes*, so it never decodes and never crashes.

    Asserted rather than assumed: it is the reason ``javascript.py`` is not
    part of this fix, and a future move to text parsing there would reopen the
    same hole silently.
    """
    (repo / "worker.js").write_bytes(b'const label = "a' + _UNDECODABLE + b'b";\n')
    change = _change(repo, "worker.js")
    adapter = JavaScriptAdapter()

    assert adapter.check_syntax(change, repo) == []
    assert adapter.structural_checks(change, repo) == []


def test_type_checker_locator_reads_an_undecodable_manifest_as_no_declaration(
    tmp_path: Path,
) -> None:
    """The same except-clause hole, one function over.

    :func:`~mcgyvr.gate.adapters.python._has_toml_table` hands ``pyproject.toml``
    to ``tomllib``, which decodes strictly, and caught ``TOMLDecodeError`` —
    which a ``UnicodeDecodeError`` is not. Its own docstring is the specification
    it broke: "Nothing here raises: a malformed file is the target's business,
    and the honest answer to *does it declare a checker* is no."

    Worth its own test because the blast radius is not the gate but the
    *decomposer*: :func:`mcgyvr.orchestrator.decompose._acceptance_for` calls
    this to fill a ``type_check`` contract in, and its whole vocabulary is a
    command or a ``Refusal``. One byte in a manifest took the plan down.
    """
    (tmp_path / "pyproject.toml").write_bytes(
        b'[tool.mypy]\nstrict = true\nname = "' + _UNDECODABLE + b'"\n'
    )

    assert PythonAdapter().locate_type_check_command(tmp_path) is None


def test_type_checker_locator_still_reads_a_decodable_manifest(
    tmp_path: Path,
) -> None:
    """The other direction: the guard must not turn every manifest into silence."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.mypy]\nstrict = true\n", encoding="utf-8"
    )

    assert PythonAdapter().locate_type_check_command(tmp_path) == ["mypy"]


def test_js_test_command_locator_reads_an_undecodable_manifest_as_no_declaration(
    tmp_path: Path,
) -> None:
    """The fourth site, and the same except clause missing the same family.

    :meth:`~mcgyvr.gate.adapters.JavaScriptAdapter.locate_test_command` reads
    ``package.json`` strictly and caught ``(OSError, json.JSONDecodeError)`` —
    and ``UnicodeDecodeError`` is a ``ValueError``, so a manifest with one
    non-UTF-8 byte raised out of a locator whose only two answers are a command
    and ``None``. Exactly the shape of the ``tomllib`` hole one adapter over,
    which is why it is fixed the same way and asserted the same way.
    """
    (tmp_path / "package.json").write_bytes(
        b'{"scripts": {"test": "vitest ' + _UNDECODABLE + b'"}}'
    )

    assert JavaScriptAdapter().locate_test_command(tmp_path) is None


def test_js_test_command_locator_still_reads_a_decodable_manifest(
    tmp_path: Path,
) -> None:
    """The other direction: a real manifest must still locate a real command."""
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "vitest"}}', encoding="utf-8"
    )

    assert JavaScriptAdapter().locate_test_command(tmp_path) == ["npm", "test"]


def test_semantic_rung_reports_one_unreadable_file_without_losing_the_others(
    repo: Path,
) -> None:
    """A driver that raises takes the whole job down, not just the bad file.

    :func:`mcgyvr.gate.semantic_driver.resolve_file` documents itself as never
    raising, and returns a per-file ``error`` entry so one unresolvable file
    costs only itself. It opens with a *strict* decoder — correctly, since a
    surrogate is precisely what its own ``ast.parse`` cannot take — but caught
    only ``OSError``, and ``UnicodeDecodeError`` is a ``ValueError``. One
    latin-1 byte anywhere in the change therefore killed the run for every
    other file in it.

    Driven through the real rung in a real sandbox, because the driver is never
    imported on the host (ADR-0010) and the host has no ``ghostcall``.
    """
    with TempDirSandbox(repo) as sandbox:
        (sandbox.workspace / "bad.py").write_bytes(
            b"import json\nLABEL = " + _UNDECODABLE + b"\n"
        )
        (sandbox.workspace / "good.py").write_text(
            "import json\nVALUE = json.dumps({})\n", encoding="utf-8"
        )
        changeset = ChangeSet.detect(sandbox.workspace, sandbox.base_changeset_ref())
        report: SemanticReport = SemanticCheck(sandbox).run(changeset)
        assert not (sandbox.workspace / STAGING_DIR).exists()

    # The unreadable file is named, once, as its own problem…
    unreadable = [i for i in report.environment_issues if "bad.py" in i]
    assert len(unreadable) == 1
    assert "not resolved" in unreadable[0]
    # …and the file beside it was still resolved, which is what a per-file
    # error buys and what a driver traceback would have thrown away.
    assert report.resolved > 0
    assert not any("good.py" in issue for issue in report.environment_issues)
