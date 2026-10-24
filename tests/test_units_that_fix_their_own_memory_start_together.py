"""Units that take only the memory their launch states start together.

Two units on one card are chained (`depends_on` on a healthy neighbour) so one
does not size itself off memory the other has not taken yet. A llama.cpp unit
whose launch turns fitting off takes what its argv states and nothing more,
and the room for every unit on the card was reckoned before any was written;
so when every unit on a card does, they start at the same moment instead of
one after another. An emitted llama.cpp server states ``--fit off`` unless its
own flags or env state fitting, so units start together by default; a unit
that turns fitting back on, and any vLLM unit, keeps the card's chain. An
rpc-server worker takes no ``--fit``. A locked fleet's layout on a host is
judged by the argv each unit states.

The machines here are invented.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr.emit import _document, _fixes_its_memory, argv, emit_locked
from mcgyvr.scan import Scan
from mcgyvr.serving import ROLE_RPC, ModelSpec, Unit, unit_for

SPEC = ModelSpec(
    name="coder-small",
    vram_gb=1.5,
    ram_gb=0.0,
    disk_gb=1.0,
    kv_cache_dtype_k="f16",
    kv_cache_dtype_v="f16",
)
FIT_OFF = ("--fit", "off")


def server() -> Unit:
    """One llama.cpp server unit on an invented card."""
    scan = Scan.of(host="rig-b", vram_mib=16384, ram_gb=32.0, disk_free_gb=500.0)
    return unit_for(scan, SPEC, engine="llama.cpp", width=1, ctx_per_slot=2048)


def pair(
    first: tuple[str, ...],
    second: tuple[str, ...],
    second_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The services of two llama.cpp units on one invented card."""
    base = server()
    units = (
        replace(base, port=8101, extra=first),
        replace(
            base,
            key=replace(base.key, model="coder-other", port=8102),
            model="coder-other",
            port=8102,
            extra=second,
            env=second_env or {},
        ),
    )
    services: dict[str, Any] = yaml.safe_load(_document(units))["services"]
    return services


def chained(services: dict[str, Any]) -> bool:
    return any("depends_on" in body for body in services.values())


def test_two_units_that_turn_fitting_off_start_together() -> None:
    services = pair(FIT_OFF, FIT_OFF)
    assert len(services) == 2
    assert not chained(services)
    assert not any("healthcheck" in body for body in services.values())


def test_two_units_that_state_no_fitting_start_together() -> None:
    assert not chained(pair((), ()))
    assert not chained(pair(FIT_OFF, ()))


def test_one_unit_that_turns_fitting_on_keeps_the_chain() -> None:
    assert chained(pair(FIT_OFF, ("--fit", "on")))
    assert chained(pair((), ("-fit=on",)))
    assert chained(pair((), (), second_env={"LLAMA_ARG_FIT": "on"}))


def test_a_llama_cpp_server_is_launched_with_fitting_off_by_default() -> None:
    assert fitting(list(argv(server()))) == ["--fit", "off"]


@pytest.mark.parametrize(
    ("extra", "env", "said"),
    [
        (("--fit", "on"), {}, ["--fit", "on"]),
        (("-fit", "on"), {}, ["-fit", "on"]),
        (("--fit=on",), {}, ["--fit=on"]),
        ((), {"LLAMA_ARG_FIT": "on"}, []),
    ],
)
def test_a_unit_that_states_fitting_itself_gets_no_default(
    extra: tuple[str, ...], env: dict[str, str], said: list[str]
) -> None:
    parts = list(argv(replace(server(), extra=extra, env=env)))
    assert fitting(parts) == said


def fitting(parts: list[str]) -> list[str]:
    """The fit flags in `parts`, each with the value that follows it."""
    found: list[str] = []
    for at, part in enumerate(parts):
        if part in ("--fit", "-fit"):
            found += parts[at : at + 2]
        elif part.startswith(("--fit=", "-fit=")):
            found.append(part)
    return found


def test_an_rpc_worker_and_a_vllm_unit_get_no_fit_flag() -> None:
    worker = replace(server(), role=ROLE_RPC, args={})
    vllm = replace(server(), engine="vllm", args={})
    assert "--fit" not in argv(worker)
    assert "--fit" not in argv(vllm)


@pytest.mark.parametrize(
    ("engine", "argv", "env", "fixed"),
    [
        ("llama.cpp", ["--fit", "off"], {}, True),
        ("llama.cpp", ["-fit", "0"], {}, True),
        ("llama.cpp", ["--fit=disabled"], {}, True),
        ("llama.cpp", [], {"LLAMA_ARG_FIT": "false"}, True),
        # A flag wins over the variable, as llama.cpp reads them.
        ("llama.cpp", ["--fit", "on"], {"LLAMA_ARG_FIT": "off"}, False),
        ("llama.cpp", [], {}, False),
        ("vllm", ["--fit", "off"], {"LLAMA_ARG_FIT": "off"}, False),
    ],
)
def test_what_fixes_a_units_memory(
    engine: str, argv: list[str], env: dict[str, str], fixed: bool
) -> None:
    assert _fixes_its_memory(engine, argv, env) is fixed


def locked_fleet(first: list[str], second: list[str]) -> dict[str, Any]:
    def unit(name: str, port: int, flags: list[str]) -> dict[str, Any]:
        return {
            "unit_id": f"id-{name}",
            "address": f"http://rig-c:{port}",
            "engine": "llama.cpp",
            "image": "example/llama-server:1",
            "container": f"mcgyvr-rig-c-{name}",
            "launch": {
                "argv": ["--port", str(port), *flags],
                "env": {},
                "volumes": ["/srv/models:/models:ro"],
            },
        }

    return {
        "units": {
            "small": unit("small", 8201, first),
            "other": unit("other", 8202, second),
        },
        "fleets": {"pair": {"layout": {"rig-c": [["small"], ["other"]]}}},
    }


def test_a_locked_layout_whose_units_turn_fitting_off_starts_together(
    tmp_path: Path,
) -> None:
    together = emit_locked(locked_fleet(list(FIT_OFF), list(FIT_OFF)), tmp_path / "a")
    services = yaml.safe_load(together[0].read_text(encoding="utf-8"))["services"]
    assert len(services) == 2
    assert not chained(services)

    ordered = emit_locked(locked_fleet(list(FIT_OFF), []), tmp_path / "b")
    services = yaml.safe_load(ordered[0].read_text(encoding="utf-8"))["services"]
    assert services["other"]["depends_on"] == {
        "small": {"condition": "service_healthy"}
    }
