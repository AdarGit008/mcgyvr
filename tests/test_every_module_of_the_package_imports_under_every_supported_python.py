"""Every module of the package can be imported under every Python it supports.

The package declares the Python versions it supports, and a user may run any of
them. A module that compiles on one of those versions and not on another is a
module that is missing for some users, and the first they hear of it is a
traceback at import.

One such defect is invisible on older interpreters: a non-raw string literal
that holds a *lone* surrogate (a code point in U+D800..U+DFFF that is not half
of a pair). Older compilers keep it as it is. Newer ones clean docstrings at
compile time and encode them as UTF-8 while doing so, which a lone surrogate
cannot survive, so the module raises ``UnicodeEncodeError`` before any of its
code runs. A docstring that *talks about* such a character must show its escape
(``\\ud800`` in the source), not hold the character.

The scan below proves the promise on whichever supported Python runs the suite,
because it looks at what the source means rather than at what this interpreter
happens to accept. The compile check beside it catches, on the interpreter that
runs it, any other way a module can fail to compile.
"""

from __future__ import annotations

import ast
from pathlib import Path

import mcgyvr

PACKAGE = Path(mcgyvr.__file__).resolve().parent


def _modules() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def _lone_surrogates(text: str) -> list[str]:
    return [f"U+{ord(c):04X}" for c in text if 0xD800 <= ord(c) <= 0xDFFF]


def test_the_package_has_modules_to_check() -> None:
    assert (PACKAGE / "__init__.py") in _modules()


def test_no_string_in_the_package_holds_a_lone_surrogate() -> None:
    found = []
    for path in _modules():
        tree = ast.parse(path.read_bytes(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                bad = _lone_surrogates(node.value)
                if bad:
                    found.append(f"{path.relative_to(PACKAGE)}:{node.lineno} {bad}")
    assert not found, (
        "these string literals hold a lone surrogate, which newer supported "
        "Pythons refuse to compile; write the escape so the text shows it "
        "without holding it:\n" + "\n".join(found)
    )


def test_every_module_of_the_package_compiles_on_this_python() -> None:
    failed = []
    for path in _modules():
        try:
            compile(path.read_bytes(), str(path), "exec", dont_inherit=True)
        except (SyntaxError, ValueError) as exc:
            failed.append(f"{path.relative_to(PACKAGE)}: {type(exc).__name__}: {exc}")
    assert not failed, "\n".join(failed)
