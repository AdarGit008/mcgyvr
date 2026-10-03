"""Each process of a split model renders as a compose service and as a command.

Promise: a process that holds several cards reserves every one of them; a
worker that lends a card runs ``rpc-server`` with no model and no weights
mount; a vLLM node that answers nothing renders like any vLLM unit with its
``--headless``; what an engine reads beside its argv is the service's
environment, and a clash with what the file already sets is refused by name.
A launch that needs an image built with RPC support is refused, naming the
unit, until the unit states one. The compose service and the bare command say
the same thing, as they do for any other unit.

The machines are invented, and so are their addresses.
"""

from __future__ import annotations

import shlex
from dataclasses import replace
from typing import Any

import pytest
import yaml

from mcgyvr.emit import EmitError, render_command, render_compose
from mcgyvr.serving import (
    ROLE_HEADLESS,
    ROLE_RPC,
    ROLE_SERVE,
    Fit,
    Unit,
    UnitKey,
    Width,
)
from mcgyvr.serving.sharding import Grid
from mcgyvr.serving.shardlaunch import Process
from tests.invented_split_plans import (
    HF_CACHE,
    HOST_A,
    HOST_B,
    NAME,
    WEIGHTS,
    card,
    launch,
    llama_plan,
    two_machines_llama,
    vllm_plan,
)

#: The image an operator built with RPC support; invented.
RPC_IMAGE = "example.invalid/llama-rpc:build-1"
REPO = "example-org/example-model-large"


def unit_of(
    process: Process, *, engine: str, image: str | None = None, model: str = NAME
) -> Unit:
    """The unit a caller builds from one process: the process says the rest."""
    return Unit(
        key=UnitKey(host=process.host, model=model, engine=engine, port=process.port),
        host=process.host,
        model=model,
        engine=engine,
        gpu=process.gpus[0],
        weights=HF_CACHE if engine == "vllm" else WEIGHTS,
        width=Width(value=2, how="written"),
        args=process.args,
        fit=Fit(fits=True, headroom_gb=0.0, why="invented"),
        port=process.port,
        image=image,
        extra=process.extra,
        gpus=process.gpus,
        role=process.role,
        env=process.env,
    )


def service_of(unit: Unit) -> dict[str, Any]:
    document = yaml.safe_load(render_compose(unit))
    (service,) = document["services"].values()
    assert isinstance(service, dict)
    return service


def devices_of(service: dict[str, Any]) -> list[str]:
    reserved = service["deploy"]["resources"]["reservations"]["devices"]
    (entry,) = reserved
    return list(entry["device_ids"])


def llama_units(image: str | None = RPC_IMAGE) -> list[Unit]:
    made = llama_plan(two_machines_llama())
    return [
        unit_of(process, engine="llama.cpp", image=image) for process in launch(made)
    ]


def vllm_units() -> list[Unit]:
    made = vllm_plan(
        [card(HOST_A, 0), card(HOST_A, 1), card(HOST_B, 0), card(HOST_B, 1)],
        Grid(tensor=2, pipeline=2),
    )
    return [unit_of(process, engine="vllm", model=REPO) for process in launch(made)]


# The device reservation.


def test_a_process_that_holds_two_cards_reserves_both() -> None:
    head = llama_units()[0]
    assert devices_of(service_of(head)) == ["0", "1"]


def test_a_vllm_node_reserves_every_card_it_holds() -> None:
    first, second = vllm_units()
    assert devices_of(service_of(first)) == ["0", "1"]
    assert devices_of(service_of(second)) == ["0", "1"]


def test_a_unit_that_names_no_cards_still_reserves_its_one_card() -> None:
    head = llama_units()[0]
    plain = replace(
        head,
        gpus=(),
        gpu=3,
        role=ROLE_SERVE,
        env={},
        args={k: v for k, v in head.args.items() if k != "--rpc"},
    )
    service = service_of(plain)
    assert devices_of(service) == ["3"]
    assert service["environment"] == {"LLAMA_ARG_HOST": "0.0.0.0"}
    assert "entrypoint" not in service


# The worker.


def test_a_worker_runs_rpc_server_with_no_model_and_no_weights_mount() -> None:
    _, worker, _ = llama_units()
    service = service_of(worker)

    assert service["entrypoint"] == ["rpc-server"]
    assert "volumes" not in service
    assert service["image"] == RPC_IMAGE
    command = service["command"]
    assert "--model" not in command
    assert command[command.index("-H") + 1] == "192.0.2.20"
    assert command[command.index("-d") + 1] == "CUDA0"
    assert devices_of(service) == ["0"]


def test_a_worker_has_exactly_one_port_flag_and_it_is_its_own() -> None:
    _, first, second = llama_units()
    for unit in (first, second):
        command = service_of(unit)["command"]
        assert command.count("--port") == 1
        assert command[command.index("--port") + 1] == str(unit.port)
    assert first.port != second.port


def test_a_worker_does_not_listen_on_every_interface_through_its_environment() -> None:
    _, worker, _ = llama_units()
    environment = service_of(worker)["environment"]
    assert "LLAMA_ARG_HOST" not in environment
    assert environment == {"CUDA_DEVICE_ORDER": "PCI_BUS_ID"}


def test_workers_and_the_server_of_one_model_have_names_of_their_own() -> None:
    head, first, second = llama_units()
    names = [service_of(unit)["container_name"] for unit in (head, first, second)]
    assert len(set(names)) == 3
    assert names[1].endswith("-rpc") and names[2].endswith("-rpc")


def test_the_head_is_told_where_its_workers_are() -> None:
    head = llama_units()[0]
    command = service_of(head)["command"]
    assert command[command.index("--rpc") + 1] == ("192.0.2.20:50052,192.0.2.20:50053")
    assert service_of(head)["environment"]["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"


# The node that answers nothing.


def test_a_headless_node_renders_like_a_vllm_unit_with_its_switch() -> None:
    first, second = vllm_units()
    served, headless = service_of(first), service_of(second)

    assert headless["command"][-1] == "--headless"
    assert "--headless" not in served["command"]
    assert headless["command"][0] == REPO
    assert headless["image"] == served["image"]
    assert headless["volumes"] == served["volumes"]
    assert headless["ipc"] == "host"
    assert headless["environment"]["HF_HUB_OFFLINE"] == "1"
    assert headless["environment"]["VLLM_PP_LAYER_PARTITION"]
    assert second.role == ROLE_HEADLESS


def test_a_node_of_a_multi_node_launch_carries_its_rank() -> None:
    first, second = vllm_units()
    for rank, unit in enumerate((first, second)):
        command = service_of(unit)["command"]
        assert command[command.index("--node-rank") + 1] == str(rank)


# What the engine needs that the file cannot supply.


def test_a_server_that_reaches_workers_needs_an_image_and_is_refused_without() -> None:
    head = llama_units(image=None)[0]
    with pytest.raises(EmitError, match=head.key.slug) as raised:
        render_compose(head)
    assert "RPC" in str(raised.value)
    assert "image" in str(raised.value)


def test_a_worker_needs_an_image_and_is_refused_without() -> None:
    worker = llama_units(image=None)[1]
    assert worker.role == ROLE_RPC
    with pytest.raises(EmitError, match=worker.key.slug):
        render_compose(worker)


def test_a_server_that_reaches_no_workers_needs_no_image_of_its_own() -> None:
    made = llama_plan([card(HOST_A, 0), card(HOST_A, 1)])
    (head,) = launch(made)
    service = service_of(unit_of(head, engine="llama.cpp"))
    assert service["image"].startswith("ghcr.io/")


# The environment.


def test_a_variable_the_unit_sets_beside_the_files_own_is_merged() -> None:
    first = vllm_units()[0]
    environment = service_of(first)["environment"]
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert environment["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"


def test_a_variable_the_file_already_sets_differently_is_refused_by_name() -> None:
    first = vllm_units()[0]
    clashing = replace(first, env={**first.env, "HF_HUB_OFFLINE": "0"})
    with pytest.raises(EmitError, match="HF_HUB_OFFLINE"):
        render_compose(clashing)


def test_a_role_the_engine_has_no_process_for_is_refused() -> None:
    head = llama_units()[0]
    wrong = replace(head, role=ROLE_HEADLESS)
    with pytest.raises(EmitError, match=wrong.key.slug):
        render_compose(wrong)


# Two renderings, one argv.


def test_the_bare_command_of_each_process_is_its_binary_and_the_compose_argv() -> None:
    for unit in llama_units():
        service = service_of(unit)
        binary = service.get("entrypoint", ["llama-server"])
        assert render_command(unit) == shlex.join([*binary, *service["command"]])
    for unit in vllm_units():
        service = service_of(unit)
        assert render_command(unit) == shlex.join(
            ["vllm", "serve", *service["command"]]
        )


def test_the_bare_command_of_a_worker_is_rpc_server_without_needing_an_image() -> None:
    worker = llama_units(image=None)[1]
    command = shlex.split(render_command(worker))
    assert command[0] == "rpc-server"
    assert "--model" not in command
    assert command[command.index("--port") + 1] == str(worker.port)
