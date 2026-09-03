#!/usr/bin/env python3
"""The llama.cpp backend: llama-server launched directly, with its flags set.

Implements the contract in :mod:`contract`. **This file names no other backend
and must not**: it knows how to stop being on the GPU and how to get itself onto
it, and who else wants the card is the orchestrator's decision, never this
module's.

**Why this exists at all.** Another engine in this tree also ends up running
``llama-server`` — it spawns one child per loaded model and proxies to it — but
it drives its own HTTP API, and that API does not expose the flags this campaign
varies. That path READS ``-ngl``/``-c``/``-np`` off the running child's command
line; nothing in it can SET them. ``--n-cpu-moe``, the single most important
knob for MoE-on-a-small-card, appeared nowhere in ``tools/`` at all. Measuring
expert offload, thread count or batch width therefore required a module that
launches ``llama-server`` itself, with the flags as arguments.

**Slots are the correctness story here, and they are measured, not assumed.**
``llama-server`` defaults to FOUR slots. Offer it eight concurrent requests and
it runs two sequential batches of four: aggregate throughput flatlines at the
n=4 value while per-request latency doubles. That is indistinguishable, in the
numbers, from a model that has saturated the hardware — and it is the exact
shape of the "llama.cpp caps at ~2x" claim this campaign exists to test. A ramp
run against default slots would have *confirmed* a configuration artifact.

Measured on srv1, 2026-08-30, Qwen2.5-Coder-3B-Q4_K_M, ``-ngl 99``, one model,
one prompt, only the launch flags differing::

    -c 4096                  total_slots=4  n_ctx=4096  2158 MiB
    -c 4096  --parallel 8    total_slots=8  n_ctx=512   2154 MiB
    -c 16384 --parallel 8    total_slots=8  n_ctx=2048  2588 MiB

Two things follow, and both are enforced below rather than left to a caller:

1. **``--parallel`` is always set, and never below the widest level the ramp
   will offer.** :func:`claim` reads ``total_slots`` back off ``/props`` and
   refuses a launch that did not get the width it asked for, because a slot
   count that silently came back smaller is a false plateau waiting to be
   recorded as a finding.

2. **``-c`` is the TOTAL context and is divided across the slots.** Per-slot is
   ``-c / total_slots``, which is why row two above reads 512. The contract's
   ramp asks for :data:`contract.RAMP_TOKENS` (475) completion tokens on top of
   a prompt, so a 512-token slot truncates the very generation being timed.
   Configs therefore declare ``ctx_per_slot`` and this module multiplies; a
   caller that insists on a raw ``n_ctx`` gets it validated against the width.

**mmap stays on.** ``--no-mmap`` is never passed and is refused if a config asks
for it (D-mmap, 2026-08-25): it is a fix for a RAM shortage, not an
optimisation, and every srv2 cell measured slower with it. The MoE gate below
is what keeps a model that cannot fit from thrashing instead.
"""

from __future__ import annotations

import importlib.util
import re
import shlex
import sys
import time
import types
from pathlib import Path
from typing import Any


def _contract() -> types.ModuleType:
    """The shared contract, by path — ``tools/`` is not a package.

    One slot, so every backend and the orchestrator share a single copy: two
    would mean two ramps, two idle thresholds and two definitions of what
    "clean" means, which is the drift the contract exists to prevent.
    """
    cached = sys.modules.get("serving_contract")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "serving_contract", Path(__file__).resolve().parents[1] / "contract.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["serving_contract"] = module
    spec.loader.exec_module(module)
    return module


contract = _contract()


def _fingerprint() -> types.ModuleType:
    """The serving-config fingerprint, shared through one slot."""
    cached = sys.modules.get("serving_fingerprint")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "serving_fingerprint", Path(__file__).resolve().parents[1] / "fingerprint.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["serving_fingerprint"] = module
    spec.loader.exec_module(module)
    return module


fingerprint = _fingerprint()

NAME = "llamacpp"

#: The port this engine ships on. llama-server's own default, and deliberately
#: distinct from every other engine's in this tree: they are never up at once
#: by the orchestrator's exclusion rule, but a port collision would make a stale
#: server answer for a live one.
PORT = 8080

#: Pinned. The build is part of the measurement — b10481 is the first build in
#: this campaign that carries the ngram speculative family and `bailingmoe3`,
#: and a floating tag would silently change the instrument between cells.
CONTAINER_IMAGE = "ghcr.io/ggml-org/llama.cpp:server-cuda-b10481"

CONTAINER_REPOSITORY = CONTAINER_IMAGE.split(":")[0]

#: What we start is what we stop. A cell never repairs a machine it found wrong
#: (run contract §4), and killing a stranger's container is further from repair
#: than anything that clause was written about.
CONTAINER_NAME = "mcgyvr-llamacpp"

#: The host tree holding GGUF blobs, and where it appears inside the container.
#: A single mount point is what lets :func:`release` tell our `llama-server`
#: from a `llama-server` this module did not start: ours carries `/models/` in
#: its command line, a proxied child carries a blob path under its own store.
HOST_MODELS = "$HOME/models"
CONTAINER_MODELS = "/models"

#: A card holding less than this, after a release, is carrying nothing of ours.
IDLE_BEFORE_LOAD_MIB = contract.IDLE_GPU_MIB

#: Headroom the MoE mmap gate keeps between a GGUF and the RAM available to hold
#: it. Two gigabytes, and the number is the campaign's, not this module's: a
#: model mmap'd right up to `available` thrashes instead of refusing, and a
#: thrashing cell reports a throughput that is really a disk benchmark.
MMAP_HEADROOM_BYTES = 2 * 1000**3

#: Measured on the rigs 2026-08-30: container to `/health` was 25.2 s for a 3B
#: dense (24.1 s warm — the cost is CUDA init, not the read) and 47.7 s for a
#: 12.11 GB MoE under `--n-cpu-moe 99`. A 36 GB MoE off a cold page cache is the
#: worst case this has to cover, so the budget is an order of magnitude above
#: the measured cases rather than a tight fit to them.
START_TIMEOUT_S = 900.0

#: Kept on a refusal, so the cause survives the next launch's `docker rm -f`.
LAUNCH_LOG_LINES = 60

#: Room a slot must have for the prompt, ON TOP of the ramp's completion budget.
#:
#: A slot sized to :data:`contract.RAMP_TOKENS` exactly is not big enough: the
#: window holds the prompt AND the reply, so 512 tokens against a 475-token
#: completion leaves 37 for the prompt and truncates a generation the ramp is
#: timing. The failure is silent — the server answers 200 and reports the
#: tokens it managed — so it reads downstream as a slow model rather than as a
#: context that was too small. 512 is deliberately generous against the
#: contract's own short prompt, because the cost of being wrong in this
#: direction is a few hundred MiB of KV and the cost in the other is a
#: corrupted curve.
PROMPT_HEADROOM_TOKENS = 512

#: The smallest per-slot context this backend will launch or accept.
MIN_CTX_PER_SLOT = contract.RAMP_TOKENS + PROMPT_HEADROOM_TOKENS


def probe(host: str) -> str | None:
    """The base URL this engine answers on, or ``None``. Read-only."""
    base = f"http://{host}:{PORT}"
    return base if contract.get_json(contract.url(base, "/props")) else None


def inventory(host: str, base: str) -> list[str]:
    """Every model this engine could serve here — the GGUF blobs on disk.

    **Not "loaded models", and the difference is the engine's.** ``llama-server``
    serves exactly one model for the life of the process, so the other sense of
    an inventory (a library the server can switch between) does not exist. What
    a caller can usefully ask is which files a cell could name, which is a
    listing of the host tree the container mounts.

    ``base`` is accepted and unused: the running server's own model is one entry
    of this list and is reported by :func:`residents`.
    """
    listing = contract.ssh(
        host,
        f"find {HOST_MODELS} -name '*.gguf' -printf '%p\\n' 2>/dev/null | sort || true",
    )
    return [line.strip() for line in (listing or "").splitlines() if line.strip()]


def readings(host: str) -> dict[str, Any]:
    """This engine's own footprint on the machine.

    ``props`` is the field the slot correctness rests on: it carries
    ``total_slots`` and the per-slot ``n_ctx`` that :func:`claim` asserts
    against, and a caller checking ``total_slots >= max(levels)`` reads it from
    here without paying for a :func:`describe`.
    """
    reads = {
        "image": (
            "docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' "
            f"| grep {shlex.quote(CONTAINER_REPOSITORY)} || true"
        ),
        "containers": (
            "docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}' "
            f"| grep {shlex.quote(CONTAINER_REPOSITORY + ':')} || true"
        ),
        # `-a` so a stopped container is still in the record even though
        # `release` deliberately counts only running ones.
        "server_processes": "pgrep -af '[l]lama-server' || true",
        "props": f"curl -s -m 10 http://127.0.0.1:{PORT}/props || true",
        "slots": f"curl -s -m 10 http://127.0.0.1:{PORT}/slots || true",
        # The gate's own input, recorded beside the cells it admits or refuses.
        "memory": "free -b | head -2 || true",
    }
    # Scrubbed: a `docker inspect`/process command line is where a token lives,
    # and this is written to a tracked path.
    return {
        name: {
            "command": command,
            "stdout": contract.scrub(contract.ssh(host, command)),
        }
        for name, command in reads.items()
    }


def build(host: str) -> dict[str, Any]:
    """This engine's version on ``host``, for the identity block (#326).

    The pinned image tag IS the build for this engine — there is no
    ``--version`` to ask on a host where the server only exists inside a
    container — so the tag is confirmed present rather than parsed out of a
    running process.
    """
    command = (
        "docker images --format '{{.Repository}}:{{.Tag}}' "
        f"| grep -x {shlex.quote(CONTAINER_IMAGE)} || true"
    )
    raw = contract.ssh(host, command)
    if (raw or "").strip() == CONTAINER_IMAGE:
        match = re.search(r"-(b\d+)$", CONTAINER_IMAGE)
        build_id = match.group(1) if match else CONTAINER_IMAGE.split(":")[-1]
        return {"serving_build": f"llama.cpp {build_id}", "refused": None}
    return {
        "serving_build": None,
        "refused": (
            f"{CONTAINER_IMAGE} is not present on {host}; the output of "
            f"{command!r} was {(raw or '').strip()!r}"
        ),
    }


def release(host: str) -> dict[str, Any]:
    """Stop serving and give up the card. Only this engine's own processes.

    Three steps, for the reason the sibling engines record: each is insufficient
    alone.

    1. Remove our container by NAME. Not by image and not by a filter over
       ``docker ps`` — on srv2 that listing carries four containers of which one
       is ours, and stopping a stranger's server is not this module's business.
    2. Kill any ``llama-server`` still carrying our mount point. A container
       that was killed rather than stopped can leave the child alive for a beat,
       and the card is not free until it is gone.
    3. Settle, then read the card back.

    **``released`` is a statement about THIS backend, not about the card.**
    Reading total VRAM would make a backend that holds nothing report failure
    whenever another engine held the card — which is how the orchestrator's
    exclusion gate came to refuse the very engine it was about to measure. The
    card's own number travels beside it under ``card_used_mib``.

    **The process count is narrowed to ours on purpose, and this engine is the
    one where that matters.** Another engine in this tree also runs
    ``llama-server`` children. A host-wide ``pgrep -c '[l]lama-server'`` — which
    is the right scope for *that* module, whose docstring explains why — would
    here count another engine's child as ours and report ``released: False`` for
    a card we had already let go of. Ours are the ones serving out of
    :data:`CONTAINER_MODELS`.
    """
    steps: list[dict[str, Any]] = []

    def run(name: str, command: str) -> str | None:
        stdout = contract.ssh(host, command)
        steps.append({"step": name, "command": command, "stdout": stdout})
        return stdout

    run(
        "remove_container",
        f"docker rm -f {shlex.quote(CONTAINER_NAME)} >/dev/null 2>&1; true",
    )
    # The bracket is not cosmetic: `pkill -f` matches against its own shell's
    # command line, and an unbracketed pattern kills the ssh session before it
    # kills the server. `sudo -n` because a container's child is root-owned and
    # the ssh user gets EPERM otherwise — silently, if stderr is discarded.
    run(
        "kill_servers",
        f"sudo -n pkill -f '[l]lama-server.*{CONTAINER_MODELS}' 2>/dev/null; "
        "sleep 3; "
        f"echo \"remaining=$(pgrep -cf '[l]lama-server.*{CONTAINER_MODELS}' "
        '2>/dev/null || echo 0)"',
    )
    run("settle", "sleep 5; echo settled")
    gpu = run("gpu_memory", "nvidia-smi --query-gpu=memory.used --format=csv,noheader")
    mine = run(
        "engine_processes",
        f"{{ pgrep -cf '[l]lama-server.*{CONTAINER_MODELS}' 2>/dev/null "
        "|| echo 0; } | head -1",
    )
    boxes = run(
        "engine_containers",
        # Running only, deliberately, and matching this module's own name: a
        # stopped container holds no card, and `_start` removes it before the
        # next launch either way. `readings` takes `-a` so the stopped one is
        # still in the record.
        "docker ps --format '{{.Names}}\t{{.Image}}' 2>/dev/null "
        f"| grep -w {shlex.quote(CONTAINER_NAME)} | head -20 || true",
    )
    # Recorded and gating nothing: every llama-server on the box, ours and
    # anybody's. A reader comparing this with `engine_processes_remaining` sees
    # exactly how many of them belong to another engine — which on these rigs is
    # another engine's children, and is the difference the narrowing is about.
    everyones = run(
        "llama_server_processes_hostwide",
        "{ pgrep -c '[l]lama-server' 2>/dev/null || echo 0; } | head -1",
    )
    killed = next((step for step in steps if step["step"] == "kill_servers"), {})
    after_kill = contract.first_int((killed.get("stdout") or "").split("=")[-1])
    remaining = contract.first_int(mine)
    containers = len([line for line in (boxes or "").splitlines() if line.strip()])
    used = contract.first_int(gpu)
    return {
        "backend": NAME,
        "steps": steps,
        "gpu_used_mib": used,
        "engine_processes_remaining": remaining,
        "engine_containers_remaining": containers,
        "llama_server_processes_hostwide": contract.first_int(everyones),
        "children_after_kill": after_kill,
        "kill_was_effective": None if after_kill is None else after_kill == 0,
        "released": remaining == 0 and containers == 0,
        # A reading of the CARD, kept separate from the statement about this
        # backend, because `claim` needs to know whether the card was clear
        # before a load and must not be handed a process count under that name.
        "card_used_mib": used,
        "card_idle": None if used is None else used < IDLE_BEFORE_LOAD_MIB,
    }


def _props(base: str) -> dict[str, Any] | None:
    """``/props``, the server's own statement of how it was configured."""
    props = contract.get_json(contract.url(base, "/props"), timeout=15.0)
    return props if isinstance(props, dict) else None


def _slot_geometry(props: dict[str, Any] | None) -> dict[str, Any]:
    """``total_slots`` and the per-slot context, as the server reports them.

    Both fields, because neither alone says what a level will get: eight slots
    of 512 tokens and eight slots of 2048 are the same width and different
    instruments, and the ramp's 475 completion tokens fit only one of them.
    """
    if not props:
        return {"total_slots": None, "n_ctx_per_slot": None, "read": False}
    settings = props.get("default_generation_settings")
    per_slot = settings.get("n_ctx") if isinstance(settings, dict) else None
    return {
        "total_slots": props.get("total_slots"),
        "n_ctx_per_slot": per_slot,
        "read": True,
    }


def _gguf_bytes(host: str, model: str) -> int | None:
    """The size of the blob a cell names, in bytes, from the serving host."""
    raw = contract.ssh(host, f"stat -c %s {shlex.quote(model)} 2>/dev/null || true")
    return contract.first_int(raw)


def _available_bytes(host: str) -> int | None:
    """``MemAvailable``, in bytes.

    ``available`` and not ``free``: Linux counts mmap'd page cache as
    reclaimable, and measured on srv1 reading a 12.11 GB GGUF moved `available`
    by 16 MiB while `buff/cache` grew 11.6 GiB. Gating on `free` would refuse
    every cell after the first.
    """
    raw = contract.ssh(
        host, "awk '/MemAvailable/ {print $2 * 1024}' /proc/meminfo || true"
    )
    return contract.first_int(raw)


def mmap_gate(host: str, model: str) -> dict[str, Any]:
    """Refuse a model that cannot be held in RAM, BEFORE it is launched.

    **The gate is on ``available`` at the moment of the check, and the moment
    matters.** Measured on srv1: with a 12.11 GB MoE mmap'd, `available` reads
    about a gigabyte lower than it does once that server is gone. Evaluating
    this while the previous cell is still up therefore refuses a cell that fits.
    :func:`_start` calls it *after* :func:`release`, which is the only ordering
    that reads the memory the model will actually get.

    A refusal here is the campaign's intended outcome for an oversized model,
    not an error to route around: the alternative is a cell that runs, thrashes,
    and reports a disk benchmark as a decode throughput.
    """
    size = _gguf_bytes(host, model)
    available = _available_bytes(host)
    if size is None or available is None:
        return {
            "checked": False,
            "gguf_bytes": size,
            "available_bytes": available,
            "why": (
                "the blob size or MemAvailable could not be read on "
                f"{host}; the gate is recorded as not applied rather than "
                "as passed"
            ),
        }
    budget = available - MMAP_HEADROOM_BYTES
    return {
        "checked": True,
        "gguf_bytes": size,
        "gguf_gb": round(size / 1000**3, 2),
        "available_bytes": available,
        "available_gb": round(available / 1000**3, 2),
        "headroom_bytes": MMAP_HEADROOM_BYTES,
        "budget_bytes": budget,
        "budget_gb": round(budget / 1000**3, 2),
        "fits": size <= budget,
    }


def validate_serve(serve: dict[str, Any]) -> int:
    """Every check on a serving config that needs no host, and the per-slot size.

    **Separated so it can run BEFORE anything is torn down.** ``_start`` opens
    with :func:`release`, which stops whatever is serving; a config error raised
    after that point has already destroyed the previous cell's server to render
    a sentence about a typo. A sibling module records the same lesson from the
    other direction — a pin check placed after its own ``_start`` cost a restart
    and half an hour to say a field name was wrong. :func:`claim` calls this
    first.

    Returns the per-slot context, because the caller needs it and computing it
    is where the validation happens.
    """
    flags = list(serve.get("flags", []))
    if "--no-mmap" in flags or serve.get("no_mmap"):
        raise contract.NotCleanError(
            "`--no-mmap` is refused by this backend. It is a fix for a RAM "
            "shortage, not an optimisation — every srv2 cell measured slower "
            "with it (2026-08-25) — and the MoE gate is what keeps a model "
            "that cannot fit from thrashing. Nothing was measured."
        )
    per_slot = int(serve.get("ctx_per_slot", 2048))
    if per_slot < MIN_CTX_PER_SLOT:
        raise contract.NotCleanError(
            f"ctx_per_slot={per_slot} is below {MIN_CTX_PER_SLOT} — the ramp's "
            f"{contract.RAMP_TOKENS}-token completion budget plus "
            f"{PROMPT_HEADROOM_TOKENS} tokens of room for the prompt. A slot "
            "holds the prompt AND the reply, so a window this small truncates "
            "the generation being timed, and does it silently: the server "
            "answers 200 and reports the tokens it managed, which reads as a "
            "slow model rather than as a context that was too small. Nothing "
            "was measured."
        )
    return per_slot


def _launch_args(model: str, serve: dict[str, Any], width: int) -> list[str]:
    """The command line, with the two flags that are not the caller's to choose.

    ``--parallel`` is forced to ``width`` and ``-c`` is derived from
    ``ctx_per_slot`` times that width, for the reasons in the module docstring.
    Everything else a cell wants — ``-ngl``, ``--n-cpu-moe``, ``-t``, the
    speculative family — passes through as declared.
    """
    per_slot = validate_serve(serve)
    flags = list(serve.get("flags", []))
    n_ctx = int(serve.get("n_ctx", per_slot * width))
    args = [
        # The container's view of the blob. A config names a HOST path, because
        # that is what `inventory` returns and what a reader can stat.
        "-m",
        _container_path(model),
        "--host",
        "0.0.0.0",
        "--port",
        str(PORT),
        "--parallel",
        str(width),
        "-c",
        str(n_ctx),
    ]
    for key, flag in (
        ("ngl", "-ngl"),
        ("n_cpu_moe", "--n-cpu-moe"),
        ("threads", "-t"),
        ("batch_size", "-b"),
        ("ubatch_size", "-ub"),
        ("draft_model", "--spec-draft-model"),
        ("draft_n_max", "--spec-draft-n-max"),
        ("ngram_size_n", "--spec-ngram-simple-size-n"),
        ("ngram_size_m", "--spec-ngram-simple-size-m"),
    ):
        if serve.get(key) is not None:
            args += [flag, str(serve[key])]
    return args + flags


def _container_path(model: str) -> str:
    """A host blob path as the container sees it."""
    if "/models/" in model:
        return CONTAINER_MODELS + "/" + model.split("/models/", 1)[1]
    return f"{CONTAINER_MODELS}/{model.lstrip('/')}"


def _host_path(host: str, model: str) -> str:
    """The inverse of :func:`_container_path` — what the HOST can ``stat``.

    ``/props`` answers with the path the server sees, which is inside the
    mount. Measured live on srv2: :func:`placements` fed that container path
    straight to ``stat`` on the host, got nothing, and reported
    ``fraction: None`` for a model whose size was perfectly readable — the one
    number this engine can report and its sibling cannot, silently absent.
    """
    if not model.startswith(CONTAINER_MODELS + "/"):
        return model
    tail = model[len(CONTAINER_MODELS) + 1 :]
    root = contract.ssh(host, f"printf %s {HOST_MODELS}")
    return f"{(root or '').strip() or '/home/adaramir/models'}/{tail}"


def _launch_log(host: str) -> str:
    """The server's own last lines, read on a failure and before the next
    launch's ``docker rm -f`` destroys them."""
    raw = contract.ssh(
        host,
        f"docker logs --tail {LAUNCH_LOG_LINES} {shlex.quote(CONTAINER_NAME)} "
        "2>&1 | tail -n " + str(LAUNCH_LOG_LINES) + " || true",
    )
    return contract.scrub(raw or "")


def _start(host: str, model: str, serve: dict[str, Any], width: int) -> dict[str, Any]:
    """Launch the server with ``serve``, and wait for it to answer.

    Ordering is the whole of the correctness here and each step is where it is
    for a stated reason:

    1. :func:`release` first, so the card and the RAM the next two steps read
       are the ones this model will actually get.
    2. :func:`mmap_gate` second, on that freed memory — never on memory the
       previous cell is still holding.
    3. Launch, then read ``total_slots`` back and refuse a width we did not get.
    """
    freed = release(host)
    gate = mmap_gate(host, model)
    if gate.get("checked") and not gate.get("fits"):
        raise contract.NotCleanError(
            f"{model} is {gate['gguf_gb']} GB and {host} has "
            f"{gate['available_gb']} GB available, leaving a budget of "
            f"{gate['budget_gb']} GB after {MMAP_HEADROOM_BYTES / 1000**3:.0f} GB "
            "of headroom. mmap'd past `available` the server thrashes instead "
            "of refusing, and the throughput it then reports is a disk "
            "benchmark. Nothing was measured, and this is a refusal rather "
            "than an error."
        )
    args = _launch_args(model, serve, width)
    environment = serve.get("env", {})
    for key in environment:
        if not key.replace("_", "").isalnum() or key[:1].isdigit():
            raise contract.NotCleanError(
                f"{key!r} is not a usable environment variable name. Serving "
                "config is interpolated into a shell on the serving host, so a "
                "name is held to letters, digits and underscores rather than "
                "escaped into something no shell would set."
            )
    environment_flags = " ".join(
        f"-e {shlex.quote(f'{key}={value}')}" for key, value in environment.items()
    )
    command = (
        f"docker rm -f {shlex.quote(CONTAINER_NAME)} >/dev/null 2>&1; "
        f"docker run -d --name {shlex.quote(CONTAINER_NAME)} "
        "--runtime=nvidia --gpus all "
        f"-v {HOST_MODELS}:{CONTAINER_MODELS} "
        f"-p {PORT}:{PORT} {environment_flags} {CONTAINER_IMAGE} "
        + " ".join(shlex.quote(arg) for arg in args)
    )
    began = time.monotonic()
    launched = contract.ssh(host, command)
    # The loop's worst case is (curl 5s + sleep 10s) per round, so the ssh
    # budget covers THAT and not START_TIMEOUT_S alone — a slow start cut off by
    # the client is recorded as a server that never came up.
    rounds = int(START_TIMEOUT_S // 20)
    ready = contract.ssh(
        host,
        f"for i in $(seq 1 {rounds}); do "
        f"code=$(curl -s -m 5 -o /dev/null -w '%{{http_code}}' "
        f"http://127.0.0.1:{PORT}/health); "
        '[ "$code" = "200" ] && { echo ready; exit 0; }; sleep 10; done; '
        'echo "timeout code=$code"',
        timeout=START_TIMEOUT_S + 120,
    )
    # Asserted, not merely recorded: a server that never came up must not be
    # measured against anyway.
    if (ready or "").split()[:1] != ["ready"]:
        tail = _launch_log(host)
        raise contract.NotCleanError(
            f"llamacpp on {host} did not reach health inside "
            f"{START_TIMEOUT_S:.0f}s: {contract.scrub(ready)!r}. Nothing was "
            "measured. The known causes here are a GGUF larger than the card "
            "at the requested `-ngl`, and a cold page cache on a large MoE. "
            f"The server's own last {LAUNCH_LOG_LINES} log lines, read on the "
            f"failure and before the next launch removes them: {tail!r}"
        )
    return contract.scrub(
        {
            "restarted": True,
            "command": command,
            "launched": launched,
            "ready": ready,
            "released_first": freed,
            "mmap_gate": gate,
            # Every launch adds a point to the only dataset that could ever
            # calibrate START_TIMEOUT_S, at no cost.
            "start_seconds": round(time.monotonic() - began, 2),
            "serve": serve,
        }
    )


def claim(
    host: str,
    base: str,
    model: str,
    serve: dict[str, Any] | None = None,
    expect: dict[str, Any] | None = None,
    **declared: Any,
) -> dict[str, Any]:
    """Be serving ``model`` under ``serve``, and prove it — width included.

    ``**declared`` absorbs the per-entry declarations the orchestrator forwards
    for backends that model them (``placement``, ``coresident``,
    ``coresident_with``). What is ignored is written down rather than dropped,
    because an entry that believes it declared something nothing reads is worse
    than one that was told.

    **The width assertion is the point of this function.** A launch that asked
    for eight slots and got four will serve every request, answer ``200`` on
    every probe, and produce a ramp whose n=8 aggregate equals its n=4 — a
    plateau that reads as hardware saturation and is a flag that did not take.
    So ``total_slots`` is read back off ``/props`` and a shortfall is a refusal.
    """
    serve = serve or {}
    expect = expect or {}
    ignored = {key: value for key, value in declared.items() if value}
    unknown = set(expect) - {"total_slots", "n_ctx_per_slot", "gguf_sha256"}
    if unknown:
        raise contract.NotCleanError(
            f"{model} on {host}: {sorted(unknown)} is not this backend's pin. "
            "This engine pins `total_slots` and `n_ctx_per_slot`, both read "
            "from the server's own /props. Nothing was measured, and nothing "
            "was restarted."
        )
    # The width the ramp will actually offer. A cell that measures n=8 must
    # launch with at least eight slots, and this is the only place that knows
    # both numbers.
    levels = tuple(serve.get("levels") or contract.RAMP_LEVELS)
    width = int(serve.get("parallel", max(levels)))
    if width < max(levels):
        raise contract.NotCleanError(
            f"parallel={width} is below the widest level this cell will offer "
            f"(n={max(levels)}). llama-server runs the excess as a second "
            "sequential batch, so the aggregate flatlines while latency "
            "doubles — a configuration artifact shaped exactly like hardware "
            "saturation. Nothing was measured."
        )
    # BEFORE anything ACTS. `_start` opens with `release`, so a config error
    # raised inside it has already stopped the previous cell's server in order
    # to complain about a typo.
    validate_serve(serve)
    claim_started_at = contract.now()
    started = _start(host, model, serve, width)
    base = f"http://{host}:{PORT}"

    props = _props(base)
    geometry = _slot_geometry(props)
    gpu = contract.ssh(host, "nvidia-smi --query-gpu=memory.used --format=csv,noheader")
    allocated = contract.first_int(gpu)
    card = contract.card_state(contract.ssh(host, contract.CARD_STATE_COMMAND))

    got = geometry.get("total_slots")
    if got is None:
        raise contract.NotCleanError(
            f"{model} on {host} came up but /props did not answer "
            "`total_slots`, so the width this cell was measured at is "
            "unknown. A ramp whose slot count cannot be stated cannot "
            "distinguish saturation from a flag that did not take. Nothing "
            "was measured."
        )
    if int(got) < max(levels):
        raise contract.NotCleanError(
            f"{model} on {host} was launched with --parallel {width} but "
            f"/props reports total_slots={got}, below the widest level "
            f"n={max(levels)}. The engine reduced the width it was given — "
            "usually because the KV cache for that many slots did not fit the "
            "card. Measuring here would record two sequential batches as a "
            "plateau. Nothing was measured."
        )
    per_slot = geometry.get("n_ctx_per_slot")
    if per_slot is not None and int(per_slot) < MIN_CTX_PER_SLOT:
        raise contract.NotCleanError(
            f"{model} on {host} came up with {per_slot} tokens per slot, below "
            f"{MIN_CTX_PER_SLOT} (the ramp's {contract.RAMP_TOKENS}-token "
            f"completion budget plus {PROMPT_HEADROOM_TOKENS} for the prompt). "
            "Read back from /props, so this is what the slots ACTUALLY got "
            "after `-c` was divided by the width — not what was asked for. "
            "Every timed generation would be cut short by the window rather "
            "than by max_tokens. Raise `ctx_per_slot`. Nothing was measured."
        )
    for pin, value in expect.items():
        if pin in ("total_slots", "n_ctx_per_slot"):
            actual = geometry.get(pin)
            if actual is None or int(actual) != int(value):
                raise contract.NotCleanError(
                    f"{model} on {host}: pinned {pin}={value}, /props reports "
                    f"{actual}. Nothing was measured."
                )
    return {
        "backend": NAME,
        "model": model,
        "started": started,
        "claim_started_at": claim_started_at,
        "props": props,
        # Hoisted, because this is what a reader of the curve needs beside it
        # and it is the field the whole module is organised around.
        "slot_geometry": geometry,
        "parallel_requested": width,
        "levels_to_offer": list(levels),
        "card_used_mib": allocated,
        "card": card,
        "ignored_declarations": ignored or None,
    }


def slots_now(host: str) -> dict[str, Any]:
    """This host's declared slot count, without a full :func:`describe`.

    The ramp needs the same number the survey records and cannot pay for a
    capture to get it. For this engine the value is genuinely observed — the
    server states it on ``/props`` — and it is the number a caller asserts
    ``total_slots >= max(levels)`` against.
    """
    return declared_slots(_props(f"http://{host}:{PORT}"))


def declared_slots(props: dict[str, Any] | None) -> dict[str, Any]:
    """What this engine SAYS its width is — never what the curve did.

    A scheduler limit and a throughput saturation point are different
    quantities that coincide only when the limit binds before the hardware
    does, so they are different fields. This is the limit; the curve is
    :func:`contract.saturation`.

    The provenance travels with the value because it is not observable on every
    engine: here it is read, and a consumer that could not tell a reading from
    an intention would be comparing the two across backends.
    """
    geometry = _slot_geometry(props)
    if not geometry["read"]:
        return {
            "slots": None,
            "provenance": "unavailable",
            "why": f"/props did not answer on port {PORT}",
        }
    return {
        "slots": geometry["total_slots"],
        "n_ctx_per_slot": geometry["n_ctx_per_slot"],
        "provenance": "observed",
        "source": "/props total_slots",
        "why": (
            "llama-server states its own width; it is set from --parallel "
            "where given and from the engine's default of 4 where not"
        ),
    }


def residents(host: str) -> list[str]:
    """The model this engine is serving, if any.

    One entry at most: ``llama-server`` binds a single model for the life of the
    process, which is why there is no unload here and why :func:`release` stops
    the server rather than evicting a model from it.
    """
    props = _props(f"http://{host}:{PORT}")
    if not props:
        return []
    path = props.get("model_path") or props.get("model")
    return [str(path)] if path else []


def placements(host: str) -> list[dict[str, Any]]:
    """Where this engine's model sits, as far as it can say.

    This engine genuinely *spills* — a model runs with some layers on the card
    and the rest in host RAM, which is what ``-ngl`` and ``--n-cpu-moe``
    select — so unlike an all-or-nothing allocator there is a real question
    here about how much of it is resident.

    **``fraction`` is nonetheless ``None``, and that is a correction rather
    than a gap.** The obvious number, ``card_mib`` over the blob's size, is not
    the share of the weights on the card: the driver attributes the process's
    WHOLE allocation, which is weights plus the KV cache plus the CUDA context.
    Measured live on srv2 — a 1.93 GB blob at ``-ngl 99`` with 8 slots of 2048
    read 2618 MiB, a "fraction" of **1.42**. A number above one is the
    harmless case, because it is visibly wrong; the damaging case is a MoE
    under ``--n-cpu-moe`` landing at, say, 0.7 and being read as "70% of the
    weights are resident" when the KV is most of what is being counted.

    The sibling engine reports a weights-only share under this name, taken from
    its own accounting rather than from the driver. Publishing a
    differently-defined number under the same key is exactly the cross-engine
    comparison the record is supposed to make impossible, so the ratio is
    reported under its own name with its terms stated, and ``fraction`` carries
    the refusal.
    """
    props = _props(f"http://{host}:{PORT}")
    if not props:
        return []
    model = props.get("model_path") or props.get("model")
    raw = contract.ssh(
        host,
        "nvidia-smi --query-compute-apps=pid,used_gpu_memory "
        "--format=csv,noheader,nounits 2>/dev/null || true",
    )
    rows: list[dict[str, Any]] = []
    for line in (raw or "").splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 2:
            continue
        pid = contract.first_int(parts[0])
        mib = contract.first_int(parts[1])
        owner = contract.ssh(
            host, f"ps -o args= -p {pid} 2>/dev/null | head -1 || true"
        )
        if CONTAINER_MODELS not in (owner or ""):
            continue
        # The HOST path: /props answers with the container's view, and `stat`
        # runs on the host. See :func:`_host_path`.
        size = _gguf_bytes(host, _host_path(host, str(model))) if model else None
        rows.append(
            {
                "name": str(model) if model else None,
                "pid": pid,
                "card_mib": mib,
                "blob_bytes": size,
                # Named for what it actually divides, and it can exceed 1.
                "card_over_blob": (
                    None if not size or mib is None else round(mib * 1024**2 / size, 4)
                ),
                "card_over_blob_note": (
                    "the driver's whole allocation for the process — weights "
                    "AND the KV cache AND the CUDA context — over the blob's "
                    "size on disk. Exceeds 1.0 whenever the KV cache is large "
                    "relative to the weights, so it is NOT the share of the "
                    "model that is resident"
                ),
                "fraction": None,
                "fraction_refused": (
                    "the weights-only share is not observable from the driver "
                    "here, and the sibling engine publishes a weights-only "
                    "number under this key; see `card_over_blob`"
                ),
                "backend": NAME,
            }
        )
    if not rows and model:
        rows.append(
            {
                "name": str(model),
                "pid": None,
                "card_mib": None,
                "fraction": None,
                "unplaced": (
                    "served by this engine and attributed no memory by the "
                    "driver; the process holding the card for it was not "
                    "found, which is unknown rather than zero"
                ),
                "backend": NAME,
            }
        )
    return rows


#: This engine's defining flags, which this engine cannot read back.
#:
#: ``-ngl``, ``--n-cpu-moe`` and ``-t`` decide *where each layer is computed*,
#: which is the axis this whole campaign varies. Since 2026-09-03 they are in
#: the shared fingerprint's SEMANTIC set (ADR-0041: ``--n-cpu-moe`` 0 against
#: 99 on one build moved 9 of 257 verdicts, so placement is semantic until a
#: placement null shows otherwise). What this engine cannot do is *read* them:
#: ``/props`` reports none of them, and a value this module typed in from the
#: launch command would be a declaration wearing a reading's clothes.
#:
#: So they are held out of the digest and recorded beside it under
#: ``uncovered_by_digest``, with this note. **Two cells differing only in
#: ``--n-cpu-moe`` therefore share a semantic digest from this engine**, which
#: is a reading gap, stated in the record rather than papered over. The launch
#: command in ``claim.started.command`` carries the actual values; closing the
#: gap is a server that reports them, or a reader of that command.
ENGINE_FLAGS_NOT_IN_DIGEST = ("n_gpu_layers", "n_cpu_moe", "threads", "mmap")


def serving_config(props: dict[str, Any] | None) -> dict[str, Any]:
    """The settings that decide what a curve means, as the shared fingerprint.

    Width and per-slot context are the two a cross-engine comparison has to
    match and the two this engine silently defaults, so they lead. The digest
    is the shared one — the same function the sibling engines pass their
    configuration through — so two cells are comparable by construction rather
    than by a reader lining up fields.

    See :data:`ENGINE_FLAGS_NOT_IN_DIGEST` for what this deliberately does not
    cover, and why that is recorded rather than fixed here.
    """
    geometry = _slot_geometry(props)
    settings = (props or {}).get("default_generation_settings")
    settings = settings if isinstance(settings, dict) else {}
    # Only keys the shared classifier knows. `n_ctx` is the PER-SLOT window,
    # which is the one that decides whether a reply fits — not the `-c` total,
    # which is that number times the width and would compare two servers of
    # different widths as though they were the same instrument.
    config: dict[str, Any] = {
        "n_ctx": geometry["n_ctx_per_slot"],
        "total_slots": geometry["total_slots"],
        "n_parallel": geometry["total_slots"],
    }
    for key, value in (
        ("seed", settings.get("seed")),
        ("chat_template", bool((props or {}).get("chat_template"))),
        ("model_ftype", (props or {}).get("model_ftype")),
        ("build_info", (props or {}).get("build_info")),
    ):
        if value is not None:
            config[key] = value
    block: dict[str, Any] = {
        "model_path": (props or {}).get("model_path"),
        "n_ctx_per_slot": geometry["n_ctx_per_slot"],
        "n_ctx_total": (
            None
            if geometry["total_slots"] is None or geometry["n_ctx_per_slot"] is None
            else int(geometry["total_slots"]) * int(geometry["n_ctx_per_slot"])
        ),
        "mmap": True,
        "mmap_why": "this backend never passes --no-mmap; see the module docstring",
        "uncovered_by_digest": list(ENGINE_FLAGS_NOT_IN_DIGEST),
        "uncovered_why": (
            "-ngl, --n-cpu-moe and -t decide where each layer is computed, "
            "which is the axis this campaign varies. They are SEMANTIC in the "
            "shared fingerprint (ADR-0041) and /props does not report them, "
            "so this engine cannot put them in the digest: two cells differing "
            "only in expert offload share a semantic digest from this engine, "
            "and are NOT comparable on output. The launch command in "
            "`claim.started.command` carries the actual values."
        ),
    }
    try:
        block["fingerprint"] = fingerprint.fingerprint(config)
    except fingerprint.UnclassifiedError as error:
        block["fingerprint"] = {"refused": str(error), "parsed": config}
    return block


def describe(
    host: str,
    base: str,
    model: str,
    serve: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Everything this engine will say about ``model``."""
    props = _props(base)
    return {
        "backend": NAME,
        "capture": contract.observed().capture(base, model),
        "resident": residents(host),
        "props": props,
        "serving_config": serving_config(props),
        "declared_slots": declared_slots(props),
        "placements": placements(host),
    }
