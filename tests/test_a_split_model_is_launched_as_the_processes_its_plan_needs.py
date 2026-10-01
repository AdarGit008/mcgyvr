"""A split model is launched as the processes its plan needs, and nothing wider.

Promise: a sizing plan becomes the processes to start -- for llama.cpp one
server on the head's machine and one ``rpc-server`` worker per card of another
machine, for vLLM one process per machine -- each with the cards it holds, the
flags the engine takes for the split, and the environment that pins the card
order. What a plan says is stated to the engine as the plan says it. A worker
listens on the one address it was given and never on every interface, and what
cannot be launched as a split (one card, a split that does not fit, a worker
with no address) is refused by name instead of started.

The machines are invented, and so are their addresses.
"""

from __future__ import annotations

import ipaddress

import pytest

from mcgyvr.serving import ROLE_HEADLESS, ROLE_RPC, ROLE_SERVE, sharding
from mcgyvr.serving.sharding import SPLIT_LAYER, Grid
from mcgyvr.serving.shardlaunch import LaunchError
from tests.invented_split_plans import (
    ADDR_A,
    ADDR_B,
    ADDR_C,
    HOST_A,
    HOST_B,
    HOST_C,
    MASTER_PORT,
    PORT,
    RPC_PORT,
    THREADS,
    UBATCH,
    WEIGHTS,
    card,
    launch,
    links,
    llama_plan,
    table,
    two_machines_llama,
    vllm_plan,
)

# llama.cpp on one machine.


def test_a_layer_split_on_one_machine_is_one_server_told_the_plans_counts() -> None:
    made = llama_plan([card(HOST_A, 0), card(HOST_A, 1)])
    (head,) = launch(made)

    assert head.role == ROLE_SERVE
    assert head.host == HOST_A
    assert head.gpus == (0, 1)
    assert head.port == PORT
    assert head.args["--split-mode"] == "layer"
    assert head.args["--tensor-split"] == ",".join(str(c) for c in made.layer_counts)
    assert "--rpc" not in head.args
    assert head.shards == made.shards


def test_the_server_is_given_the_flags_an_ordinary_llama_cpp_unit_is_given() -> None:
    made = llama_plan([card(HOST_A, 0), card(HOST_A, 1)])
    (head,) = launch(made)

    assert head.args == {
        "--model": str(WEIGHTS),
        "-ngl": str(sum(made.layer_counts)),
        "-c": str(made.ctx_per_slot * made.slots),
        "-ub": str(UBATCH),
        "-b": str(UBATCH),
        "-fa": "on",
        "--parallel": str(made.slots),
        "-t": str(THREADS),
        "-ctk": "f16",
        "-ctv": "f16",
        "--split-mode": "layer",
        "--tensor-split": ",".join(str(c) for c in made.layer_counts),
    }
    assert "--n-cpu-moe" not in head.args
    assert "--port" not in head.args


def test_every_process_numbers_its_cards_by_the_bus() -> None:
    made = llama_plan(two_machines_llama())
    for process in launch(made):
        assert process.env["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"


def test_every_layer_of_a_deep_model_is_offloaded_so_the_counts_hold() -> None:
    # -ngl 99 would leave the first blocks of a 126-block model on the host
    # and shift every other block onto a card it was not sized for.
    deep = sharding.plan(
        table(blocks=126, block_mib=40),
        [card(HOST_A, 0, free_gib=12), card(HOST_A, 1, free_gib=12)],
        Grid(tensor=1, pipeline=2, split=SPLIT_LAYER),
        engine="llama.cpp",
        slots=1,
        ctx_per_slot=4096,
        cache_type_k="f16",
        cache_type_v="f16",
        n_ubatch=UBATCH,
        name="example-model-deep",
        links=links,
        allowance_bytes=256 << 20,
    )
    (head,) = launch(deep)
    assert sum(deep.layer_counts) == 127
    assert head.args["-ngl"] == "127"


# llama.cpp across machines.


def test_cards_of_another_machine_are_lent_by_one_worker_each_in_plan_order() -> None:
    made = llama_plan(two_machines_llama())
    head, *workers = launch(made)

    assert head.role == ROLE_SERVE
    assert head.host == HOST_A
    assert head.gpus == (0, 1)
    assert [w.role for w in workers] == [ROLE_RPC, ROLE_RPC]
    assert [w.host for w in workers] == [HOST_B, HOST_B]
    assert [w.gpus for w in workers] == [(0,), (1,)]
    # The plan's shards: the cards reached over RPC first, then the head's own.
    assert [w.shards[0] for w in workers] == list(made.shards[:2])
    assert head.shards == made.shards[2:]
    # One count per card, in the same order.
    assert len(head.args["--tensor-split"].split(",")) == 4


def test_two_cards_of_one_worker_machine_listen_on_consecutive_ports() -> None:
    made = llama_plan(two_machines_llama())
    head, *workers = launch(made)

    assert [w.port for w in workers] == [RPC_PORT, RPC_PORT + 1]
    assert head.args["--rpc"] == f"{ADDR_B}:{RPC_PORT},{ADDR_B}:{RPC_PORT + 1}"


def test_each_worker_machine_counts_its_own_ports_from_the_first() -> None:
    made = llama_plan(
        [
            card(HOST_A, 0),
            card(HOST_B, 0, bind=ADDR_B),
            card(HOST_C, 0, bind=ADDR_C),
        ]
    )
    head, *workers = launch(made)

    assert [w.port for w in workers] == [RPC_PORT, RPC_PORT]
    assert head.args["--rpc"] == f"{ADDR_B}:{RPC_PORT},{ADDR_C}:{RPC_PORT}"


def test_a_worker_lends_one_card_and_listens_on_its_bind_and_nothing_wider() -> None:
    made = llama_plan(two_machines_llama())
    _, *workers = launch(made)

    for worker in workers:
        assert worker.args == {"-H": ADDR_B, "-d": "CUDA0"}
        assert worker.extra == ()
        assert "--port" not in worker.args
        assert worker.args["-H"] != "0.0.0.0"


def test_a_host_that_is_already_an_ipv4_literal_needs_no_bind() -> None:
    made = llama_plan([card(HOST_A, 0), card(ADDR_B, 0)])
    head, worker = launch(made)

    assert worker.args["-H"] == ADDR_B
    assert head.args["--rpc"] == f"{ADDR_B}:{RPC_PORT}"


def test_a_worker_machine_with_only_a_name_is_refused_by_shard_and_asked_for_bind() -> (
    None
):
    made = llama_plan([card(HOST_A, 0), card(HOST_B, 0)])
    with pytest.raises(LaunchError, match=HOST_B) as raised:
        launch(made)
    assert "bind" in str(raised.value)
    assert "card 0" in str(raised.value)


def test_a_bind_that_means_every_interface_is_refused() -> None:
    made = llama_plan([card(HOST_A, 0), card(HOST_B, 0, bind="0.0.0.0")])
    with pytest.raises(LaunchError, match="every interface"):
        launch(made)


def test_a_bind_that_is_not_an_address_is_refused() -> None:
    made = llama_plan([card(HOST_A, 0), card(HOST_B, 0, bind="box-b.internal")])
    with pytest.raises(LaunchError, match="IPv4 literal"):
        launch(made)


def test_a_bind_reachable_from_the_internet_is_refused_as_unauthenticated() -> None:
    # Built from a documentation block rather than written, so no machine's
    # address is named here: the first octet moved out of every private,
    # shared and documentation range.
    public = str(ipaddress.IPv4Address("198.51.100.20") + (1 << 24))
    assert ipaddress.IPv4Address(public).is_global
    made = llama_plan([card(HOST_A, 0), card(HOST_B, 0, bind=public)])
    with pytest.raises(LaunchError, match="no authentication"):
        launch(made)


def test_two_workers_that_would_share_an_address_and_port_are_refused() -> None:
    made = llama_plan(
        [
            card(HOST_A, 0),
            card(HOST_B, 0, bind=ADDR_B),
            card(HOST_C, 0, bind=ADDR_B),
        ]
    )
    with pytest.raises(LaunchError, match="one address and port"):
        launch(made)


# What is never a split.


def test_a_plan_of_one_card_is_not_a_split() -> None:
    made = llama_plan([card(HOST_A, 0)], Grid(tensor=1, pipeline=1, split=SPLIT_LAYER))
    with pytest.raises(LaunchError, match="not a split"):
        launch(made)


def test_a_split_that_does_not_fit_is_not_launched() -> None:
    made = llama_plan([card(HOST_A, 0, free_gib=1), card(HOST_A, 1, free_gib=1)])
    assert not made.fits
    with pytest.raises(LaunchError, match="does not fit"):
        launch(made)


# vLLM.


def test_a_tensor_split_on_one_machine_is_one_process_with_no_multi_node_flags() -> (
    None
):
    made = vllm_plan([card(HOST_A, 0), card(HOST_A, 1)], Grid(tensor=2, pipeline=1))
    (node,) = launch(made)

    assert node.role == ROLE_SERVE
    assert node.gpus == (0, 1)
    assert node.port == PORT
    assert node.extra == ()
    assert node.args == {
        "--tensor-parallel-size": "2",
        "--pipeline-parallel-size": "1",
        "--max-num-seqs": str(made.slots),
        "--max-model-len": str(made.ctx_per_slot),
        "--kv-cache-dtype": "float16",
    }
    assert node.env == {"CUDA_DEVICE_ORDER": "PCI_BUS_ID"}


def test_a_grid_over_two_machines_is_one_node_each_and_only_the_first_answers() -> None:
    made = vllm_plan(
        [
            card(HOST_A, 0, bind=ADDR_A),
            card(HOST_A, 1),
            card(HOST_B, 0),
            card(HOST_B, 1),
        ],
        Grid(tensor=2, pipeline=2),
    )
    first, second = launch(made)

    assert (first.host, first.role, first.gpus) == (HOST_A, ROLE_SERVE, (0, 1))
    assert (second.host, second.role, second.gpus) == (HOST_B, ROLE_HEADLESS, (0, 1))
    assert first.extra == ()
    assert second.extra == ("--headless",)
    for rank, node in enumerate((first, second)):
        assert node.args["--tensor-parallel-size"] == "2"
        assert node.args["--pipeline-parallel-size"] == "2"
        assert node.args["--distributed-executor-backend"] == "mp"
        assert node.args["--nnodes"] == "2"
        assert node.args["--node-rank"] == str(rank)
        assert node.args["--master-addr"] == ADDR_A
        assert node.args["--master-port"] == str(MASTER_PORT)
        assert node.port == PORT
        assert node.shards == tuple(
            s for s in made.shards if s.target.host == node.host
        )


def test_the_pipelines_layer_counts_are_stated_to_every_node() -> None:
    made = vllm_plan(
        [card(HOST_A, 0), card(HOST_A, 1), card(HOST_B, 0), card(HOST_B, 1)],
        Grid(tensor=2, pipeline=2),
    )
    for node in launch(made):
        assert node.env["VLLM_PP_LAYER_PARTITION"] == ",".join(
            str(c) for c in made.layer_counts
        )
        assert node.env["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"


def test_the_rendezvous_is_the_head_host_when_no_bind_is_stated() -> None:
    made = vllm_plan([card(HOST_A, 0), card(HOST_B, 0)], Grid(tensor=1, pipeline=2))
    first, second = launch(made)

    assert first.args["--master-addr"] == HOST_A
    assert second.args["--master-addr"] == HOST_A
    assert second.args["--node-rank"] == "1"


def test_a_pure_tensor_split_across_machines_states_no_layer_partition() -> None:
    made = vllm_plan([card(HOST_A, 0), card(HOST_B, 0)], Grid(tensor=2, pipeline=1))
    for node in launch(made):
        assert "VLLM_PP_LAYER_PARTITION" not in node.env


def test_a_rendezvous_on_the_servers_own_port_is_refused() -> None:
    made = vllm_plan([card(HOST_A, 0), card(HOST_B, 0)], Grid(tensor=1, pipeline=2))
    with pytest.raises(LaunchError, match="rendezvous"):
        launch(made, master_port=PORT)


def test_a_vllm_plan_of_one_card_is_not_a_split() -> None:
    made = vllm_plan([card(HOST_A, 0)], Grid(tensor=1, pipeline=1))
    with pytest.raises(LaunchError, match="not a split"):
        launch(made)
