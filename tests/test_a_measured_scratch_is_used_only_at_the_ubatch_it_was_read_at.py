"""A measured scratch reading is used only at the ``-ub`` it was read at.

RED. :data:`mcgyvr.serving.vramfit.MEASURED_SCRATCH_MIB` holds one number per
architecture — deepseek2 259.5, gptoss 302.1, qwen35moe 302.7 and
nemotron_h_moe 521.2 MiB — and every one was read at ``-ub 256``: the probe
passes ``-b "$UB" -ub "$UB"`` and the engine prints ``n_ubatch = 256``
(``records/evidence/2026-09-05-context-decomposition/ctx-probe.sh:50``,
``srv2-deepseek-coder-v2-16b/c2048-r1.log``, and the module's own comment on
``SCRATCH_AND_CONTEXT_MIB``). Units run at ``-ub 512`` (``DEFAULT_UBATCH``,
``src/mcgyvr/serving/__init__.py:89``). :func:`vramfit.allowance_mib` never asks
which: :func:`vramfit.explain` and :func:`vramfit.fits_measured` take
``n_ubatch`` and price the cache with it, then add a scratch reading taken at a
different batch.

The compute buffer grows with ``-ub``. nemotron reads 386.19 MiB at 256, 429.81
at 512 and 517.06 at 1024
(``records/evidence/2026-09-04-srv1-ncmoe-floor/srv2-bufprobe-nvidia_Nemotron-3-Nano-30B-A3B-IQ4_NL.tsv:5-7``),
and Qwen3.6 205, 214 and 232 (``srv1-buffer-probe.tsv`` beside it). A unit at
512 judged with a 256 reading is given less room than it allocates, which is the
under-statement the allowance exists to prevent: a cell that clears every gate
and then fails to allocate.

What is specified:

* **A reading names the ``-ub`` it was read at.** ``MEASURED_SCRATCH_MIB`` maps
  an architecture to ``{n_ubatch: MiB}``, and today's four readings sit under
  256 with the values they were measured at.
* **A reading is used only at its own ``-ub``.** ``allowance_mib(geometry,
  n_ubatch=...)`` is the reading taken at exactly that batch, and
  :data:`vramfit.SCRATCH_AND_CONTEXT_MIB` at any batch the architecture has no
  reading for — the rule the module already states for an architecture nobody
  probed.
* **``explain`` and ``fits_measured`` judge at their own ``n_ubatch``,** so the
  room a 256 reading grants does not admit the same placement at a batch it was
  not read at, and still admits it at 256.

For the GREEN. Live srv1 serves Qwen3.6 at ``-ub 512``, and
``tests/red_port/test_dod_placement_conservatism.py`` pins that its running
placement is accepted: 5347.2 MiB predicted against 5726 usable. The bound would
refuse it (5347.2 + 768), so the GREEN needs a qwen35moe reading taken at 512 —
the buffer probe above has its compute half — not the bound standing in. #438's
B77 calls ``allowance_mib({"arch": "qwen3next"})`` with no batch; how that call
reads is the GREEN's to settle with #438.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.serving import vramfit

MIB = 1 << 20

#: Today's readings, each taken at ``-ub 256`` by
#: ``records/evidence/2026-09-05-context-decomposition/ctx-probe.sh``.
READ_AT_256: dict[str, float] = {
    "deepseek2": 259.5,
    "gptoss": 302.1,
    "qwen35moe": 302.7,
    "nemotron_h_moe": 521.2,
}

#: srv1's own scan of the Qwen3.6 checkpoint it serves, and the running placement
#: ``tests/red_port/test_dod_placement_conservatism.py`` measured it at.
GEOMETRY = (
    Path(__file__).resolve().parents[1]
    / "records"
    / "evidence"
    / "2026-09-05-e2e-srv1-qwen3-6-35b-a3b-ud-iq3xxs"
    / "geometry.json"
)
SRV1_NCMOE = 32
SRV1_SLOTS = 8
SRV1_CTX_PER_SLOT = 4096

#: Batches a test may pick from when it needs one an architecture was not read at.
CANDIDATE_BATCHES = (256, 512, 1024, 2048, 4096)


def _readings(arch: str) -> dict[int, float]:
    entry: Any = vramfit.MEASURED_SCRATCH_MIB[arch]
    assert isinstance(entry, dict), (
        f"MEASURED_SCRATCH_MIB[{arch!r}] is {entry!r}: a reading that does not "
        f"name its -ub cannot be matched to the unit it is added to"
    )
    return entry


def _unread_batch(arch: str) -> int:
    readings = _readings(arch)
    return next(batch for batch in CANDIDATE_BATCHES if batch not in readings)


def _allowance(geometry: dict[str, Any], n_ubatch: int) -> float:
    allowance: Any = vramfit.allowance_mib
    result: float = allowance(geometry, n_ubatch=n_ubatch)
    return result


def _geometry() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(GEOMETRY.read_text(encoding="utf-8"))
    return loaded


def test_every_measured_scratch_reading_names_the_ubatch_it_was_read_at() -> None:
    """A number with no batch beside it cannot be told apart from one taken at 512."""
    for arch in vramfit.MEASURED_SCRATCH_MIB:
        readings = _readings(arch)
        assert readings, f"{arch} names no reading"
        for batch, mib in readings.items():
            assert isinstance(batch, int) and batch > 0, (arch, batch)
            assert isinstance(mib, int | float) and mib > 0, (arch, mib)


@pytest.mark.parametrize("arch", sorted(READ_AT_256))
def test_todays_readings_sit_under_the_batch_they_were_read_at(arch: str) -> None:
    """Moving them to 512 would be a measurement nobody took."""
    assert _readings(arch).get(256) == READ_AT_256[arch]


@pytest.mark.parametrize("arch", sorted(READ_AT_256))
def test_a_reading_is_the_allowance_at_its_own_ubatch(arch: str) -> None:
    """A measurement in hand outranks the bound — at the batch it was taken at."""
    for batch, mib in _readings(arch).items():
        assert _allowance({"arch": arch}, batch) == mib, (arch, batch)


@pytest.mark.parametrize("arch", sorted(READ_AT_256))
def test_at_a_ubatch_it_was_not_read_at_the_bound_stands(arch: str) -> None:
    """No reading for this batch is no reading: the conservative number applies."""
    batch = _unread_batch(arch)
    assert _allowance({"arch": arch}, batch) == vramfit.SCRATCH_AND_CONTEXT_MIB


def test_an_architecture_nobody_probed_gets_the_bound_at_every_ubatch() -> None:
    """The rule the module already states, asked with the batch."""
    for batch in (256, 512):
        assert (
            _allowance({"arch": "no-such-architecture"}, batch)
            == vramfit.SCRATCH_AND_CONTEXT_MIB
        )


def test_explain_reports_the_allowance_for_the_ubatch_it_was_asked_at() -> None:
    """The prediction is priced at ``n_ubatch``; its allowance is read at it too."""
    geometry = _geometry()
    assert geometry["arch"] == "qwen35moe"
    for batch in (256, _unread_batch("qwen35moe")):
        told = vramfit.explain(
            geometry,
            n_cpu_moe=SRV1_NCMOE,
            slots=SRV1_SLOTS,
            ctx_per_slot=SRV1_CTX_PER_SLOT,
            n_ubatch=batch,
        )
        assert told.allowance_mib == _allowance(geometry, batch), batch


def test_room_a_256_reading_grants_does_not_admit_a_unit_at_another_ubatch() -> None:
    """Today it does: 302.7 MiB read at 256 is added to a unit priced at 512."""
    geometry = _geometry()
    batch = _unread_batch("qwen35moe")
    told = vramfit.explain(
        geometry,
        n_cpu_moe=SRV1_NCMOE,
        slots=SRV1_SLOTS,
        ctx_per_slot=SRV1_CTX_PER_SLOT,
        n_ubatch=batch,
    )
    free = int((told.predicted_mib + READ_AT_256["qwen35moe"] + 1) * MIB)
    assert not vramfit.fits_measured(
        geometry,
        n_cpu_moe=SRV1_NCMOE,
        slots=SRV1_SLOTS,
        ctx_per_slot=SRV1_CTX_PER_SLOT,
        free_bytes=free,
        n_ubatch=batch,
    ), f"a card with room for the 256 reading must not admit the unit at -ub {batch}"


def test_the_same_room_still_admits_the_unit_at_256() -> None:
    """The guard: the reading is kept for the batch it was taken at."""
    geometry = _geometry()
    told = vramfit.explain(
        geometry,
        n_cpu_moe=SRV1_NCMOE,
        slots=SRV1_SLOTS,
        ctx_per_slot=SRV1_CTX_PER_SLOT,
        n_ubatch=256,
    )
    free = int((told.predicted_mib + READ_AT_256["qwen35moe"] + 1) * MIB)
    assert vramfit.fits_measured(
        geometry,
        n_cpu_moe=SRV1_NCMOE,
        slots=SRV1_SLOTS,
        ctx_per_slot=SRV1_CTX_PER_SLOT,
        free_bytes=free,
        n_ubatch=256,
    )
