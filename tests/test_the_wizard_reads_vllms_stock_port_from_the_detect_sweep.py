"""The setup wizard reads vLLM's stock port from the detect sweep, and no unit's
default port changes.

mcgyvr has one default port for every engine, ``serving.DEFAULT_PORT`` (8080):
a unit address that carries no port resolves there whatever its engine, so a
portless vLLM unit stays on 8080, not vLLM's own stock 8000. The only place
8000 belongs is the detect sweep's list of stock ports
(``detect.PORT_CONVENTIONS``), which probes servers mcgyvr did not launch. The
wizard, staging a synthetic detection of a vLLM placement, reads that stock
port from the sweep rather than spelling 8000 a second time.

Two things hold. The synthetic backend the wizard builds for a vLLM placement
carries the sweep's vLLM port, and a non-vLLM placement carries the one unit
default. And ``port_of`` — which every emitted unit's address is read through —
still falls back to ``DEFAULT_PORT`` for every engine, so no existing unit
changes the port it is served on.
"""

from __future__ import annotations

from mcgyvr import detect
from mcgyvr.cli.commands.setup import _setup_synthetic_detection
from mcgyvr.serving import DEFAULT_PORT, port_of


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


def test_the_wizards_vllm_port_is_not_the_one_unit_default() -> None:
    # The whole point of reading the sweep: the stock vLLM port the wizard
    # probes is a different number from mcgyvr's one unit default.
    assert _stock_ports()["vllm"] != DEFAULT_PORT


def test_a_portless_unit_defaults_to_8080_for_every_engine() -> None:
    # port_of takes no engine: a portless address resolves to the one default
    # whatever engine serves it, so moving vLLM's probe to the sweep moves no
    # existing unit off 8080.
    assert DEFAULT_PORT == 8080
    assert port_of("http://rig") == DEFAULT_PORT
    assert port_of("http://rig:8080") == DEFAULT_PORT
