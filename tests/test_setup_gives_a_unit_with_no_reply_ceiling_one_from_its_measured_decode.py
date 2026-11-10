"""Setup gives a unit with no reply ceiling one from its measured decode.

Promise: while `mcgyvr setup` samples a fleet, each unit on a rig that names no
`output_tokens` gets one written into the staged `fleet.yaml`: the warm decode
its reads measured times its request timeout, clipped to its window, so a reply
is capped at what the unit can finish inside the timeout it is held to. A unit
that already names a ceiling keeps it, a unit whose reads measured no warm
decode keeps what it has, and `fleet.yaml` is not rewritten when no unit
changed.

The rig, the units and the reads are the invented ones of
:mod:`tests.sample_fleet`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from mcgyvr.fleet.sampler import FLEET, _reply_ceilings
from tests import sample_fleet as fx


def _staged(tmp_path: Path, **unit: Any) -> Path:
    """The staged setup with the one awake unit changed by `unit` (None drops a key),
    its fleet named `own`, as the fleet setup stages and samples is."""
    fleet = fx.fleet_doc()
    fleet["fleets"] = {FLEET: fleet["fleets"].pop(fx.FLEET)}
    body = fleet["units"][fx.UNIT]
    for key, value in unit.items():
        if value is None:
            body.pop(key, None)
        else:
            body[key] = value
    return fx.staged(tmp_path, fleet=fleet)


def _read_once(setup: Path) -> None:
    """One read filed under the fleet setup samples, `own`."""
    fx.read(setup, fx.READS[0], fleet=FLEET)


def _unit(setup: Path) -> dict[str, Any]:
    fleet = yaml.safe_load((setup / "fleet.yaml").read_text(encoding="utf-8"))
    body: dict[str, Any] = fleet["units"][fx.UNIT]
    return body


def test_a_unit_with_no_ceiling_gets_its_warm_decode_times_its_timeout(
    tmp_path: Path,
) -> None:
    setup = _staged(tmp_path, output_tokens=None)
    _read_once(setup)

    _reply_ceilings(setup, fx.READS[:1])

    warm, timeout = fx.Harness.warm, fx.unit()["request_timeout_s"]
    assert _unit(setup)["output_tokens"] == int(warm * timeout)


def test_the_ceiling_is_clipped_to_the_units_window(tmp_path: Path) -> None:
    setup = _staged(tmp_path, output_tokens=None, request_timeout_s=600.0)
    _read_once(setup)

    _reply_ceilings(setup, fx.READS[:1])

    assert fx.Harness.warm * 600.0 > fx.unit()["window"]
    assert _unit(setup)["output_tokens"] == fx.unit()["window"]


def test_a_unit_that_names_its_ceiling_keeps_it_and_the_file_is_not_rewritten(
    tmp_path: Path,
) -> None:
    setup = _staged(tmp_path)
    _read_once(setup)
    before = (setup / "fleet.yaml").read_bytes()

    _reply_ceilings(setup, fx.READS[:1])

    assert (setup / "fleet.yaml").read_bytes() == before
    assert _unit(setup)["output_tokens"] == fx.unit()["output_tokens"]


def test_a_unit_whose_reads_measured_no_decode_is_left_as_it_was(
    tmp_path: Path,
) -> None:
    setup = _staged(tmp_path, output_tokens=None)
    before = (setup / "fleet.yaml").read_bytes()

    _reply_ceilings(setup, fx.READS[:1])

    assert (setup / "fleet.yaml").read_bytes() == before
    assert "output_tokens" not in _unit(setup)
