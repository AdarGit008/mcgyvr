"""A shim applies the door's rule under an interpreter that has no mcgyvr.

The door puts ``gate-scripts/bin`` first on PATH, so everything it starts
finds its ``ssh`` and ``docker`` rather than the real ones. Those two are
executables and not ``.py`` files on purpose — a shim that could be imported
is a shim that could be replaced — which means their ``#!/usr/bin/env
python3`` resolves THROUGH PATH, and the interpreter that ends up running one
need not be the interpreter running the door. From an installed wheel it
routinely is not: `python -m mcgyvr.serving.run` out of a virtualenv that was
never activated leaves ``python3`` pointing at the system one, which has no
mcgyvr.

Each shim already anticipates that and falls back to loading ``gatelib.py``
by path. What the fallback did not do is register the module it built in
``sys.modules``, and ``gatelib`` has held a dataclass since the rig lease
landed (#423, ``Lease``). ``gatelib.py`` carries ``from __future__ import
annotations``, so every annotation is a string, and ``@dataclass`` resolves a
bare string annotation against the defining module::

    ns = sys.modules.get(cls.__module__).__dict__   # dataclasses._is_type

``cls.__module__`` is ``"gatelib"``, nothing registered that name, and the
shim died on ``AttributeError: 'NoneType' object has no attribute
'__dict__'`` before it could apply any rule at all. The lease broke the
fallback the lease depends on: reading a lease off a rig is what the shim
does before it lets a call through.

It is not caught by the rest of the suite because every test and every `make`
target runs under `uv run`, which puts the project's own venv first on PATH —
so the plain import succeeds and the fallback is dead code in every
configuration this repository exercises.

What must be true: run either shim under an interpreter that cannot import
mcgyvr and it refuses the way the door means it to, naming the rule, rather
than tracing back.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "src" / "mcgyvr" / "serving" / "gate-scripts" / "bin"

#: One call per shim that reaches the door's rule: `ssh` names the host
#: itself, `docker` takes the door's from RUN_HOST.
CALLS = {"ssh": ["srv2", "true"], "docker": ["ps"]}

#: The rule every shim applies before it becomes the real binary.
REFUSAL = "was not started by the door"


@pytest.fixture
def blind(tmp_path: Path) -> dict[str, str]:
    """An environment whose ``import mcgyvr`` fails, on this interpreter.

    A module named ``mcgyvr`` on ``PYTHONPATH`` shadows the installed
    package — PYTHONPATH is searched before site-packages — so the shim takes
    the same branch the system python3 takes on a machine where mcgyvr was
    never installed, without needing such a machine to run the test on.
    """
    (tmp_path / "mcgyvr.py").write_text(
        'raise ImportError("no mcgyvr on this interpreter")\n', encoding="utf-8"
    )
    return {**os.environ, "PYTHONPATH": str(tmp_path), "RUN_HOST": "srv2"}


@pytest.mark.parametrize("shim", sorted(CALLS))
def test_a_shim_without_mcgyvr_refuses_rather_than_traces_back(
    shim: str, blind: dict[str, str]
) -> None:
    done = subprocess.run(
        [sys.executable, str(BIN / shim), *CALLS[shim]],
        env=blind,
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = done.stdout + done.stderr
    assert "Traceback" not in output, (
        f"bin/{shim} traced back under an interpreter with no mcgyvr, so the "
        f"door's rule was never applied:\n{output}"
    )
    assert done.returncode != 0, (
        f"bin/{shim} admitted a call nothing started by the door made"
    )
    assert REFUSAL in output, f"bin/{shim} refused without naming the rule:\n{output}"
