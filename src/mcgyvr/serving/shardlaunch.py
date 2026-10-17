"""What a sizing plan of a split model becomes: the processes to start.

A plan says which cards hold which blocks; this module turns it into the
processes those cards need -- for llama.cpp one server on the head's machine
plus one ``rpc-server`` per card of every other machine, for vLLM one process
per machine -- and each process carries its host, role, cards, port, engine
flags, trailing arguments, environment and the shards it holds. What is not a
split (one card, a split that does not fit, an rpc worker with no address it
may bind, an engine with no launch) is refused with a LaunchError instead of
being started.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.serving import ROLE_HEADLESS, ROLE_RPC, ROLE_SERVE
from mcgyvr.serving.sharding import (
    LLAMACPP_ENGINE,
    VLLM_ENGINE,
    Plan,
    Shard,
    Target,
)

# Every process is told to number its cards by PCI bus, so the order the
# driver would otherwise pick cannot move a plan's card onto another device.
DEVICE_ORDER_ENV = "CUDA_DEVICE_ORDER"
DEVICE_ORDER_BUS = "PCI_BUS_ID"
# vLLM takes the layers of each pipeline stage from this variable, so the
# plan's per-card layer counts are stated in it.
PIPELINE_PARTITION_ENV = "VLLM_PP_LAYER_PARTITION"
# A worker holds one card, which is device 0 of the process it runs in.
RPC_DEVICE = "CUDA0"
# A vLLM node other than the first is started with this trailing switch.
HEADLESS_SWITCH = "--headless"


class LaunchError(Exception):
    """A plan that cannot be started as the processes it asks for.

    The message names the model and what is wrong with the plan or the
    shard it would have started.
    """


@dataclass(frozen=True)
class Process:
    """One process to start, and what it is started with.

    ``host`` is the machine it runs on and ``role`` is what it is there for
    (serving, an rpc worker lending a card, a headless vLLM node); ``gpus``
    are the cards it holds, ``port`` the one it serves or listens on, ``args``
    the engine's flags, ``extra`` the trailing arguments after them, ``env``
    the environment it needs, and ``shards`` the plan's shards whose cards it
    holds.
    """

    host: str
    role: str
    gpus: tuple[int, ...]
    port: int
    args: Mapping[str, str]
    extra: tuple[str, ...]
    env: Mapping[str, str]
    shards: tuple[Shard, ...]


def processes(
    plan: Plan,
    *,
    model: str,
    weights: Path,
    port: int,
    cache_type_k: str,
    cache_type_v: str,
    threads: int,
    n_ubatch: int,
    rpc_port: int,
    master_port: int,
) -> tuple[Process, ...]:
    """The processes that serve this plan, the serving one first.

    A plan that does not fit is refused rather than started to fail at load,
    and a plan of fewer than two cards is not a split to launch. The engine
    the plan was sized for picks the shape: llama.cpp gives a head server and
    its rpc workers, vLLM one process per machine.
    """
    if not plan.fits:
        raise LaunchError(
            f"{model}: the split does not fit, and a launch would be started "
            f"to fail at load: {plan.fullest.says()}"
        )
    if len(plan.shards) < 2:
        raise LaunchError(
            f"{model}: a split over {len(plan.shards)} card is not a split; the "
            f"ordinary unit serves one card"
        )
    if plan.engine == LLAMACPP_ENGINE:
        return _llama(
            plan,
            model=model,
            weights=weights,
            port=port,
            cache_type_k=cache_type_k,
            cache_type_v=cache_type_v,
            threads=threads,
            n_ubatch=n_ubatch,
            rpc_port=rpc_port,
        )
    if plan.engine == VLLM_ENGINE:
        return _vllm(
            plan,
            model=model,
            port=port,
            cache_type_k=cache_type_k,
            master_port=master_port,
        )
    raise LaunchError(f"{model}: no launch is known for engine {plan.engine!r}")


def _same(host_a: str, host_b: str) -> bool:
    """Whether two host names name the same machine, ignoring case."""
    return host_a.lower() == host_b.lower()


def _pinned() -> dict[str, str]:
    return {DEVICE_ORDER_ENV: DEVICE_ORDER_BUS}


def worker_may_listen(address: ipaddress.IPv4Address) -> bool:
    """Whether a worker on another machine may bind this address.

    rpc-server has no authentication, so the address must be one the head
    reaches that worker at and nothing wider: not every interface, not
    loopback, and not an address the internet can reach.
    """
    return not (address.is_unspecified or address.is_loopback or address.is_global)


def _bind(target: Target, *, model: str) -> str:
    """The IPv4 literal a worker on this card's machine listens on for the head.

    What the shard states as ``bind``, or the target's host when it states
    none; either way it must be an IPv4 literal, because rpc-server binds
    one.
    """
    stated = target.bind if target.bind is not None else target.host
    where = f"card {target.gpu} of {target.host}"
    try:
        address = ipaddress.IPv4Address(stated)
    except ValueError:
        if target.bind is not None:
            raise LaunchError(
                f"{model}: {where} states bind {target.bind!r}, which is not an "
                f"IPv4 literal, and rpc-server binds only one"
            ) from None
        raise LaunchError(
            f"{model}: {where} is reached over RPC, and rpc-server binds only an "
            f"IPv4 literal while {target.host!r} is a name. State the address "
            f"the head reaches it at as `bind` on that shard"
        ) from None
    if worker_may_listen(address):
        return str(address)
    if address.is_unspecified or address.is_loopback:
        raise LaunchError(
            f"{model}: {where} would bind {stated}, and a worker on another "
            f"machine must listen on the one address the head reaches it at, "
            f"never every interface and never loopback; state it as `bind`"
        )
    raise LaunchError(
        f"{model}: {where} would bind {stated}, an address reachable from "
        f"the internet, and rpc-server has no authentication: anyone who "
        f"reaches it can use the card. Bind a private or overlay-network "
        f"address the head reaches it at"
    )


def _head_shards(plan: Plan, *, model: str) -> tuple[Shard, ...]:
    held = tuple(shard for shard in plan.shards if _same(shard.target.host, plan.head))
    if not held:
        raise LaunchError(
            f"{model}: the plan's head is {plan.head!r} and none of its cards is "
            f"on that machine"
        )
    return held


def _llama(
    plan: Plan,
    *,
    model: str,
    weights: Path,
    port: int,
    cache_type_k: str,
    cache_type_v: str,
    threads: int,
    n_ubatch: int,
    rpc_port: int,
) -> tuple[Process, ...]:
    """The head server and one rpc worker per card of another machine.

    llama.cpp numbers its devices in the plan's order -- the cards reached
    over RPC first, then the head's own -- so a plan whose cards are in
    another order is refused rather than split onto the wrong cards. Each
    worker machine counts its rpc ports from ``rpc_port`` up, one card per
    port, and the head is handed the resulting endpoints as ``--rpc``.
    """
    if plan.grid.split is None:
        raise LaunchError(f"{model}: a llama.cpp plan states no --split-mode")
    local = _head_shards(plan, model=model)
    remote = tuple(s for s in plan.shards if not _same(s.target.host, plan.head))
    if plan.shards != (*remote, *local):
        raise LaunchError(
            f"{model}: the plan's cards are not in llama.cpp's device order "
            f"(cards reached over RPC first, then the head's own); the tensor "
            f"split would put layers on the wrong cards"
        )
    if len(plan.layer_counts) != len(plan.shards):
        raise LaunchError(
            f"{model}: the plan states {len(plan.layer_counts)} layer count(s) "
            f"for {len(plan.shards)} cards"
        )

    # The head server's flags: what an ordinary one-card unit is given, with
    # the plan's context, batch, slot and cache figures, plus the split the
    # plan sized across the cards this launch holds.
    args: dict[str, str] = {
        "--model": str(weights),
        # Every block the plan puts on a card, plus the one output layer: any
        # smaller count would leave the first blocks on the host and shift
        # every other block onto a card it was not sized for.
        "-ngl": str(len({b for shard in plan.shards for b in shard.blocks}) + 1),
        "-c": str(plan.ctx_per_slot * plan.slots),
        "-ub": str(n_ubatch),
        "-b": str(n_ubatch),
        "-fa": "on",
        "--parallel": str(plan.slots),
        "-t": str(threads),
        "-ctk": cache_type_k,
        "-ctv": cache_type_v,
        "--split-mode": plan.grid.split,
        "--tensor-split": ",".join(str(count) for count in plan.layer_counts),
    }

    workers: list[Process] = []
    next_on: dict[str, int] = {}
    for shard in remote:
        key = shard.target.host.lower()
        listens = rpc_port + next_on.get(key, 0)
        next_on[key] = next_on.get(key, 0) + 1
        workers.append(
            Process(
                host=shard.target.host,
                role=ROLE_RPC,
                gpus=(shard.target.gpu,),
                port=listens,
                args={"-H": _bind(shard.target, model=model), "-d": RPC_DEVICE},
                extra=(),
                env=_pinned(),
                shards=(shard,),
            )
        )
    endpoints = [f"{worker.args['-H']}:{worker.port}" for worker in workers]
    if len(set(endpoints)) != len(endpoints):
        raise LaunchError(
            f"{model}: two workers would listen on one address and port "
            f"({', '.join(endpoints)}); state a distinct `bind` per machine or "
            f"a distinct rpc_port"
        )
    if endpoints:
        args["--rpc"] = ",".join(endpoints)
    head = Process(
        host=plan.head,
        role=ROLE_SERVE,
        gpus=tuple(shard.target.gpu for shard in local),
        port=port,
        args=args,
        extra=(),
        env=_pinned(),
        shards=local,
    )
    return (head, *workers)


def _vllm(
    plan: Plan,
    *,
    model: str,
    port: int,
    cache_type_k: str,
    master_port: int,
) -> tuple[Process, ...]:
    """One process per machine, the head's machine first and the one answering.

    Machines are ranked in the order their first card appears in the plan,
    and a plan whose first card is not on the head's machine is refused,
    vLLM's first node being the one that answers. Every node states the
    plan's tensor and pipeline sizes, and a pipeline of more than one stage
    is told the plan's layer partition through the environment. A grid over
    several machines also states the backend, node count, rank and
    rendezvous, and starts every node but the first with ``--headless``; a
    grid on one machine states none of them.
    """
    hosts: list[str] = []
    for shard in plan.shards:
        if not any(_same(shard.target.host, seen) for seen in hosts):
            hosts.append(shard.target.host)
    if not _same(hosts[0], plan.head):
        raise LaunchError(
            f"{model}: the plan's first card is on {hosts[0]!r} and its head is "
            f"{plan.head!r}; vLLM's first node is the one that answers"
        )
    held = {
        host.lower(): tuple(s for s in plan.shards if _same(s.target.host, host))
        for host in hosts
    }
    common = {
        "--tensor-parallel-size": str(plan.grid.tensor),
        "--pipeline-parallel-size": str(plan.grid.pipeline),
        "--max-num-seqs": str(plan.slots),
        "--max-model-len": str(plan.ctx_per_slot),
        "--kv-cache-dtype": cache_type_k,
    }
    env = _pinned()
    if plan.grid.pipeline > 1:
        env[PIPELINE_PARTITION_ENV] = ",".join(str(c) for c in plan.layer_counts)
    multi = len(hosts) > 1
    if multi and master_port == port:
        raise LaunchError(
            f"{model}: the rendezvous port and the serving port are both "
            f"{port} on the head's machine; state a different master_port"
        )
    master = _master_addr(held[hosts[0].lower()], model=model)
    out: list[Process] = []
    for rank, host in enumerate(hosts):
        args = dict(common)
        if multi:
            args.update(
                {
                    "--distributed-executor-backend": "mp",
                    "--nnodes": str(len(hosts)),
                    "--node-rank": str(rank),
                    "--master-addr": master,
                    "--master-port": str(master_port),
                }
            )
        here = held[host.lower()]
        out.append(
            Process(
                host=host,
                role=ROLE_SERVE if rank == 0 else ROLE_HEADLESS,
                gpus=tuple(shard.target.gpu for shard in here),
                port=port,
                args=args,
                extra=() if rank == 0 else (HEADLESS_SWITCH,),
                env=dict(env),
                shards=here,
            )
        )
    return tuple(out)


def _master_addr(head: tuple[Shard, ...], *, model: str) -> str:
    """The address the head's machine is reached at for the vLLM rendezvous.

    The first ``bind`` the head's cards state, when one of them states it,
    otherwise the head host as the plan names it.
    """
    for shard in head:
        if shard.target.bind is not None:
            try:
                return str(ipaddress.IPv4Address(shard.target.bind))
            except ValueError:
                raise LaunchError(
                    f"{model}: card {shard.target.gpu} of {shard.target.host} "
                    f"states bind {shard.target.bind!r}, which is not an IPv4 "
                    f"literal"
                ) from None
    return head[0].target.host
