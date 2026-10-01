"""``mcgyvr emit`` turns vLLM's sleep mode on only where sleep and wake is on.

A level-2 sleep keeps a vLLM unit's process and gives its card back, and a
wake reads the weights in again without a container start. The server offers
that only when it was started with ``--enable-sleep-mode`` and with
``VLLM_SERVER_DEV_MODE=1``, which registers the routes the door calls. Those
routes — ``/sleep``, ``/wake_up``, ``/reset_prefix_cache`` and the rest of the
development set — answer anyone who reaches the serving port, with no
authentication.

So the switch that lets mcgyvr sleep and wake a card, ``serving.enable_sleep_wake``,
is also the switch that writes those two settings into a vLLM unit's launch
spec, and the spec says in a comment what they expose. With the switch off,
nothing in the emitted file changes. A llama.cpp unit has no such mode and is
never changed.
"""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest
import yaml

from mcgyvr.config import parse
from mcgyvr.emit import (
    argv,
    check_all,
    emit_all,
    render_command,
    render_compose,
    sleep_mode,
)
from mcgyvr.serving import Unit, unit_for
from tests.test_the_live_ladder_serves_vllm_and_carries_extra_flags import (
    DENSE,
    SEVEN_B_SPEC,
    WINDOW,
    rig,
    service_of,
)

HOST = "gpu-box.example"
SLEEP_FLAG = "--enable-sleep-mode"
DEV_MODE = "VLLM_SERVER_DEV_MODE"


def vllm_unit() -> Unit:
    return unit_for(
        rig(HOST), SEVEN_B_SPEC, engine="vllm", width=8, port=8002, ctx_per_slot=WINDOW
    )


def llama_unit() -> Unit:
    return unit_for(
        rig(HOST, vram_mib=6144, free_mib=5727), DENSE, width=8, ctx_per_slot=WINDOW
    )


def test_a_vllm_unit_with_sleep_mode_starts_with_the_flag_and_the_dev_routes() -> None:
    unit = vllm_unit()
    document = render_compose(unit, sleep_mode=True)
    service = service_of(document)

    assert SLEEP_FLAG in service["command"]
    assert service["environment"][DEV_MODE] == "1"
    assert service["command"] == list(argv(unit, sleep_mode=True))


def test_the_spec_says_the_routes_answer_anyone_who_reaches_the_port() -> None:
    document = render_compose(vllm_unit(), sleep_mode=True)
    comment = "".join(
        line for line in document.splitlines(keepends=True) if line.startswith("#")
    ).lower()

    assert "unauthenticated" in comment
    for route in ("/sleep", "/wake_up", "/reset_prefix_cache"):
        assert route in comment, route
    assert yaml.safe_load(document)["services"], "the comment leaves the file valid"


def test_without_sleep_mode_a_vllm_unit_is_emitted_exactly_as_before() -> None:
    unit = vllm_unit()
    document = render_compose(unit, sleep_mode=False)
    service = service_of(document)

    assert document == render_compose(unit)
    assert SLEEP_FLAG not in service["command"]
    assert DEV_MODE not in service["environment"]
    assert not document.startswith("#")


def test_a_llamacpp_unit_has_no_sleep_mode_to_turn_on() -> None:
    unit = llama_unit()

    assert render_compose(unit, sleep_mode=True) == render_compose(unit)


def test_the_bare_command_carries_the_same_flag_and_variable() -> None:
    unit = vllm_unit()
    words = shlex.split(render_command(unit, sleep_mode=True))

    assert words[0] == f"{DEV_MODE}=1"
    assert words[-len(argv(unit, sleep_mode=True)) :] == list(
        argv(unit, sleep_mode=True)
    )


def test_a_file_written_with_sleep_mode_drifts_from_one_without_it(
    tmp_path: Path,
) -> None:
    units = [vllm_unit()]
    emit_all(units, tmp_path, sleep_mode=True)

    assert check_all(units, tmp_path, sleep_mode=True) == ()
    assert len(check_all(units, tmp_path)) == 1


@pytest.mark.parametrize(("switch", "expected"), [("true", True), ("false", False)])
def test_sleep_mode_is_the_sleep_and_wake_switch(switch: str, expected: bool) -> None:
    config = parse(
        "units:\n"
        "  big:\n"
        f"    address: http://{HOST}:8002\n"
        "    model: a-model\n"
        "    rig: big-rig\n"
        "    engine: vllm\n"
        "ladder:\n"
        "- big\n"
        "serving:\n"
        f"  enable_sleep_wake: {switch}\n"
        "  compose_dir: /srv/specs\n"
    )

    assert sleep_mode(config) is expected


def test_a_config_that_says_nothing_has_no_sleep_mode() -> None:
    config = parse(
        "units:\n"
        "  big:\n"
        f"    address: http://{HOST}:8002\n"
        "    model: a-model\n"
        "    rig: big-rig\n"
        "ladder:\n"
        "- big\n"
    )

    assert sleep_mode(config) is False
