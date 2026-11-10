"""The setup wizard reads vLLM's stock port from the detect sweep, and no unit's
default port changes.

mcgyvr has one default port for every engine, ``serving.DEFAULT_PORT`` (8080):
a unit address that carries no port resolves there whatever its engine, so a
portless vLLM unit stays on 8080. 8000 is vLLM's own stock port, recorded
among the well-known servers' ports in the detect sweep's
list (``detect.PORT_CONVENTIONS``); the wizard, staging a synthetic detection of
a vLLM placement, reuses it from there — writing it into the address it stages —
rather than spelling 8000 a second time.

Four things hold. The synthetic backend the wizard builds for a vLLM placement
carries the sweep's vLLM port, and a non-vLLM placement carries the one unit
default. The wizard *follows* the sweep: move vLLM's stock port in
``PORT_CONVENTIONS`` and the staged address moves with it — a hard-coded literal
would not. And ``port_of`` and ``UnitKey`` — how an emitted unit's address and
identity are read — still default to ``DEFAULT_PORT`` for every engine, so no
existing unit changes the port it is served on.
"""

from __future__ import annotations

import pytest

from mcgyvr import detect
from mcgyvr.cli.commands.setup import _setup_synthetic_detection
from mcgyvr.serving import DEFAULT_PORT, UnitKey, port_of


def _stock_ports() -> dict[str, int]:
    return {kind: port for kind, port, _ in detect.PORT_CONVENTIONS}


def test_the_wizard_vllm_backend_port_is_the_sweeps_stock_vllm_port() -> None:
    plans = {"rig1": {"placement": {"model_id": "a-model", "engine": "vllm"}}}

    detection = _setup_synthetic_detection(plans)

    (backend,) = detection.backends
    assert backend.base_url == f"http://rig1:{_stock_ports()['vllm']}/v1"


def test_a_non_vllm_placement_takes_the_one_unit_default_port() -> None:
    plans = {"rig1": {"placement": {"model_id": "a-model", "engine": "llama.cpp"}}}

    detection = _setup_synthetic_detection(plans)

    (backend,) = detection.backends
    assert backend.base_url == f"http://rig1:{DEFAULT_PORT}/v1"


def test_the_wizard_follows_the_sweep_when_the_stock_vllm_port_moves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The guard against regression: change vLLM's stock port in the sweep and the
    # wizard must follow it. A hard-coded literal would ignore this and keep
    # writing 8000 (this test would fail on the pre-change source). The wizard
    # imports PORT_CONVENTIONS inside the function, so patching the module
    # attribute reaches it.
    moved = tuple(
        (kind, 9001 if kind == "vllm" else port, api)
        for kind, port, api in detect.PORT_CONVENTIONS
    )
    monkeypatch.setattr(detect, "PORT_CONVENTIONS", moved)

    plans = {"rig1": {"placement": {"model_id": "a-model", "engine": "vllm"}}}
    detection = _setup_synthetic_detection(plans)

    (backend,) = detection.backends
    assert backend.base_url == "http://rig1:9001/v1"


def test_the_wizards_vllm_port_is_not_the_one_unit_default() -> None:
    # The whole point of reading the sweep: the stock vLLM port the wizard writes
    # is a different number from mcgyvr's one unit default.
    assert _stock_ports()["vllm"] != DEFAULT_PORT


def test_a_portless_unit_defaults_to_8080_for_every_engine() -> None:
    # port_of takes no engine: a portless address resolves to the one default
    # whatever engine serves it, so moving vLLM's probe to the sweep moves no
    # existing unit off 8080.
    assert DEFAULT_PORT == 8080
    assert port_of("http://rig") == DEFAULT_PORT
    assert port_of("http://rig:8080") == DEFAULT_PORT
    # A unit's identity keys on its port, which defaults to DEFAULT_PORT whatever
    # the engine: a portless vLLM unit groups on 8080, not vLLM's stock 8000, so
    # it is the same process as `http://rig:8080`.
    assert UnitKey(host="rig", model="a-model", engine="vllm").port == DEFAULT_PORT
    assert UnitKey(host="rig", model="a-model", engine="llama.cpp").port == DEFAULT_PORT
