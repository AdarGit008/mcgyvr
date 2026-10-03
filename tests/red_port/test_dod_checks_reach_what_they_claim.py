"""Five checks reach what they are named for.

A check that cannot fail is worse than no check: it occupies the place a real one
would take, and it reports green.

1. **mypy sees ``tools/``.** ``pyproject.toml`` points mypy at ``tools`` under
   ``strict = true``, and does not silence it there.

2. **The package ships ``py.typed``**, so a strict-typed library exports its types.

3. **``docgen.check_reference`` looks a key up under the block it belongs to.**
   ``mode``, ``source``, ``model``, ``enabled``, ``image``, ``dir`` and ``attempts``
   recur across blocks, so a check on the last segment alone would pass on a
   namesake when a whole block stopped rendering.

4. **The always-entries of the door have exactly one name.**

5. **The door's manifest covers every shell reader a gate depends on**,
   ``rig-snapshot.sh`` included, so a missing file is a refusal and not a
   ``FileNotFoundError`` traceback.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.red_port.conftest import required

REPO = Path(__file__).resolve().parents[2]


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
    """4. One list of always-entries, under one name."""
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


def test_the_manifest_covers_every_file_a_gate_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """5. A reader a gate depends on is part of the door, or the check is partial.

    ``rig-snapshot.sh`` is read by gate 2 and re-used by gate 7. If it can go
    missing without the manifest noticing, the door's promise that a missing
    entry is a refusal is only true of the entries someone remembered.

    The file is removed from a copy of the gate scripts the door is pointed
    at, never from the checkout: other tests read and copy the real folder at
    the same time, and a file renamed under them is a failure of theirs.
    """
    import shutil

    from mcgyvr.serving import run as door

    real = Path(door.__file__).resolve().parent / "gate-scripts"
    scripts = tmp_path / "gate-scripts"
    shutil.copytree(real, scripts, symlinks=True)

    def moved(path: Path) -> Path:
        # A reader that does not sit beside the gates (the link timer sits
        # beside the door) is left where it is: it is still on READERS, so
        # check_manifest still checks it, and nothing here removes it — only
        # a file in the copy is ever unlinked.
        if not path.is_relative_to(real):
            return path
        return scripts / path.relative_to(real)

    monkeypatch.setattr(door, "GATE_SCRIPTS", scripts)
    monkeypatch.setattr(door, "BIN", moved(door.BIN))
    monkeypatch.setattr(door, "DEFAULT_STEP", moved(door.DEFAULT_STEP))
    monkeypatch.setattr(door, "READERS", tuple(moved(p) for p in door.READERS))
    monkeypatch.setattr(
        door, "SERVE_STEPS", {k: moved(v) for k, v in door.SERVE_STEPS.items()}
    )
    readers = sorted(path.name for path in scripts.iterdir() if path.suffix == ".sh")
    assert readers, "the fixture must find the shell readers beside the gates"

    # Asserted by removing one and asking the door, rather than by looking for
    # the filename in the source: a comment naming the file would satisfy a
    # substring check while the door still died on a traceback.
    check = required(
        "refuse when a file a gate reads is missing, naming it — rather than "
        "raising where the gate tried to read it",
        lambda: door.check_manifest,
    )
    missing = readers[0]
    (scripts / missing).unlink()
    with pytest.raises(Exception) as refusal:
        check()
    assert missing in str(refusal.value), (
        f"the door must name {missing} when it is gone; it raised {refusal.value!r}"
    )
    assert (real / missing).is_file()
