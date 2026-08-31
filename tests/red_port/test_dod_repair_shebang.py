"""D3 — an auto-import splice must never land above a shebang.

``_import_anchor`` counts lines with the parser, and the parser does not count a
shebang at all — it is a comment to ``ast``, so a file that starts with ``#!``
has every AST line number one lower than the line it actually sits on. The
import is then spliced at index 0, *above* the shebang, and the executable stops
being one: the kernel reads the import line as the interpreter and the run
fails with ``Exec format error``.

The fix counts the shebang the parser ignores, so the anchor is never above
line 1 in a file that has one.
"""

from __future__ import annotations

import ast
from pathlib import Path

from mcgyvr.repair import _insert_imports

SHEBANG = "#!/usr/bin/env python3\n"


def test_an_import_is_never_spliced_above_a_shebang(tmp_path: Path) -> None:
    """The shebang stays on line 1; the import goes below it, not above it."""
    module = tmp_path / "m.py"
    module.write_text(SHEBANG + "\ndef use():\n    return Retry()\n")

    _insert_imports(module, ["from pkg.retry import Retry"], [])

    written = module.read_text()
    assert written.startswith(SHEBANG), (
        f"the import was spliced above the shebang, so the file is no longer "
        f"an executable: {written!r}"
    )
    assert any(
        "Retry" in line for line in written.splitlines() if line.startswith("from ")
    ), f"the import did not land below the shebang: {written!r}"
    # The file must still parse, and with the import at module level.
    assert ast.parse(written).body, "the repaired file no longer parses"
