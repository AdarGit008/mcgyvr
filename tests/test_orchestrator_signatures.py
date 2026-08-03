"""ADR-0007 moves ``deps[].signature`` from a model's output to the index's, so
these tests hold the slice to what #115 makes acceptance criteria — a signature
is reproducible from a checkout, it carries no body, both launch languages
produce signatures and imports from the passes that already run, and a file the
parser cannot handle still degrades to the text index.

The body test is the load-bearing one, and it is deliberately adversarial: the
function it asserts against contains its own signature as a string inside its
body, so a slice that took the whole node would pass a naive "no body" check by
accident. Reproducibility is asserted as text equality between two extractions
rather than as a property of the parser, because a reviewer diffing a contract's
``deps`` against the index is what the guarantee is for.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from mcgyvr.orchestrator.cache import build_index_cached
from mcgyvr.orchestrator.index import build_index
from mcgyvr.orchestrator.symbols import Symbol, SymbolKind, extract


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


def signature_of(path: str, source: str, name: str) -> str:
    """The signature the index holds for the definition of ``name`` in ``source``."""
    return next(
        s.signature
        for s in extract(path, source.encode())
        if s.kind is SymbolKind.DEFINITION and s.name == name
    )


def imports_of(path: str, source: str) -> list[tuple[str, str]]:
    """``(name, module)`` for every import in ``source``, in discovery order."""
    return [
        (s.name, s.detail)
        for s in extract(path, source.encode())
        if s.kind is SymbolKind.IMPORT
    ]


# --- acceptance: a signature carries no body --------------------------------


# The body quotes the signature verbatim. A slice that kept the body would still
# "contain the signature", so the assertion is on what must be absent.
_PYTHON_SELF_QUOTING = '''def paginate(items: list[int], size: int = 10) -> list[int]:
    """Split into pages."""
    banner = "def paginate(items: list[int], size: int = 10) -> list[int]:"
    print(banner)
    return items[:size]
'''

_JS_SELF_QUOTING = """function paginate(items, size = 10) {
  const banner = "function paginate(items, size = 10) {"
  console.log(banner)
  return items
}
"""


def test_python_signature_carries_no_body() -> None:
    signature = signature_of("m.py", _PYTHON_SELF_QUOTING, "paginate")
    assert signature.startswith(
        "def paginate(items: list[int], size: int=10) -> list[int]:"
    )
    assert "banner" not in signature
    assert "return" not in signature


def test_js_signature_carries_no_body() -> None:
    signature = signature_of("m.js", _JS_SELF_QUOTING, "paginate")
    assert signature == "function paginate(items, size = 10)"
    assert "banner" not in signature


# --- acceptance: a signature is reproducible from a checkout ----------------


def test_signature_is_identical_across_extractions() -> None:
    """Two extractions over unchanged bytes produce the same text, both languages."""
    for path, source in (
        ("m.py", _PYTHON_SELF_QUOTING),
        ("m.js", _JS_SELF_QUOTING),
        ("m.ts", "class Repo<T> extends Base implements Store<T> {\n  x = 1\n}\n"),
    ):
        first = [s.signature for s in extract(path, source.encode())]
        second = [s.signature for s in extract(path, source.encode())]
        assert first == second
        assert any(first), f"{path} produced no signature at all"


def test_signature_survives_the_cache(tmp_path: Path) -> None:
    """The cached path is a second way to get a signature, and must agree."""
    repo = init_repo(tmp_path / "repo")
    (repo / "a.py").write_text(_PYTHON_SELF_QUOTING)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")
    cache = tmp_path / "cache"

    fresh = build_index(repo).symbols.definitions("paginate")
    build_index_cached(repo, directory=cache)  # populate
    cached = build_index_cached(repo, directory=cache).index.symbols.definitions(
        "paginate"
    )
    assert [s.signature for s in cached] == [s.signature for s in fresh]
    assert cached[0].signature.startswith("def paginate(")


# --- Python: what the ast node already visited yields -----------------------


def test_python_signature_keeps_annotations_and_docstring() -> None:
    source = 'def f(a: int, *, b: str = "x") -> bool:\n    """Doc."""\n    return 1\n'
    assert signature_of("m.py", source, "f") == (
        'def f(a: int, *, b: str=\'x\') -> bool:\n    """Doc."""'
    )


def test_python_signature_without_a_docstring_stubs_the_body() -> None:
    signature = signature_of("m.py", "def f(a):\n    return a\n", "f")
    assert signature == "def f(a):\n    ..."


def test_python_signature_keeps_decorators() -> None:
    """A decorator is interface: @property changes how a caller may use the name."""
    source = "class C:\n    @property\n    def size(self) -> int:\n        return 1\n"
    assert signature_of("m.py", source, "size") == (
        "@property\ndef size(self) -> int:\n    ..."
    )


def test_python_class_signature_keeps_bases_and_drops_members() -> None:
    source = (
        'class Repo(Base, metaclass=M):\n    """Docs."""\n\n'
        "    def get(self):\n        return 1\n"
    )
    assert signature_of("m.py", source, "Repo") == (
        'class Repo(Base, metaclass=M):\n    """Docs."""'
    )
    # The method is still its own symbol, with its own signature.
    assert signature_of("m.py", source, "get") == "def get(self):\n    ..."


def test_python_async_signature_keeps_the_async_keyword() -> None:
    source = "async def fetch(url: str) -> bytes:\n    return b''\n"
    assert signature_of("m.py", source, "fetch") == (
        "async def fetch(url: str) -> bytes:\n    ..."
    )


def test_python_extraction_does_not_disturb_the_walk() -> None:
    """The stub is built from a copy, so the rest of the file still indexes."""
    source = "def outer():\n    inner()\n\n\ndef other():\n    pass\n"
    kinds = [(s.name, s.kind) for s in extract("m.py", source.encode())]
    assert ("outer", SymbolKind.DEFINITION) in kinds
    assert ("other", SymbolKind.DEFINITION) in kinds
    assert ("inner", SymbolKind.REFERENCE) in kinds


# --- Python: imports --------------------------------------------------------


def test_python_imports_name_the_module_they_come_from() -> None:
    source = (
        "import os\n"
        "import os.path as p\n"
        "from pkg.mod import fetch, send as post\n"
        "from . import sibling\n"
        "from .config import load\n"
    )
    assert imports_of("m.py", source) == [
        ("os", "os"),
        ("os.path", "os.path"),
        ("fetch", "pkg.mod"),
        ("send", "pkg.mod"),
        ("sibling", "."),
        ("load", ".config"),
    ]


def test_python_import_signature_holds_the_statement_and_the_alias() -> None:
    """``name`` is the dependency; the local alias survives on the statement."""
    imported = [
        s
        for s in extract("m.py", b"from pkg import send as post\n")
        if s.kind is SymbolKind.IMPORT
    ]
    assert [(s.name, s.signature) for s in imported] == [
        ("send", "from pkg import send as post")
    ]


def test_python_star_import_is_recorded_not_dropped() -> None:
    assert imports_of("m.py", "from pkg import *\n") == [("*", "pkg")]


def test_python_function_level_import_is_still_an_import() -> None:
    source = "def f():\n    import json\n    return json\n"
    assert imports_of("m.py", source) == [("json", "json")]


# --- JS/TS: signatures and imports -----------------------------------------


def test_js_signatures_across_the_shapes_that_name_a_function() -> None:
    source = (
        "function declared(a, b) {\n  return a\n}\n"
        "const arrow = (a) => {\n  return a\n}\n"
        "class C extends Base {\n  method(x) {\n    return x\n  }\n}\n"
    )
    assert signature_of("m.js", source, "declared") == "function declared(a, b)"
    assert signature_of("m.js", source, "arrow") == "const arrow = (a) =>"
    assert signature_of("m.js", source, "C") == "class C extends Base"
    assert signature_of("m.js", source, "method") == "method(x)"


def test_typescript_signature_keeps_type_annotations() -> None:
    source = "function typed(x: number, y?: string): Promise<void> {\n  return\n}\n"
    assert signature_of("m.ts", source, "typed") == (
        "function typed(x: number, y?: string): Promise<void>"
    )


def test_js_expression_bodied_arrow_stops_at_the_arrow() -> None:
    assert signature_of("m.js", "const twice = (n) => n * 2\n", "twice") == (
        "const twice = (n) =>"
    )


def test_js_imports_across_the_shapes_that_bring_a_name_in() -> None:
    source = (
        'import def from "./default"\n'
        'import { a, b as c } from "./named"\n'
        'import * as ns from "pkg"\n'
        'import "./styles.css"\n'
    )
    assert sorted(imports_of("m.js", source)) == [
        ("./styles.css", "./styles.css"),
        ("a", "./named"),
        ("b", "./named"),
        ("def", "./default"),
        ("ns", "pkg"),
    ]


def test_js_import_signature_holds_the_statement_and_the_alias() -> None:
    imported = [
        s
        for s in extract("m.ts", b'import { send as post } from "./api"\n')
        if s.kind is SymbolKind.IMPORT
    ]
    assert [(s.name, s.signature) for s in imported] == [
        ("send", 'import { send as post } from "./api"')
    ]


def test_js_re_export_is_an_export_not_an_import() -> None:
    """ADR-0007 puts the barrel file in the "cannot name it" bucket, not this one."""
    symbols = extract("m.js", b'export { x } from "./x"\n')
    assert [s.name for s in symbols if s.kind is SymbolKind.EXPORT] == ["x"]
    assert [s for s in symbols if s.kind is SymbolKind.IMPORT] == []


# --- what does *not* carry a signature --------------------------------------


def test_references_and_exports_carry_no_signature() -> None:
    """Both are occurrences of a name declared elsewhere; asserting one would lie."""
    source = "__all__ = ['f']\n\n\ndef f():\n    helper()\n"
    for symbol in extract("m.py", source.encode()):
        if symbol.kind in (SymbolKind.REFERENCE, SymbolKind.EXPORT):
            assert symbol.signature == "", symbol


# --- acceptance: an unparseable file still degrades to text -----------------


def test_a_file_the_parser_cannot_handle_still_text_indexes(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    (repo / "broken.py").write_text("def broken(\n    # never closed\n")
    (repo / "good.py").write_text("def fine(a: int) -> int:\n    return a\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")

    index = build_index(repo)
    assert [s.path for s in index.symbols.all()] == ["good.py"] * len(
        index.symbols.all()
    )
    assert [m.path for m in index.search("never closed")] == ["broken.py"]
    assert index.symbols.definitions("fine")[0].signature == (
        "def fine(a: int) -> int:\n    ..."
    )


# --- the index-level accessor #50 will read ---------------------------------


def test_imports_narrow_to_one_file(tmp_path: Path) -> None:
    repo = init_repo(tmp_path / "repo")
    (repo / "a.py").write_text("from pkg import fetch\n")
    (repo / "b.js").write_text('import { send } from "./api"\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")

    index = build_index(repo)
    assert {(s.path, s.name) for s in index.symbols.imports()} == {
        ("a.py", "fetch"),
        ("b.js", "send"),
    }
    assert [s.name for s in index.symbols.imports("a.py")] == ["fetch"]
    assert index.symbols.imports("nothing.py") == ()


def test_an_import_does_not_masquerade_as_a_definition() -> None:
    """The file that imports ``fetch`` is not the file that defines it."""
    symbols = extract("m.py", b"from pkg import fetch\n")
    assert [s.kind for s in symbols] == [SymbolKind.IMPORT]
    assert Symbol("fetch", SymbolKind.DEFINITION, "m.py", 1) not in symbols
