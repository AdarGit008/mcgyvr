"""The JS/TS adapter is the second implementation of the gate's #35 contract.

It must reach feature parity with the Python adapter on the shared check set
while sharing none of its tools, so these mirror ``test_python_adapter``'s
shape — every attribution check is paired: the same defect on an added line
fails, on a pre-existing line does not, which is the gate's core promise.

Syntax and structural checks use tree-sitter and run for real. Lint and format
shell out to eslint and prettier, which are not present where this suite runs;
rather than skip the load-bearing attribution logic, the tool calls are faked
so the JSON parsing, the file resolution, and the added-line filtering are all
exercised deterministically, everywhere.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

import pytest

from mcgyvr.gate.adapter import ToolFailedError, ToolUnavailableError
from mcgyvr.gate.adapters import JavaScriptAdapter
from mcgyvr.gate.changeset import ChangeSet, FileChange
from mcgyvr.gate.runner import Gate

ADAPTER = JavaScriptAdapter()


def change(path: str, added: set[int]) -> FileChange:
    return FileChange(
        path=path, status="A", added_lines=frozenset(added), is_binary=False
    )


def write(repo: Path, path: str, text: str) -> None:
    dest = repo / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


class _Proc(NamedTuple):
    returncode: int
    stdout: str
    stderr: str = ""


# --- ownership -----------------------------------------------------------


def test_owns_the_js_ts_family_only() -> None:
    for path in ("a.js", "a.jsx", "a.mjs", "a.cjs", "a.ts", "a.tsx", "a.mts"):
        assert ADAPTER.owns(path), path
    assert not ADAPTER.owns("a.py")
    assert not ADAPTER.owns("README.md")


# --- syntax (tree-sitter, real) ------------------------------------------


def test_syntax_error_is_reported_with_a_line(tmp_path: Path) -> None:
    write(tmp_path, "bad.js", "function f( {\n  return 1;\n")
    findings = ADAPTER.check_syntax(change("bad.js", {1}), tmp_path)
    assert len(findings) == 1
    assert findings[0].check == "syntax"
    assert findings[0].line == 1


def test_clean_file_passes_syntax_across_variants(tmp_path: Path) -> None:
    write(tmp_path, "ok.ts", "const x: number = 1;\nexport const y = x + 1;\n")
    write(tmp_path, "ok.tsx", "export const El = () => <div>{1}</div>;\n")
    assert ADAPTER.check_syntax(change("ok.ts", {1, 2}), tmp_path) == []
    assert ADAPTER.check_syntax(change("ok.tsx", {1}), tmp_path) == []


# --- structural hazards (tree-sitter, real) ------------------------------


def test_var_flagged_only_when_added(tmp_path: Path) -> None:
    write(tmp_path, "v.ts", "var x = 1;\nconst y = 2;\n")

    added = ADAPTER.structural_checks(change("v.ts", {1}), tmp_path)
    assert [f.code for f in added] == ["NO-VAR"]

    pre_existing = ADAPTER.structural_checks(change("v.ts", {2}), tmp_path)
    assert pre_existing == [], "a hazard the worker didn't add is out of scope"


def test_loose_equality_flagged_but_strict_is_clean(tmp_path: Path) -> None:
    write(tmp_path, "e.js", "const a = x == 1;\nconst b = y === 2;\n")

    loose = ADAPTER.structural_checks(change("e.js", {1}), tmp_path)
    assert [f.code for f in loose] == ["LOOSE-EQ"]

    strict = ADAPTER.structural_checks(change("e.js", {2}), tmp_path)
    assert strict == [], "=== is not a hazard"


def test_debugger_statement_flagged_when_added(tmp_path: Path) -> None:
    write(tmp_path, "d.js", "function f() {\n  debugger;\n}\n")
    findings = ADAPTER.structural_checks(change("d.js", {2}), tmp_path)
    assert [f.code for f in findings] == ["DEBUGGER"]


def test_structural_checks_are_silent_on_syntax_error(tmp_path: Path) -> None:
    write(tmp_path, "b.ts", "function ( {\n")
    assert ADAPTER.structural_checks(change("b.ts", {1}), tmp_path) == []


# --- lint (eslint, faked) ------------------------------------------------


def _fake_eslint(
    monkeypatch: pytest.MonkeyPatch,
    repo: Path,
    path: str,
    messages: list[dict[str, object]],
) -> None:
    """Make the adapter's eslint call return one result for ``path``."""
    monkeypatch.setattr(
        "mcgyvr.gate.adapters.javascript.require_tool", lambda tool: tool
    )
    payload = [{"filePath": str(repo / path), "messages": messages}]

    def run(argv, *a, **k):  # type: ignore[no-untyped-def]
        return _Proc(1, json.dumps(payload))

    monkeypatch.setattr("mcgyvr.gate.adapters.javascript.subprocess.run", run)


def test_lint_attributes_errors_to_added_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, "u.ts", "const os = 1;\n\nexport const f = () => 2;\n")
    _fake_eslint(
        monkeypatch,
        tmp_path,
        "u.ts",
        [
            {"ruleId": "no-unused-vars", "severity": 2, "message": "unused", "line": 1},
            {"ruleId": "no-console", "severity": 1, "message": "warn", "line": 1},
        ],
    )

    flagged = ADAPTER.lint([change("u.ts", {1})], tmp_path)
    assert [(f.code, f.line) for f in flagged] == [("no-unused-vars", 1)]

    not_flagged = ADAPTER.lint([change("u.ts", {3})], tmp_path)
    assert not_flagged == [], "a lint error off the worker's added lines is not theirs"


def test_lint_warnings_do_not_reject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, "w.ts", "export const x = 1;\n")
    _fake_eslint(
        monkeypatch,
        tmp_path,
        "w.ts",
        [{"ruleId": "no-console", "severity": 1, "message": "warn", "line": 1}],
    )
    assert ADAPTER.lint([change("w.ts", {1})], tmp_path) == []


def test_a_fatal_eslint_is_a_fault_not_an_empty_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fatal eslint run says nothing at all — and nothing is not clean (#261).

    Measured against eslint 9 on 2026-08-16: no config, an unloadable config
    and an internal error all exit **2 with an empty stdout**. That is why the
    stdout here is empty and why the exit code is what this asserts on — the
    version of this test that fed it a non-JSON *string* was testing a shape
    eslint does not produce, while the shape it does produce parsed cleanly as
    zero findings and passed the change.
    """
    write(tmp_path, "a.ts", "export const x = 1;\n")
    monkeypatch.setattr(
        "mcgyvr.gate.adapters.javascript.require_tool", lambda tool: tool
    )
    monkeypatch.setattr(
        "mcgyvr.gate.adapters.javascript.subprocess.run",
        lambda *a, **k: _Proc(2, "", "Error: no eslint config found"),
    )
    with pytest.raises(ToolFailedError) as excinfo:
        ADAPTER.lint([change("a.ts", {1})], tmp_path)
    assert excinfo.value.tool == "eslint"
    assert excinfo.value.exit_code == 2
    assert "no eslint config found" in excinfo.value.detail


def test_eslint_reporting_problems_is_not_a_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 1 is eslint doing its job. Only a code outside (0, 1) is a fault."""
    write(tmp_path, "u.ts", "const os = 1;\n")
    _fake_eslint(
        monkeypatch,
        tmp_path,
        "u.ts",
        [{"ruleId": "no-unused-vars", "severity": 2, "message": "unused", "line": 1}],
    )
    assert [f.code for f in ADAPTER.lint([change("u.ts", {1})], tmp_path)] == [
        "no-unused-vars"
    ]


def test_lint_raises_when_tool_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, "a.ts", "export const x = 1;\n")
    monkeypatch.setattr("mcgyvr.gate.adapter.shutil.which", lambda _: None)
    with pytest.raises(ToolUnavailableError) as excinfo:
        ADAPTER.lint([change("a.ts", {1})], tmp_path)
    assert excinfo.value.tool == "eslint"


def test_lint_of_no_owned_files_needs_no_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mcgyvr.gate.adapter.shutil.which", lambda _: None)
    assert ADAPTER.lint([change("README.md", {1})], tmp_path) == []


# --- format (prettier, faked) --------------------------------------------


def _fake_prettier(
    monkeypatch: pytest.MonkeyPatch,
    differing: list[str],
    formatted: dict[str, str],
) -> None:
    """Fake the two prettier calls: list-different, then per-file formatted output."""
    monkeypatch.setattr(
        "mcgyvr.gate.adapters.javascript.require_tool", lambda tool: tool
    )

    def run(argv, *a, **k):  # type: ignore[no-untyped-def]
        if "--list-different" in argv:
            return _Proc(1 if differing else 0, "\n".join(differing))
        path = argv[-1]  # [prettier, "--", path]
        return _Proc(0, formatted.get(path, ""))

    monkeypatch.setattr("mcgyvr.gate.adapters.javascript.subprocess.run", run)


def test_format_flags_only_reflowed_added_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, "f.ts", "const a=1;\nconst b = 2;\n")  # line 1 needs spaces
    _fake_prettier(monkeypatch, ["f.ts"], {"f.ts": "const a = 1;\nconst b = 2;\n"})

    on_added = ADAPTER.format_check([change("f.ts", {1})], tmp_path)
    assert [f.check for f in on_added] == ["format"]
    assert on_added[0].line == 1

    off_added = ADAPTER.format_check([change("f.ts", {2})], tmp_path)
    assert off_added == [], "reflowing a pre-existing line is not the worker's failure"


def test_well_formatted_file_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, "g.ts", "const a = 1;\n")
    _fake_prettier(monkeypatch, [], {})  # prettier finds nothing to change
    assert ADAPTER.format_check([change("g.ts", {1})], tmp_path) == []


def test_format_raises_when_tool_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, "f.ts", "const a=1;\n")
    monkeypatch.setattr("mcgyvr.gate.adapter.shutil.which", lambda _: None)
    with pytest.raises(ToolUnavailableError) as excinfo:
        ADAPTER.format_check([change("f.ts", {1})], tmp_path)
    assert excinfo.value.tool == "prettier"


def test_a_fatal_prettier_listing_is_a_fault_not_an_all_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An invalid prettier config exits 2 and lists no file — not "all formatted"."""
    write(tmp_path, "f.ts", "const a=1;\n")
    monkeypatch.setattr(
        "mcgyvr.gate.adapters.javascript.require_tool", lambda tool: tool
    )
    monkeypatch.setattr(
        "mcgyvr.gate.adapters.javascript.subprocess.run",
        lambda *a, **k: _Proc(2, "", "[error] Invalid configuration"),
    )
    with pytest.raises(ToolFailedError) as excinfo:
        ADAPTER.format_check([change("f.ts", {1})], tmp_path)
    assert excinfo.value.tool == "prettier"
    assert excinfo.value.exit_code == 2


def test_a_prettier_that_cannot_print_a_differing_file_is_a_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file has already been reported as differing; a bad exit cannot unsay it."""
    write(tmp_path, "f.ts", "const a=1;\n")
    monkeypatch.setattr(
        "mcgyvr.gate.adapters.javascript.require_tool", lambda tool: tool
    )

    def run(argv, *a, **k):  # type: ignore[no-untyped-def]
        if "--list-different" in argv:
            return _Proc(1, "f.ts")
        return _Proc(2, "", "[error] Cannot format")

    monkeypatch.setattr("mcgyvr.gate.adapters.javascript.subprocess.run", run)
    with pytest.raises(ToolFailedError):
        ADAPTER.format_check([change("f.ts", {1})], tmp_path)


# --- test-command conventions --------------------------------------------


def test_locate_test_command_reads_package_json(tmp_path: Path) -> None:
    assert ADAPTER.locate_test_command(tmp_path) is None  # no package.json
    (tmp_path / "package.json").write_text('{"scripts": {"test": "jest"}}')
    assert ADAPTER.locate_test_command(tmp_path) == ["npm", "test"]


def test_locate_test_command_picks_the_package_manager(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"scripts": {"test": "vitest"}}')
    (tmp_path / "pnpm-lock.yaml").write_text("")
    assert ADAPTER.locate_test_command(tmp_path) == ["pnpm", "test"]


def test_locate_test_command_none_without_a_test_script(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"scripts": {"build": "tsc"}}')
    assert ADAPTER.locate_test_command(tmp_path) is None


def test_locate_test_command_none_on_malformed_manifest(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{not json")
    assert ADAPTER.locate_test_command(tmp_path) is None


# --- shared base behaviour + gate wiring ---------------------------------


def test_owned_drops_deletions_and_binaries() -> None:
    changes = [
        change("keep.ts", {1}),
        FileChange("gone.ts", "D", frozenset(), False),
        FileChange("blob.ts", "M", frozenset(), True),
        change("skip.md", {1}),
    ]
    assert [c.path for c in ADAPTER.owned(changes)] == ["keep.ts"]


def test_gate_checks_js_by_default(tmp_path: Path) -> None:
    """The default gate now carries the JS/TS adapter, so a JS hazard is caught."""
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True
        )

    git("init", "-q")
    git(
        "-c",
        "user.email=t@t.io",
        "-c",
        "user.name=t",
        "commit",
        "--allow-empty",
        "-q",
        "-m",
        "base",
    )
    write(tmp_path, "app.js", "const ok = x === 1;\ndebugger;\n")

    result = Gate().run(ChangeSet.detect(tmp_path))
    assert not result.accepted
    assert any(f.code == "DEBUGGER" for f in result.findings)
