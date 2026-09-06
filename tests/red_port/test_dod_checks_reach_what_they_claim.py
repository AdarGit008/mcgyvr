"""Five checks that pass while measuring nothing, or less than they say.

A check that cannot fail is worse than no check: it occupies the place a real one
would take, and it reports green. Each of these is one of those, and each was
found by tracing what the gates actually reach rather than by reading what they
are named.

1. **mypy does not see ``tools/``.** ``pyproject.toml`` sets
   ``files = ["src", "tests"]`` under ``strict = true``. Measured on 2026-09-06:
   mypy checks 390 files, ruff checks 821. Everything under ``tools/`` is linted
   and never type-checked — including ``tools/live/index.py`` and
   ``tools/live/review.py``, which the ``Makefile`` ships as ``journal-index``
   and ``journal-review``, the supported way to read the live journal, and
   ``tools/bench/*.py``, which ``tests/conftest.py`` imports at collection.

2. **The package ships no ``py.typed``.** A strict-typed library that exports no
   types: running mypy over ``tools/`` reports ``mcgyvr.telemetry: module is
   installed, but missing library stubs or py.typed marker``.

3. **``docgen.check_reference`` compares only the last dotted segment.** It
   verifies ``delivery.mode`` is documented by looking for the word ``mode``,
   which also appears under ``sandbox``. ``mode``, ``source``, ``model``,
   ``enabled``, ``image``, ``dir`` and ``attempts`` all recur across blocks, so a
   whole block could stop rendering and ``make docs-check`` would still pass on
   a namesake elsewhere.

4. **``SERVE_ALWAYS`` is read by nothing, and its test asserts it equals
   ``ALWAYS``.** ``_serve`` iterates the module-level ``ALWAYS`` directly. The
   assertion cannot fail by construction: it compares a name to the thing it was
   assigned from, on the line it was assigned.

5. **``_check_manifest`` does not cover ``rig-snapshot.sh``.** The door checks
   every gate script, both serve steps and both shims exist before running, so a
   missing file is "a refusal, not an absence, because 'the file was gone' is
   exactly how a check stops running". ``rig-snapshot.sh`` — which gate 2 reads
   and gate 7 re-uses — is not on the list. Delete it and gate 2 dies with a
   ``FileNotFoundError`` traceback, which is an absence.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from tests.red_port.conftest import required

REPO = Path(__file__).resolve().parents[2]


def test_the_type_gate_covers_the_tools_the_makefile_ships() -> None:
    """1. What mypy is pointed at must include what a user is told to run."""
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    files = config.get("tool", {}).get("mypy", {}).get("files", [])
    assert "tools" in files, (
        f"mypy checks {files}; `make journal-index` and `make journal-review` "
        "run tools/live/*.py over the live journal, type-checked by nothing"
    )


def test_the_package_exports_its_types() -> None:
    """2. A strict-typed library with no marker types nothing for its callers."""
    marker = REPO / "src" / "mcgyvr" / "py.typed"
    assert marker.is_file(), (
        "src/mcgyvr/py.typed does not exist, so every consumer — tools/ "
        "included — sees an untyped module"
    )


def test_the_reference_check_notices_a_dropped_block() -> None:
    """3. The check must fail when a whole config block stops being documented.

    Asserted by taking the rendered reference and deleting a block from it: the
    checker is handed a document that is genuinely missing ``delivery``, and must
    say so rather than finding the word ``mode`` under ``sandbox``.
    """
    from mcgyvr.docgen import render_reference

    text = render_reference()
    without = re.sub(
        r"\n#+ `?delivery.*?(?=\n#+ )", "\n", text, flags=re.DOTALL, count=1
    )
    assert without != text, "the fixture must actually remove the delivery block"

    problems = required(
        "check a rendered config reference against the schema by whole key, so "
        "a dropped block is noticed rather than matched on a namesake leaf",
        lambda: (
            __import__(
                "mcgyvr.docgen", fromlist=["reference_problems"]
            ).reference_problems
        ),
    )(without)
    assert problems, (
        "a reference missing the whole `delivery` block passed the check; the "
        "last-segment comparison found `mode` under `sandbox` instead"
    )


def test_the_door_reads_the_constant_it_exports() -> None:
    """4. A name the door exports must be the name the door uses.

    Stated as "the run reads it", not as "the two are equal" — the equality is
    what the current test asserts, and it is true by assignment.
    """
    source = (REPO / "src" / "mcgyvr" / "serving" / "run.py").read_text(
        encoding="utf-8"
    )
    uses = [
        line
        for line in source.splitlines()
        if "SERVE_ALWAYS" in line and not line.strip().startswith("SERVE_ALWAYS")
    ]
    assert uses, (
        "SERVE_ALWAYS is exported and never read; `_serve` iterates ALWAYS "
        "directly, and the only test on it compares the name to its own value"
    )


def test_the_manifest_covers_every_file_a_gate_reads() -> None:
    """5. A reader a gate depends on is part of the door, or the check is partial.

    ``rig-snapshot.sh`` is read by gate 2 and re-used by gate 7. If it can go
    missing without the manifest noticing, the door's promise that a missing
    entry is a refusal is only true of the entries someone remembered.
    """
    from mcgyvr.serving import run as door

    scripts = Path(door.__file__).resolve().parent / "gate-scripts"
    readers = {
        path.name
        for path in scripts.iterdir()
        if path.suffix == ".sh" and not path.name.startswith("_")
    }
    assert readers, "the fixture must find the shell readers beside the gates"

    source = Path(door.__file__).read_text(encoding="utf-8")
    uncovered = sorted(name for name in readers if name not in source)
    assert not uncovered, (
        f"{', '.join(uncovered)} is read by a gate and is named nowhere in the "
        "door; deleting it gives a traceback, not a refusal"
    )
