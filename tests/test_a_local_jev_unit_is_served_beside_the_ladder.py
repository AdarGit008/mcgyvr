"""A local Jev unit is served beside the ladder, and `mcgyvr pool` names it.

The unit `jev.unit` binds answers every typed decision, so where it is a unit
you run (no key) it has to be brought up, the way a local verifier is: served
beside the ladder, sized and given a launch spec, and never made a rung of
it. A hosted Jev unit is someone else's process and is not served. A Jev unit
that is also the verifier's is one process, served once.

`mcgyvr pool` prints each role's model; the Jev role is printed like the
orchestrator and the verifier.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.cli import main
from mcgyvr.config import parse
from mcgyvr.scan import Scan
from mcgyvr.serving import units_for
from tests._helpers import write_setup

HOST = "rig-a.test"
HF_CACHE = "/home/someone/.cache/huggingface"
THREE_B = "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"

SCANS = {
    HOST: Scan.of(
        host=HOST,
        vram_mib=16384,
        ram_gb=64.0,
        disk_free_gb=900.0,
        cores=6,
        threads=6,
        bandwidth_gbps=40.3,
    )
}


def _unit(name: str, port: int) -> str:
    return f"""\
  {name}:
    address: http://{HOST}:{port}
    model: '{THREE_B}'
    rig: rig-a
    engine: vllm
    hf_cache: '{HF_CACHE}'
    window: 4096
    launch:
      kv_cache_dtype_k: auto
"""


FLEET = (
    "units:\n"
    + _unit("cheap", 8001)
    + _unit("judge", 8009)
    + "  hosted:\n"
    + "    address: https://api.example.com/v1\n"
    + "    model: big-model\n"
    + "    api_key_env: MCGYVR_TEST_KEY\n"
    + "ladder:\n- cheap\n"
)


def served(text: str) -> dict[int | None, tuple[str, ...]]:
    """Each served unit's port → its rungs, from one config."""
    return {
        unit.port: unit.rungs
        for unit in units_for(parse(text), SCANS, specs=(), ctx_per_slot=None)
    }


def test_a_local_jev_unit_is_served_beside_the_ladder() -> None:
    text = FLEET + "jev:\n  unit: judge\n"
    assert served(text) == {8001: ("cheap",), 8009: ("judge",)}
    assert parse(text).ladder.names == ("cheap",), "never a rung of the ladder"


def test_an_unbound_jev_block_serves_nothing_more() -> None:
    assert served(FLEET) == {8001: ("cheap",)}


def test_a_hosted_jev_unit_is_not_served(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCGYVR_TEST_KEY", "sk-test")
    assert served(FLEET + "jev:\n  unit: hosted\n") == {8001: ("cheap",)}


def test_a_jev_unit_that_is_also_the_verifier_is_served_once() -> None:
    text = FLEET + "verifier:\n  enabled: true\n  unit: judge\njev:\n  unit: judge\n"
    assert served(text) == {8001: ("cheap",), 8009: ("judge",)}


def test_pool_prints_the_jev_role_like_the_others(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = FLEET + "jev:\n  unit: judge\n"
    folder = write_setup(tmp_path / "setup", text)
    assert main(["pool", str(folder)]) == 0
    out = capsys.readouterr().out
    assert f"\njev: {THREE_B}\n" in out, out
