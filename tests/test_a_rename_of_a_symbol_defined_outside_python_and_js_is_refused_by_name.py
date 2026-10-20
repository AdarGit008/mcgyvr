"""A rename of a symbol defined outside Python and JS/TS is refused, by language.

The index extracts Go, Rust and Java symbols, so it finds their definitions; the
rename resolver binds references in Python and JS/TS only. A symbol whose only
definition is in another language is therefore refused with that reason, before the
resolver is asked and before any file is written, rather than with a parser
disagreement it did not have or a lookup that fails. Where the same name is also
defined in Python, the Python symbol is renamed and the other language's files are
not candidates at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.orchestrator.references import UnsafeRenameError, resolve
from mcgyvr.rename import RenameError
from mcgyvr.rename import apply as rename_apply
from tests.renaming import committed, read, untouched

GO = {
    "cmd/serve.go": "package cmd\n\nfunc Serve() {}\n",
    "cmd/main.go": "package cmd\n\nfunc main() {\n\tServe()\n}\n",
}
RUST = {
    "src/serve.rs": "pub fn serve() {}\n",
    "src/main.rs": "mod serve;\n\nfn main() {\n    serve::serve();\n}\n",
}
JAVA = {
    "src/Server.java": "public class Server {\n    public void serve() {}\n}\n",
}


@pytest.mark.parametrize(
    ("tree", "old", "language", "where"),
    [
        (GO, "Serve", "go", "cmd/serve.go"),
        (RUST, "serve", "rust", "src/serve.rs"),
        (JAVA, "Server", "java", "src/Server.java"),
    ],
)
def test_a_symbol_defined_only_in_another_language_is_refused_by_language(
    tmp_path: Path,
    tree: dict[str, str],
    old: str,
    language: str,
    where: str,
) -> None:
    repo = committed(tmp_path / "repo", tree)

    with pytest.raises(RenameError, match=f"defined only in {language} source") as no:
        rename_apply(repo, old, "renamed")

    assert where in str(no.value)
    assert "Python and JS/TS only" in str(no.value)
    assert untouched(repo, tree)


def test_a_name_also_defined_in_python_renames_the_python_symbol_only(
    tmp_path: Path,
) -> None:
    tree = {
        "app/serve.py": "def Serve():\n    return 1\n",
        "app/use.py": "from app.serve import Serve\n\nServe()\n",
        **GO,
    }
    repo = committed(tmp_path / "repo", tree)

    report = rename_apply(repo, "Serve", "Start")

    after = read(repo, tree)
    assert after["app/serve.py"] == "def Start():\n    return 1\n"
    assert after["app/use.py"] == "from app.serve import Start\n\nStart()\n"
    assert report.files == ("app/serve.py", "app/use.py")
    assert untouched(repo, GO)


def test_the_resolver_refuses_a_defining_file_it_cannot_read() -> None:
    """No fall-through to the JS/TS resolver: a Go file is not parsed as JavaScript."""
    sources = {path: text.encode() for path, text in GO.items()}

    with pytest.raises(UnsafeRenameError, match=r"cmd/serve\.go is go source"):
        resolve(sources, set(sources), "cmd/serve.go", "Serve", "Start")
