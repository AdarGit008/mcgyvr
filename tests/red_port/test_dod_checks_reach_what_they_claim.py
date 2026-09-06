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
    mypy = config.get("tool", {}).get("mypy", {})
    files = mypy.get("files", [])
    assert "tools" in files, (
        f"mypy checks {files}; `make journal-index` and `make journal-review` "
        "run tools/live/*.py over the live journal, type-checked by nothing"
    )
    # Pointing mypy at a directory and then silencing it there is the same
    # hole with a longer config. `ignore_errors` on `tools.*` would satisfy the
    # assertion above and check nothing.
    silenced = [
        override
        for override in mypy.get("overrides", [])
        if override.get("ignore_errors")
        and any(
            str(module).startswith("tools")
            for module in (
                override.get("module")
                if isinstance(override.get("module"), list)
                else [override.get("module")]
            )
        )
    ]
    assert not silenced, f"tools/ is listed and then silenced: {silenced}"


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


def test_the_always_entries_have_exactly_one_name() -> None:
    """4. One list of always-entries, under one name.

    ``SERVE_ALWAYS = ALWAYS`` is an export nothing reads: ``_serve`` iterates
    the module-level ``ALWAYS``, and the only test on it asserts the two are
    equal — true by assignment, on the line of the assignment.

    Stated as "one name", not as "the export is read", so that **deleting** the
    dead alias is a legal fix. A test demanding that ``SERVE_ALWAYS`` be read
    would forbid the cleanest answer and force a use to be invented for it.
    """
    from mcgyvr.serving import run as door

    names = sorted(
        name
        for name, value in vars(door).items()
        if not name.startswith("_")
        and isinstance(value, tuple)
        and value == door.ALWAYS
    )
    assert len(names) == 1, (
        f"the always-entries are reachable under {names}; two names for one "
        "list is how a caller comes to iterate the one nothing maintains"
    )


def test_the_manifest_covers_every_file_a_gate_reads() -> None:
    """5. A reader a gate depends on is part of the door, or the check is partial.

    ``rig-snapshot.sh`` is read by gate 2 and re-used by gate 7. If it can go
    missing without the manifest noticing, the door's promise that a missing
    entry is a refusal is only true of the entries someone remembered.
    """
    import shutil

    import pytest

    from mcgyvr.serving import run as door

    scripts = Path(door.__file__).resolve().parent / "gate-scripts"
    readers = sorted(path.name for path in scripts.iterdir() if path.suffix == ".sh")
    assert readers, "the fixture must find the shell readers beside the gates"

    # Asserted by removing one and asking the door, rather than by looking for
    # the filename in the source: a comment naming the file would satisfy a
    # substring check while the door still died on a traceback.
    check = required(
        "refuse when a file a gate reads is missing, naming it — rather than "
        "raising where the gate tried to read it",
        lambda: door.check_manifest,  # type: ignore[attr-defined]
    )
    missing = readers[0]
    moved = scripts / missing
    spare = moved.with_suffix(".sh.moved")
    shutil.move(str(moved), str(spare))
    try:
        with pytest.raises(Exception) as refusal:
            check()
        assert missing in str(refusal.value), (
            f"the door must name {missing} when it is gone; it raised {refusal.value!r}"
        )
    finally:
        shutil.move(str(spare), str(moved))
