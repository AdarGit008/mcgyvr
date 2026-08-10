"""Fixtures shared across the tests that touch the instrument declaration.

``tools/instruments.json`` is read by five modules and none of them is a
package, so each reaches it by path through the same ``sys.modules`` slot. This
file loads it **first** — a conftest is imported before any test module — so
every rig imported later binds *this* module object, and a fixture that patches
it here is a fixture the rigs can see. Without that ordering guarantee a test
would be patching a second copy of the declaration and wondering why the guard
still fired.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load_instruments() -> types.ModuleType:
    cached = sys.modules.get("instruments")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "instruments", REPO / "tools" / "instruments.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


instruments = _load_instruments()


@pytest.fixture
def live_instruments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[types.ModuleType]:
    """The real declaration with every set un-retired and drawn from by nobody.

    #240 retired all five local sets, which is most of what the rigs can be
    pointed at — so the machinery that has nothing to do with retirement (run
    identity, resume refusal, the cap a run records) would have no live set to
    exercise itself on. This gives it one, by editing the flags rather than the
    sets: the tests then read as "with a live declaration, resuming onto
    another worker is still refused", and the refusal under the real
    declaration stays a fact about the data instead of a fact about the code.
    """
    doc = json.loads((REPO / "tools" / "instruments.json").read_text(encoding="utf-8"))
    for entry in doc["sets"]:
        entry["retired"] = None
        entry["trainable"] = False
    declaration = tmp_path / "instruments.json"
    declaration.write_text(json.dumps(doc), encoding="utf-8")
    # Two halves, and both are needed. The attribute covers every consumer that
    # already holds this module; the ``sys.modules`` entry covers the ones that
    # load a rig *inside* the test body — the by-path shims take whatever is in
    # the slot, and other test modules put their own copy there at collection
    # time. Patching only the attribute leaves those reading the real
    # declaration and wondering why the guard still fired.
    monkeypatch.setitem(sys.modules, "instruments", instruments)
    monkeypatch.setattr(instruments, "DECLARATION", declaration)
    instruments.declared.cache_clear()
    try:
        yield instruments
    finally:
        instruments.declared.cache_clear()
