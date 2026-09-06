"""A refused run releases the RUN_ID it claimed, the same as a run that finishes.

Gate 5 mints the RUN_ID and claims it (``.<RUN_ID>.running`` in the run's out
directory, ``mcgyvr.serving.gatelib.claim``). The door's own docstring states the
guarantee: "the claim ... is released on every exit path, the interrupted ones
included".

It is not. ``_release_claim`` runs in the ``finally`` of the always-block, and a
gate or data script that refuses returns out of ``main`` before that block is
reached — three entries (``data-10-scan``, ``data-20-geometry``,
``data-30-placement``) run *after* gate 5 and can each refuse. The claim survives
the process, and the next run of that step on that day is refused for a run that
is not running. The operator's only move is to delete a dotfile by hand, which is
exactly the state the claim was invented to make impossible to be in by accident.

What must be observably true: after the door stops on a refusal, the out
directory holds no claim on that RUN_ID. Which exit path stopped it is not the
point — a claim outliving its process is the defect, whatever ended the process.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.red_port.conftest import required


def _door() -> Any:
    import importlib

    return importlib.import_module("mcgyvr.serving.run")


def _claimed(out_dir: Path, run_id: str) -> Path:
    """The claim gate 5 would have taken, as it takes it."""
    from mcgyvr.serving import gatelib

    out_dir.mkdir(parents=True, exist_ok=True)
    return gatelib.claim(out_dir, run_id)


def test_a_refusal_after_gate_five_releases_the_claim(tmp_path: Path) -> None:
    """The measured case: a data script refuses, and the claim must not survive."""
    run_id = "r9-doorclaim-srv1"
    out_dir = tmp_path / "out"
    claim = _claimed(out_dir, run_id)
    assert claim.exists(), "the fixture must start from a claim actually taken"

    stop = required(
        "release the RUN_ID claim when a gate or data script refuses, not only "
        "when the run reaches its end",
        lambda: _door().stop_and_release,
    )
    env = {"RUN_OUT_DIR": str(out_dir), "RUN_ID": run_id}
    status = stop(env, 1)

    assert not claim.exists(), (
        f"{claim.name} outlived the run that took it; the next run of this step "
        "today is refused for a run that is not running"
    )
    assert status != 0, "a refusal still reports a refusal"


def test_a_run_that_took_no_claim_releases_nothing(tmp_path: Path) -> None:
    """Refusing before gate 5 is the common case and must stay silent.

    Gates 1 to 4 run before a RUN_ID exists. Releasing a claim nobody holds must
    not raise, and must not invent a file.
    """
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    stop = required(
        "release the RUN_ID claim when a gate or data script refuses, not only "
        "when the run reaches its end",
        lambda: _door().stop_and_release,
    )
    stop({}, 2)
    assert list(out_dir.iterdir()) == [], "no claim was taken, so none is written"
