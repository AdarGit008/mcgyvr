"""A refused run releases the RUN_ID it claimed, the same as a run that finishes.

Gate 5 mints the RUN_ID and claims it (``.<RUN_ID>.running`` in the run's out
directory, ``mcgyvr.serving.gatelib.claim``). The door's own docstring states the
guarantee: "the claim ... is released on every exit path, the interrupted ones
included".

It is not. ``_release_claim`` runs in the ``finally`` of the always-block, and a
gate or data script that refuses returns out of ``main`` before that block is
reached — and three entries (``data-10-scan``, ``data-20-geometry``,
``data-30-placement``) run *after* gate 5 and can each refuse. The claim survives
the process, and the next run of that step on that day is refused for a run that
is not running. The operator's only move is to delete a dotfile by hand, which is
exactly the state the claim was invented to make impossible to be in by accident.

**Driven through ``main``, not through a helper.** The finding is that an exit
path skips the release; a test calling a new ``release_and_stop`` directly would
be satisfied by adding one that the refusing path still does not reach. So the
door is run with a real sequence, a real claim taken by gate 5, and a later entry
that refuses — and the assertion is on what is left on disk afterwards.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from mcgyvr.serving import run
from tests.onedoor import executable

RUN_ID = "2026-09-06-claim-probe"


def _gates(where: Path, out_dir: Path, refuse_at: str) -> Path:
    """A full sequence whose ``refuse_at`` entry exits non-zero after gate 5.

    Every other entry succeeds and exports what ``SEQUENCE`` declares it does,
    so the run reaches the refusal the way a live run would: with a RUN_ID
    minted, claimed, and in the environment.
    """
    where.mkdir(parents=True)
    shutil.copytree(Path(run.BIN), where / "bin")
    values = {"RUN_ID": RUN_ID, "RUN_OUT_DIR": str(out_dir)}
    for entry in (*run.SEQUENCE, *run.ALWAYS):
        lines = [
            "#!/usr/bin/env python3",
            "import os, sys",
            "from pathlib import Path",
        ]
        if entry.exports:
            lines.append("fd = int(os.environ['RUN_EXPORT_FD'])")
            for key in entry.exports:
                lines.append(
                    f"os.write(fd, {f'{key}={values.get(key, "x")}\n'!r}.encode())"
                )
        if entry.script == "05-envelope.py":
            # Gate 5's actual job, done the way gate 5 does it.
            lines += [
                "from mcgyvr.serving import gatelib",
                f"Path({str(out_dir)!r}).mkdir(parents=True, exist_ok=True)",
                f"gatelib.claim(Path({str(out_dir)!r}), {RUN_ID!r})",
            ]
        if entry.script == refuse_at:
            lines.append("sys.exit(1)")
        lines.append("sys.exit(0)")
        executable(where / entry.script, "\n".join(lines) + "\n")
    return where


def _claim(out_dir: Path) -> Path:
    from mcgyvr.serving import gatelib

    return gatelib.claim_path(out_dir, RUN_ID)


def test_a_data_script_that_refuses_leaves_no_claim_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The measured case: an entry after gate 5 refuses, and the claim must go."""
    out_dir = tmp_path / "envelope"
    gates = _gates(tmp_path / "gate-scripts", out_dir, refuse_at="data-10-scan.py")
    monkeypatch.setattr(run, "GATE_SCRIPTS", gates)
    monkeypatch.setattr(run, "BIN", gates / "bin")

    step = tmp_path / "step.sh"
    executable(step, "#!/usr/bin/env bash\nexit 0\n")
    status = run.main(
        [
            "--host",
            "srv1",
            "--campaign",
            "claim-probe",
            "--model",
            "/models/x.gguf",
            "--step",
            str(step),
            "--date",
            "2026-09-06",
        ]
    )

    assert status != 0, "the fixture must actually refuse"
    assert not _claim(out_dir).exists(), (
        f"{_claim(out_dir).name} outlived the run that took it; the next run "
        "of this step today is refused for a run that is not running"
    )


def test_a_run_that_reaches_the_end_still_releases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The direction that must not break.

    The release already works on the path through the always-block. A fix that
    moved it somewhere only the refusal reaches would trade one leak for
    another, so both endings are stated.
    """
    import pytest

    monkeypatch = pytest.MonkeyPatch()
    out_dir = tmp_path / "envelope"
    gates = _gates(tmp_path / "gate-scripts", out_dir, refuse_at="")
    monkeypatch.setattr(run, "GATE_SCRIPTS", gates)
    monkeypatch.setattr(run, "BIN", gates / "bin")
    try:
        step = tmp_path / "step.sh"
        executable(step, "#!/usr/bin/env bash\nexit 0\n")
        run.main(
            [
                "--host",
                "srv1",
                "--campaign",
                "claim-probe",
                "--model",
                "/models/x.gguf",
                "--step",
                str(step),
                "--date",
                "2026-09-06",
            ]
        )
    finally:
        monkeypatch.undo()
    assert not _claim(out_dir).exists(), "a completed run releases its claim"
