"""The deterministic index is the substrate the whole cost argument rests on,
so these tests hold it to the three things #47 makes acceptance criteria — the
build is bounded and reported, an unsupported language still yields text search,
and (by construction, there being no model client to call) nothing here reaches
a model — plus the failure modes that would quietly erode the guarantee: an
ignored file leaking in, a binary or oversized file being read, and symbol
extraction missing the shapes each language actually uses to name things.

Symbols are tested directly through :func:`extract` for precision, and through
:func:`build_index` for the enumeration and reporting around it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mcgyvr.orchestrator.index import IndexBuildError, build_index
from mcgyvr.orchestrator.symbols import SymbolKind, extract


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def init_repo(repo: Path) -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    return repo


# --- enumeration and ignore rules ------------------------------------------


def test_non_git_directory_fails_loud(tmp_path: Path) -> None:
    with pytest.raises(IndexBuildError, match="cannot enumerate"):
        build_index(tmp_path)


def test_ignored_files_are_excluded_and_untracked_are_included(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "kept.py").write_text("a = 1\n")  # committed
    git(repo, "add", "kept.py")
    git(repo, "commit", "-q", "-m", "seed")
    (repo / ".gitignore").write_text("ignored.py\n")
    (repo / "ignored.py").write_text("secret = 1\n")  # ignored
    (repo / "untracked.py").write_text("b = 2\n")  # untracked but not ignored

    index = build_index(repo)
    indexed = {f.path for f in index.files}
    assert "kept.py" in indexed
    assert "untracked.py" in indexed  # --others picks it up
    assert "ignored.py" not in indexed  # --exclude-standard drops it


# --- bounded, reported build -----------------------------------------------


def test_build_stats_are_reported(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "a.py").write_text("def f():\n    return 1\n")
    index = build_index(repo)
    stats = index.stats
    assert stats.elapsed_seconds >= 0.0
    assert stats.files_indexed == len(index.files)
    assert stats.bytes_indexed > 0
    assert stats.languages.get("python") == 1


def test_oversized_files_are_skipped_not_read(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "big.py").write_text("x = 1\n" * 100)
    (repo / "small.py").write_text("y = 2\n")
    index = build_index(repo, max_file_bytes=10)
    indexed = {f.path for f in index.files}
    assert "small.py" in indexed
    assert "big.py" not in indexed
    assert index.stats.files_skipped_large == 1


def test_binary_files_are_detected_and_skipped(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "data.bin").write_bytes(b"\x00\x01\x02binary\x00")
    (repo / "code.py").write_text("z = 3\n")
    index = build_index(repo)
    indexed = {f.path for f in index.files}
    assert "code.py" in indexed
    assert "data.bin" not in indexed
    assert index.stats.files_skipped_binary == 1


# --- degradation to text-only ----------------------------------------------


def test_unsupported_language_still_yields_text_search(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "notes.txt").write_text("the fetch helper lives here\n")
    index = build_index(repo)

    # No symbols from a .txt file...
    assert index.stats.symbol_count == 0
    assert ".txt" in index.stats.degraded_extensions
    # ...but its text is searchable.
    hits = index.search("fetch")
    assert len(hits) == 1
    assert hits[0].path == "notes.txt"
    assert hits[0].line == 1


# --- text search -----------------------------------------------------------


def test_text_search_reports_path_and_line(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "a.py").write_text("first\nneedle here\nthird\n")
    index = build_index(repo)
    hits = index.search("needle")
    assert [(h.path, h.line) for h in hits] == [("a.py", 2)]


def test_text_search_is_case_insensitive_by_default(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "a.py").write_text("FetchClient\n")
    index = build_index(repo)
    assert len(index.search("fetchclient")) == 1
    assert len(index.search("fetchclient", ignore_case=False)) == 0


def test_text_search_supports_regex_and_limit(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "a.py").write_text("foo1\nfoo2\nfoo3\nbar\n")
    index = build_index(repo)
    assert len(index.search(r"foo\d", regex=True)) == 3
    assert len(index.search(r"foo\d", regex=True, limit=2)) == 2


# --- Python symbols --------------------------------------------------------


def _kinds(path: str, source: str) -> list[tuple[str, str, str]]:
    return [(s.name, s.kind.value, s.detail) for s in extract(path, source.encode())]


def test_python_definitions_distinguish_methods_from_functions() -> None:
    source = "def free():\n    pass\nclass C:\n    def method(self):\n        pass\n"
    got = _kinds("m.py", source)
    assert ("free", "definition", "function") in got
    assert ("C", "definition", "class") in got
    assert ("method", "definition", "method") in got


def test_python_async_def_is_a_definition() -> None:
    got = _kinds("m.py", "async def fetch():\n    pass\n")
    assert ("fetch", "definition", "function") in got


def test_python_dunder_all_is_authoritative_for_exports() -> None:
    source = (
        "__all__ = ['public']\ndef public():\n    pass\ndef _private():\n    pass\n"
    )
    exports = {
        s.name for s in extract("m.py", source.encode()) if s.kind is SymbolKind.EXPORT
    }
    assert exports == {"public"}


def test_python_public_top_level_names_export_without_dunder_all() -> None:
    source = "def public():\n    pass\ndef _private():\n    pass\n"
    exports = {
        s.name for s in extract("m.py", source.encode()) if s.kind is SymbolKind.EXPORT
    }
    assert exports == {"public"}


def test_python_calls_are_references() -> None:
    source = "def f():\n    helper()\n    obj.method()\n"
    refs = {
        s.name
        for s in extract("m.py", source.encode())
        if s.kind is SymbolKind.REFERENCE
    }
    assert {"helper", "method"} <= refs


def test_python_syntax_error_yields_no_symbols_not_a_crash() -> None:
    assert extract("m.py", b"def broken(\n") == []


# --- JS/TS symbols ---------------------------------------------------------


def test_js_function_class_and_method_are_definitions() -> None:
    source = "function f() {}\nclass C {\n  method() {}\n}\n"
    got = _kinds("m.js", source)
    assert ("f", "definition", "function") in got
    assert ("C", "definition", "class") in got
    assert ("method", "definition", "method") in got


def test_js_arrow_const_binding_is_a_definition() -> None:
    got = _kinds("m.js", "const fetchThing = () => 1\n")
    assert ("fetchThing", "definition", "function") in got


def test_js_plain_const_is_not_a_definition() -> None:
    names = {s.name for s in extract("m.js", b"const answer = 42\n")}
    assert "answer" not in names


def test_js_named_and_default_exports() -> None:
    source = "export function foo() {}\nexport default bar\nexport { a, b }\n"
    exports = {
        s.name for s in extract("m.js", source.encode()) if s.kind is SymbolKind.EXPORT
    }
    assert {"foo", "default", "a", "b"} <= exports


def test_js_call_expressions_are_references() -> None:
    source = "function f() {\n  helper()\n  obj.method()\n}\n"
    refs = {
        s.name
        for s in extract("m.js", source.encode())
        if s.kind is SymbolKind.REFERENCE
    }
    assert {"helper", "method"} <= refs


def test_typescript_grammar_parses_type_annotations() -> None:
    got = _kinds("m.ts", "function typed(x: number): string {\n  return ''\n}\n")
    assert ("typed", "definition", "function") in got


def test_symbol_table_lookups_after_build(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "a.py").write_text("def fetch():\n    return 1\n")
    (repo / "b.py").write_text("from a import fetch\n\n\ndef use():\n    fetch()\n")
    index = build_index(repo)
    defs = index.symbols.definitions("fetch")
    refs = index.symbols.references("fetch")
    assert [(d.path, d.line) for d in defs] == [("a.py", 1)]
    assert ("b.py", 5) in [(r.path, r.line) for r in refs]
