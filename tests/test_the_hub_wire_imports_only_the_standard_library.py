"""The hub wire imports only the standard library.

:mod:`mcgyvr.hubwire` is imported by the offline core (``runner``, ``config``)
and by the hub, which pins the product for it alone. So it reaches nothing of
``mcgyvr.cli`` or ``mcgyvr.rig`` (the offline core may not,
``tests/test_only_the_command_line_imports_the_hub_client.py``), no
tree-sitter grammar, no yaml, no third-party package at all: importing it
must not cost the hub an image of the product's world.

Two readings: its source names only standard-library modules, and a fresh
interpreter that imports it, with no site packages to lean on, has loaded
nothing else of ``mcgyvr`` and nothing outside the standard library.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys

from tests._paths import SRC

_WIRE = SRC / "hubwire.py"


def test_the_source_names_only_standard_library_modules() -> None:
    tree = ast.parse(_WIRE.read_text(encoding="utf-8"))
    named: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            named.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import reaches the package"
            assert node.module is not None
            named.add(node.module)
    tops = {name.split(".")[0] for name in named}
    assert tops - sys.stdlib_module_names == set(), sorted(tops)


def test_importing_it_loads_nothing_but_the_standard_library() -> None:
    probe = (
        "import json, sys\n"
        "before = set(sys.modules)\n"
        "import mcgyvr.hubwire as wire\n"
        "wire.schema(wire.RIDER_SCHEMA)\n"
        "print(json.dumps(sorted(set(sys.modules) - before)))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(SRC.parent)}
    done = subprocess.run(
        [sys.executable, "-S", "-c", probe],
        capture_output=True,
        text=True,
        env=env,
        check=True,
        timeout=60,
    )
    loaded: list[str] = json.loads(done.stdout)

    ours = sorted(name for name in loaded if name.split(".")[0] == "mcgyvr")
    assert ours == ["mcgyvr", "mcgyvr.hubwire"]
    foreign = sorted(
        name
        for name in loaded
        if name.split(".")[0] not in sys.stdlib_module_names
        and name.split(".")[0] != "mcgyvr"
    )
    assert foreign == []
