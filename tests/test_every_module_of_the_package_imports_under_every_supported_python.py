"""Every module of the package can be imported under every Python it supports.

The package declares the Python versions it supports, and a user may run any of
them. A module that imports on one of those versions and not on another is a
module that is missing for some users, and the first they hear of it is a
traceback at import.

What each test covers:

* The import walk imports every module of the package in a child interpreter
  of the Python that runs the suite. It proves the promise on that Python, and
  only on that one; CI runs this file under newer supported Pythons as well.
  The child keeps a failed import, and whatever a module does when imported,
  out of the running test session.
* The compile check compiles every source file of the package on the Python
  that runs the suite. It covers the scripts shipped inside the package too,
  which are compiled here but never imported, since they are programs and not
  modules.
* The docstring scan rules out one known cause on every Python, including one
  older than those that fail: a docstring that holds a *lone* surrogate (a code
  point in U+D800..U+DFFF that is not half of a pair). Older compilers keep it
  as it is. Newer ones clean docstrings at compile time and encode them as
  UTF-8 while doing so, which a lone surrogate cannot survive, so the module
  raises ``UnicodeEncodeError`` before any of its code runs. Other string
  literals holding one compile and run, so the scan looks at docstrings only.
  A docstring that *talks about* such a character must show its escape
  (``\\ud800`` in the source), not hold the character.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import mcgyvr

PACKAGE = Path(mcgyvr.__file__).resolve().parent

#: Run in a child interpreter: import every module the package's walk finds,
#: print one line per failure, and exit non-zero when there was any. A module
#: that ends the interpreter at import is a failure like any other, so the
#: walk catches that too, and its last line says the walk reached its end.
_WALK_ENDED = "the walk reached its end"
_IMPORT_ALL = f"""
import importlib
import pkgutil
import sys

import mcgyvr

failed = []
tried = 0
for info in pkgutil.walk_packages(
    mcgyvr.__path__, "mcgyvr.", onerror=lambda name: failed.append(name)
):
    tried += 1
    try:
        importlib.import_module(info.name)
    except BaseException as exc:
        failed.append(f"{{info.name}}: {{type(exc).__name__}}: {{exc}}")
print("\\n".join(failed))
print(f"{_WALK_ENDED}: {{tried}} modules tried")
sys.exit(1 if failed else 0)
"""

#: The longest the walk may take. It imports every module once in one process.
_WALK_TIMEOUT_S = 300

_DOCUMENTED = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _sources() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def _lone_surrogates(text: str) -> list[str]:
    return [f"U+{ord(c):04X}" for c in text if 0xD800 <= ord(c) <= 0xDFFF]


def test_the_package_has_sources_to_check() -> None:
    assert (PACKAGE / "__init__.py") in _sources()


def test_every_module_of_the_package_imports_on_this_python(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, "-c", _IMPORT_ALL],
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=_WALK_TIMEOUT_S,
    )
    assert done.returncode == 0, (
        f"on Python {sys.version.split()[0]} these modules do not import:\n"
        f"{done.stdout}{done.stderr}"
    )
    assert _WALK_ENDED in done.stdout, (
        f"on Python {sys.version.split()[0]} the walk ended before it had tried "
        f"every module:\n{done.stdout}{done.stderr}"
    )


def test_every_source_file_of_the_package_compiles_on_this_python() -> None:
    failed = []
    for path in _sources():
        try:
            compile(path.read_bytes(), str(path), "exec", dont_inherit=True)
        except (SyntaxError, ValueError) as exc:
            failed.append(f"{path.relative_to(PACKAGE)}: {type(exc).__name__}: {exc}")
    assert not failed, "\n".join(failed)


def test_no_docstring_in_the_package_holds_a_lone_surrogate() -> None:
    found = []
    for path in _sources():
        tree = ast.parse(path.read_bytes(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, _DOCUMENTED):
                continue
            docstring = ast.get_docstring(node, clean=False)
            bad = _lone_surrogates(docstring or "")
            if bad:
                line = node.body[0].lineno
                found.append(f"{path.relative_to(PACKAGE)}:{line} {bad}")
    assert not found, (
        "these docstrings hold a lone surrogate, which newer supported Pythons "
        "cannot compile, since they encode docstrings as UTF-8 while cleaning "
        "them; write the escape so the docstring shows the character without "
        "holding it:\n" + "\n".join(found)
    )
