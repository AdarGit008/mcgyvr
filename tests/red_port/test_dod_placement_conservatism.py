"""The sizing law must not refuse a placement the rig has been measured running.

``vramfit`` adds one allowance to every derivation — ``SCRATCH_AND_CONTEXT_MIB``,
768 MiB — for the compute buffer and the allocation no GGUF header names. Its own
comment calls it "deliberately generous, because it is only ever walked DOWN
from", and that was true while the free figure it was subtracted from was itself
generous: ``mcgyvr.scan`` derived free VRAM as ``total - used`` and so over-stated
it by the driver's reserve, roughly 400 MiB on srv1 and 376 on srv2.

Correcting the scan (2026-09-06) removes the over-statement, and the allowance is
now subtracted from a true number. The two changes do not cancel: srv1 is running
``--n-cpu-moe 32`` at a measured 5306 MiB of 5726 usable, and the corrected law
derives 34 for the same card and the same eight slots. The law now refuses a
placement that has been running for hours.

This is stated as a property rather than as a constant, because the fix may be to
the allowance, to how it is applied, or to reporting it separately from the
prediction — that is the port's choice. What must be true is that a measurement in
hand outranks an allowance: a placement a scan of the same card shows fitting must
not be refused by the law that sized it.

The second statement is the guard. It would be trivial to satisfy the first by
deleting the allowance, and an under-stated allowance admits a cell that clears
every gate and then fails to allocate — the failure the allowance exists to
prevent. So the law must still refuse a placement that genuinely does not fit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcgyvr.serving import vramfit
from tests.red_port.conftest import required

MIB = 1 << 20

#: srv1's own scan of the checkpoint it serves, in the evidence envelope the
#: sizing tests already read.
GEOMETRY = (
    Path(__file__).resolve().parents[2]
    / "records"
    / "evidence"
    / "2026-09-05-e2e-srv1-qwen3-6-35b-a3b-ud-iq3xxs"
    / "geometry.json"
)

#: MEASURED on srv1, 2026-09-06, with the unit up at ``--parallel 8 -c 32768``:
#: ``nvidia-smi`` reported total 6144, used 5306, free 438, reserved 401. The
#: card therefore hands out 5726 MiB and the running placement occupies 5306.
SRV1_USABLE_MIB = 5726
SRV1_RUNNING_MIB = 5306
SRV1_RUNNING_NCMOE = 32
SRV1_SLOTS = 8


def _geometry() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(GEOMETRY.read_text(encoding="utf-8"))
    return loaded


def _judge() -> Any:
    return required(
        "judge a placement against what a card hands out, without an allowance "
        "that refuses a placement the same card is measured running",
        lambda: (
            __import__(
                "mcgyvr.serving.vramfit", fromlist=["fits_measured"]
            ).fits_measured
        ),
    )


def test_the_law_accepts_the_offload_srv1_is_running() -> None:
    """32 blocks on a card measured holding them is not a placement to refuse."""
    fits = _judge()
    assert fits(
        _geometry(),
        n_cpu_moe=SRV1_RUNNING_NCMOE,
        slots=SRV1_SLOTS,
        free_bytes=SRV1_USABLE_MIB * MIB,
    ), (
        f"srv1 runs --n-cpu-moe {SRV1_RUNNING_NCMOE} at {SRV1_RUNNING_MIB} MiB of "
        f"{SRV1_USABLE_MIB} usable; the law must not refuse it"
    )


def test_the_law_still_refuses_an_offload_that_does_not_fit() -> None:
    """The guard: loosening the allowance must not admit a real overflow.

    ``--n-cpu-moe 24`` puts eight more blocks of experts on the card than the
    measured placement, about 2.1 GiB more than the 5306 MiB it was measured at,
    against 5726 usable. That does not fit on any reading and must still refuse.
    """
    fits = _judge()
    assert not fits(
        _geometry(),
        n_cpu_moe=SRV1_RUNNING_NCMOE - 8,
        slots=SRV1_SLOTS,
        free_bytes=SRV1_USABLE_MIB * MIB,
    )


def test_the_prediction_is_readable_apart_from_the_allowance() -> None:
    """A person checking the arithmetic against ``nvidia-smi`` needs both numbers.

    Today ``predict`` returns one figure with the allowance inside it, so a
    prediction of 6115 MiB against a measured 5306 cannot be told from a law that
    is wrong by 809 MiB. The allowance is a policy and the prediction is a claim
    about the card; a reader has to be able to see which is which.
    """
    report = required(
        "report a placement's predicted card usage separately from the "
        "allowance added to it",
        lambda: __import__("mcgyvr.serving.vramfit", fromlist=["explain"]).explain,
    )
    told = report(_geometry(), n_cpu_moe=SRV1_RUNNING_NCMOE, slots=SRV1_SLOTS)
    assert told.allowance_mib == vramfit.SCRATCH_AND_CONTEXT_MIB
    assert (
        abs(told.predicted_mib - SRV1_RUNNING_MIB) < vramfit.SCRATCH_AND_CONTEXT_MIB
    ), (
        f"a prediction net of the allowance must land near the measured "
        f"{SRV1_RUNNING_MIB} MiB, got {told.predicted_mib}"
    )
