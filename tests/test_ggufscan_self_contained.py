"""``ggufscan`` is shipped to a rig as bytes, so it may depend on nothing.

The geometry read (``gate-scripts/data-20-geometry.py``) and the bench gate
(``tools/bench/serving/backends/llamacpp.py``) base64-encode this one file and
run it on the serving host as ``python3 -``: the interpreter there is whatever
the rig has -- no venv, no ``mcgyvr``, no ``PYTHONPATH``. An import added to the
file therefore fails on the rig and nowhere else, and in the one place the door
cannot see: the gate reports the header as unreadable and the placement is
refused. Moving the file into the package on 2026-09-05 put it beside modules
it could now import from, which is exactly the temptation this suite refuses.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCANNER = REPO / "src" / "mcgyvr" / "serving" / "ggufscan.py"

#: What a bare ``python3`` on a rig is guaranteed to have: the file's own
#: import line, and nothing that has ever been added to it.
STDLIB_ONLY = {"struct", "sys", "os", "json", "glob"}


def _tree() -> ast.Module:
    return ast.parse(SCANNER.read_text(encoding="utf-8"), filename=str(SCANNER))


def _imported_names(tree: ast.Module) -> set[str]:
    """Top-level names of every import, at any depth -- a lazy one counts too."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # A relative import has no module name; the empty string is not
            # in the allowed set, so it is refused the same way.
            names.add((node.module or "").split(".")[0])
    return names


def _is_main_guard(node: ast.stmt) -> bool:
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    left = node.test.left
    right = node.test.comparators
    return (
        isinstance(left, ast.Name)
        and left.id == "__name__"
        and len(right) == 1
        and isinstance(right[0], ast.Constant)
        and right[0].value == "__main__"
    )


def test_the_scanner_imports_nothing_a_rig_lacks() -> None:
    extra = sorted(_imported_names(_tree()) - STDLIB_ONLY)
    assert not extra, (
        f"{SCANNER.relative_to(REPO)} imports {extra}; it runs on the rig as "
        f"`python3 -` with nothing installed, so only {sorted(STDLIB_ONLY)} "
        "are available there"
    )


def test_the_scanner_keeps_its_main_guard() -> None:
    """The gate scripts import the module to locate it; an unguarded loop would
    print `[]` on every such import."""
    assert any(_is_main_guard(node) for node in _tree().body), (
        f'{SCANNER.relative_to(REPO)} has no `if __name__ == "__main__":` guard'
    )


def test_the_scanner_runs_isolated_from_stdin_and_reports_no_files() -> None:
    """The exact transport the gates use, with no argument: `[]`, exit 0.

    ``-I`` isolates the child from this environment -- no site-packages, no
    ``PYTHONPATH``, no current directory on ``sys.path`` -- so a dependency the
    AST walk somehow missed fails here rather than on the rig.
    """
    done = subprocess.run(
        [sys.executable, "-I", "-"],
        input=SCANNER.read_bytes(),
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert done.stdout.strip() == b"[]", done.stdout.decode("utf-8", "replace")
