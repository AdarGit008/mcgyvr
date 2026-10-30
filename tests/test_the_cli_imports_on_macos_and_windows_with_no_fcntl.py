"""The CLI imports on macOS and on Windows, where there is no ``fcntl``.

Every module ``import mcgyvr.cli`` loads is imported afresh with ``fcntl``
hidden and ``sys.platform`` set to the other system. The standard-library and
third-party modules are loaded first, as this system has them, since they
pick their own platform code at import; what is held here is mcgyvr's own.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

#: Prints every module, not mcgyvr's own, that importing the CLI loads.
LISTED = """
import json, sys
import mcgyvr.cli
print(json.dumps(sorted(
    n for n in sys.modules if n.split(".")[0] not in ("mcgyvr", "__main__", "fcntl")
)))
"""

#: Loads those modules, then imports the CLI as `platform` with no fcntl.
IMPORTED = """
import importlib, json, sys
for name in json.loads(sys.argv[2]):
    try:
        importlib.import_module(name)
    except Exception:
        pass
sys.modules["fcntl"] = None
sys.platform = sys.argv[1]
import mcgyvr.cli
import mcgyvr.cli.commands.setup
import mcgyvr.rig.verbs
print("imported")
"""


@pytest.fixture(scope="module")
def loaded() -> str:
    done = subprocess.run(
        [sys.executable, "-c", LISTED], capture_output=True, text=True, check=True
    )
    return json.dumps(json.loads(done.stdout))


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_the_cli_imports_with_no_fcntl(platform: str, loaded: str) -> None:
    done = subprocess.run(
        [sys.executable, "-c", IMPORTED, platform, loaded],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip() == "imported"
