#!/usr/bin/env python3
"""The vLLM backend: how this engine yields the card, takes it, and describes itself.

Implements the contract in :mod:`contract`. **This file names no other
backend's module and must not**: it knows how to stop being on the GPU and how
to get itself onto it, and who else wants the card is the orchestrator's
decision, never this module's.

**This engine claims the card for the life of the process, not per model.** It
allocates its whole budget at startup — weights, then KV cache filling the rest —
and holds it whether or not a request is in flight. That budget is declared in
**bytes of KV cache** or as a fraction of the card (:func:`_memory_args`);
``requested = total_memory * util`` means one fraction is a different KV cache
on every card it is carried to.

So :func:`claim` is not "load a model" but "be running, with these serving
parameters, and prove it": an *empty* card means the server died.

**One flag decides how much this engine will say about itself.**
``/server_info`` carries the quantization, the seed and the served window, and
exists only when the server was launched with ``VLLM_SERVER_DEV_MODE=1``.
:func:`_start` sets it deliberately.

**The batch width is read off the server's own argv** (:func:`launched_width`).
On ``CONTAINER_IMAGE``'s build, ``/server_info?config_format=json`` also
carries it, under ``scheduler_config``; no code here reads it there, and the
text form that :func:`_running_config` parses leaves it out.
``kv_cache_max_concurrency`` on ``/metrics`` looks like the answer and is
KV-cache capacity — see :func:`declared_slots`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import sys
import time
import types
from pathlib import Path
from typing import Any


def _contract() -> types.ModuleType:
    """The shared contract, by path — ``tools/`` has no ``__init__.py``.

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

NAME = "vllm"

#: The port this engine ships on.
PORT = 8000

#: The base of the readiness wait: :func:`_start` polls ``START_TIMEOUT_S // 20``
#: times, each a curl of at most 5 s, an `nvidia-smi` with no time limit and a
#: 10 s sleep, under an ssh timeout of ``START_TIMEOUT_S + 120``. Launch
#: timings: `records/evidence/2026-08-24-config-sweep/`.
START_TIMEOUT_S = 900.0

#: Lines of the engine's own log kept beside a launch that never became ready.
#: Enough to hold a vLLM traceback together with the line naming the allocation
#: it died on; this text is scrubbed and written to the record, so more is a
#: wall.
LAUNCH_LOG_LINES = 40

#: How long a weights digest may take. The digest is a separate process over
#: the checkpoint files (`_DIGEST_SCRIPT`): it never starts an engine and no
#: serve flag reaches it. Timed points:
#: `records/evidence/2026-08-23-cross-rig/`.
DIGEST_TIMEOUT_S = 1800.0

#: Hashed on the serving host, because the checkpoint is there and the client
#: is not. Tensor-wise in sorted key order across every shard, so the digest is
#: a property of the WEIGHTS rather than of how they happen to be sharded or
#: laid out — two identical models split into different numbers of files hash
#: the same, and a re-quantization does not.
#:
#: The result is cached in-process per ``(host, model)`` rather than recomputed
#: per survey.
_DIGEST_SCRIPT = r"""
import hashlib, json, os, sys, glob

model = sys.argv[1]
hub = os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")
folder = "models--" + model.replace("/", "--")
roots = glob.glob(os.path.join(hub, "hub", folder, "snapshots", "*"))
if not roots:
    # A local path is as valid a model id as a hub name.
    roots = [model] if os.path.isdir(model) else []
if not roots:
    print(json.dumps({"error": "no snapshot for " + model + " under " + hub}))
    raise SystemExit(0)
# NEWEST by mtime, not last alphabetically: a snapshot directory is named by
# commit hash, so sorting them lexicographically picks an arbitrary revision
# and would silently hash a stale one after an update.
snapshot = max(roots, key=os.path.getmtime)
shards = sorted(glob.glob(os.path.join(snapshot, "*.safetensors")))
if not shards:
    print(json.dumps({"error": "no safetensors in " + snapshot}))
    raise SystemExit(0)
try:
    import torch
    from safetensors import safe_open
except ImportError as exc:
    print(json.dumps({"error": "safetensors unavailable: " + str(exc)}))
    raise SystemExit(0)

digest = hashlib.sha256()
tensors = 0
size = 0
try:
    for shard in shards:
        size += os.path.getsize(os.path.realpath(shard))
        with safe_open(shard, framework="pt", device="cpu") as handle:
            for key in sorted(handle.keys()):
                tensor = handle.get_tensor(key)
                # `.numpy()` REFUSES bfloat16 and `untyped_storage()` is worse
                # than wrong: safetensors MMAPS the shard, so a tensor is a view
                # into the whole file and its storage is the entire mapping —
                # hashing it would digest the file once per tensor. Reinterpret
                # the tensor's own elements as bytes instead.
                flat = tensor.flatten().contiguous().view(torch.uint8)
                digest.update(flat.numpy().tobytes())
                tensors += 1
except Exception as exc:
    print(json.dumps({"error": type(exc).__name__ + ": " + str(exc)}))
    raise SystemExit(0)
print(json.dumps({
    "weights_sha256": digest.hexdigest(),
    "snapshot": snapshot,
    "shards": [os.path.basename(s) for s in shards],
    "tensors": tensors,
    "bytes": size,
    "mtime": max(os.path.getmtime(os.path.realpath(s)) for s in shards),
}))
"""

#: In-process cache, keyed by ``(host, model)``. The digest is a property of the
#: checkpoint on disk, not of a run, so hashing it twice in one survey is pure
#: waste — and a survey that re-hashed per model per host would spend minutes.
_DIGEST_CACHE: dict[tuple[str, str], dict[str, Any]] = {}

#: Below this the card is empty, which for this engine means the server is not
#: holding its allocation — the opposite of the idle check an engine that loads
#: per request would make.
MIN_ALLOCATION_MIB = contract.IDLE_GPU_MIB


def probe(host: str) -> str | None:
    """The base URL this engine answers on, or ``None``. Read-only."""
    base = f"http://{host}:{PORT}"
    return base if contract.get_json(contract.url(base, "/v1/models")) else None


def inventory(host: str, base: str) -> list[str]:
    """The model ids this engine is serving. It serves what it was launched with."""
    cards = contract.get_json(contract.url(base, "/v1/models"), timeout=20.0)
    rows = (cards or {}).get("data") if isinstance(cards, dict) else None
    if not isinstance(rows, list):
        return []
    return [str(row.get("id")) for row in rows if isinstance(row, dict)]


#: What the process holding the card is called. vLLM renames its GPU worker,
#: so the process ``nvidia-smi`` attributes the memory to has a command line of
#: exactly this — **no model, no flags, nothing to join on** — which is why
#: :func:`_owner` walks to the parent instead of matching the pid's own line.
ENGINE_CORE = "VLLM::EngineCore"

#: The process read this backend takes to attribute the card. Narrow on purpose:
#: a full ``ps -eo args`` dump is the densest credential surface on the host, and
#: only this engine's own processes can be attributed to a model here anyway.
#:
#: **The brackets are load-bearing**, for the reason :func:`release`'s patterns
#: carry them: without them the pattern matches the shell running the pattern,
#: and this read would report a process that is this read.
PROCESS_TREE_COMMAND = (
    "ps -eo pid=,ppid=,args= | "
    "grep -E '[V]LLM::EngineCore|[v]llm serve|[v]llm[.]entrypoints' || true"
)

#: How far up the parent chain a compute-app pid is followed before the answer
#: is ``None``.
_OWNER_HOPS = 3


def _process_tree(raw: str | None) -> dict[int, dict[str, Any]]:
    """:data:`PROCESS_TREE_COMMAND`'s output as ``{pid: {"ppid", "args"}}``.

    A pure parser over what the host printed, so the join it feeds is testable
    without a host.
    """
    tree: dict[int, dict[str, Any]] = {}
    for line in (raw or "").splitlines():
        parts = line.split(None, 2)
        if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        tree[int(parts[0])] = {
            "ppid": int(parts[1]),
            "args": parts[2] if len(parts) > 2 else "",
        }
    return tree


def _served_name(args: str) -> str | None:
    """The model a ``vllm`` command line serves, under the name it answers to.

    ``--served-model-name`` first, because that — not the checkpoint path — is
    what ``/v1/models`` returns, and this name is joined against that list. Then
    ``--model``, the ``api_server`` shape. Then the positional of ``vllm serve
    <model>``, whatever path the ``vllm`` binary sits under, so one join covers
    a pip install and a container.
    """
    try:
        tokens = shlex.split(args)
    except ValueError:
        tokens = args.split()
    for flag in ("--served-model-name", "--model"):
        for index, token in enumerate(tokens):
            if token == flag and index + 1 < len(tokens):
                return tokens[index + 1]
            if token.startswith(f"{flag}="):
                return token.split("=", 1)[1]
    for index in range(1, len(tokens) - 1):
        previous = os.path.basename(tokens[index - 1])
        if tokens[index] == "serve" and previous.startswith("vllm"):
            candidate = tokens[index + 1]
            return None if candidate.startswith("-") else candidate
    return None


def _owner(pid: int, tree: dict[int, dict[str, Any]]) -> str | None:
    """The model the process holding the card is serving, or ``None``.

    ``None`` is the answer whenever the chain runs out, the parent has exited,
    or the line names no model — a pid this engine cannot attribute is not this
    engine's, and it is never *guessed* to be. Another engine's process sharing
    the card arrives here and leaves as ``None``: naming it would be this
    backend claiming about another engine's model.
    """
    seen: set[int] = set()
    current = pid
    for _ in range(_OWNER_HOPS + 1):
        row = tree.get(current)
        if row is None or current in seen:
            return None
        seen.add(current)
        found = _served_name(row["args"])
        if found is not None:
            return found
        current = row["ppid"]
    return None


def residents(host: str) -> list[str]:
    """The models this engine is serving here — its half of a shared card.

    A scheduler-shaped engine answers this from its own list of loaded models.
    This engine has no such list: it is **one process per model**, and
    ``/v1/models`` is a served-model list belonging to the process that answers
    it. So "resident" here means "being served by a vLLM server on this host",
    which is the same question and not the same reading.

    Public, because ``run.py`` calls it after a successful ramp of an entry
    that declares ``coresident_with``. It answers about this engine only.
    """
    base = probe(host)
    return [] if base is None else inventory(host, base)


def placements(host: str) -> list[dict[str, Any]]:
    """Where every process on this card sits, as far as this engine can say.

    **``fraction`` is ``None`` on every row, and that is a decision, not a
    gap.** vLLM takes its whole allocation or refuses to start
    (``requested = ceil(total * util)`` with a hard ``free >= requested``
    precondition), so there is no partial placement to divide, and every row
    carries the reason beside the ``None``.

    The absolute number is reported instead, in MiB, from the driver. A holder
    this engine cannot name is reported as a row rather than dropped.

    MiB and not bytes: ``nvidia-smi`` attributes per-process memory to the MiB,
    so a byte count here would be precision nobody measured.

    Raises rather than returning ``[]`` when the card's process list could not
    be read at all: an empty list is a statement that the card holds nothing.
    """
    apps = contract.compute_apps(contract.ssh(host, contract.COMPUTE_APPS_PROBE))
    if apps is None:
        raise contract.NotCleanError(
            f"the card's process list on {host} could not be read "
            f"({contract.COMPUTE_APPS_COMMAND!r} printed nothing and no "
            "sentinel), so where anything sits here is unknown. An empty list "
            "would say the card is empty, which is a different fact."
        )
    tree = _process_tree(contract.ssh(host, PROCESS_TREE_COMMAND))
    rows: list[dict[str, Any]] = []
    named: set[str] = set()
    for app in apps:
        model = _owner(app["pid"], tree)
        if model is not None:
            named.add(model)
        rows.append(
            {
                "name": model,
                "pid": app["pid"],
                "card_mib": app["card_mib"],
                "fraction": None,
                "fraction_refused": (
                    "this engine allocates its whole budget or refuses to "
                    "start, so a model is never partly on the card and there "
                    "is no denominator"
                ),
                **(
                    {}
                    if model is not None
                    else {
                        "unnamed": (
                            "no vllm command line on this host owns this pid, "
                            "so it is a holder this engine cannot name — not a "
                            "model of ours, and not guessed to be one"
                        )
                    }
                ),
            }
        )
    # A model that is being served but holds no row of the card is the other
    # direction of the same silence: the server answered `/v1/models` and the
    # driver attributed nothing to it. Recorded with `card_mib: None`, because
    # absent is not zero.
    for model in residents(host):
        if model not in named:
            rows.append(
                {
                    "name": model,
                    "pid": None,
                    "card_mib": None,
                    "fraction": None,
                    "fraction_refused": (
                        "this engine allocates its whole budget or refuses to "
                        "start, so a model is never partly on the card and "
                        "there is no denominator"
                    ),
                    "unplaced": (
                        "served by this engine and attributed no memory by the "
                        "driver; the process holding the card for it was not "
                        "found, which is unknown rather than zero"
                    ),
                }
            )
    return rows


def _recorded_placements(host: str) -> tuple[list[dict[str, Any]] | None, str | None]:
    """:func:`placements`, as a pair a record can hold either way.

    Recording, not gating: a reading that cannot be taken must never be the
    reason a measurement does not happen, and `None` beside its reason is what
    that looks like. Broad on purpose — every exception here is a failure to
    observe, and there is no shape of it that should end a claim.
    """
    try:
        return placements(host), None
    except Exception as error:
        return None, f"{type(error).__name__}: {error}"


def readings(host: str) -> dict[str, Any]:
    """This engine's own footprint on the machine.

    **`-a` here, and nowhere else in this module.** A stopped container holds
    no card, no port and no process, and :func:`_start` removes it before every
    launch. It is still there and still named, so this reading lists it.

    **What this listing holds is every container whose image string names this
    engine's repository** (a `grep`, not `--filter ancestor=`), not every
    container this project created. `mcgyvr-vllm` is the only name
    :func:`_start` gives a container of ours.

    It is recorded, not gated. The count :func:`release` returns stays
    running-only — the record sees more than the gate acts on, and that
    asymmetry is the point rather than an oversight.

    The other two `docker ps` calls in this module must NOT take `-a`:
    :func:`release` counts only what is running, and :func:`launched_width`
    reads a width off the live container, where a stopped one would answer with
    a stale one.
    """
    reads = {
        "processes": "ps -eo args | grep -E '[v]llm (serve|.*api_server)' || true",
        # Matched on the repository rather than the pinned tag, for the reason
        # :data:`CONTAINER_REPOSITORY` records.
        "containers": "docker ps -a --format "
        "'{{.Names}} {{.Image}} {{.Status}}' 2>/dev/null "
        f"| grep {shlex.quote(CONTAINER_REPOSITORY + ':')} | head -10 || true",
    }
    out: dict[str, Any] = {
        name: {
            "command": command,
            "stdout": contract.scrub(contract.ssh(host, command)),
        }
        for name, command in reads.items()
    }
    for container in _container_names(out):
        command = (
            f"docker inspect {shlex.quote(container)} "
            "--format '{{json .Config.Cmd}} {{json .Config.Env}}'"
        )
        # `.Config.Env` is the single densest place a key can be on this host.
        out[f"inspect:{container}"] = {
            "command": command,
            "stdout": contract.scrub(contract.ssh(host, command)),
        }
    return out


def _classify_containers(listing: str | None) -> list[dict[str, Any]]:
    """`name\timage` lines as rows, with the one that is ours marked (#355).

    Parsed here rather than counted in the shell for two reasons. The record
    has to show a reader WHICH containers the gate counted — "two" is not an
    answer an operator can act on — and the one container that is ours has to
    be tellable from the ones that are not, by the only thing that
    distinguishes them: the name :func:`_start` assigns.

    **Stated limit.** A container started from a bare image ID prints that ID
    as its image, and no repository string appears in the line, so it is not
    matched. So is a vLLM served from an image with another name entirely — a
    local build, a fork, a mirror. Neither is detectable from a name and a
    repository, and both would hold the card. The card reading beside this
    (`card_used_mib`) is where such a server shows up, and it is deliberately
    not part of `released`: a backend holding nothing must not report failure
    because another process holds the card.
    """
    rows: list[dict[str, Any]] = []
    for line in (listing or "").splitlines():
        name, tab, image = line.partition("\t")
        if not tab or not name.strip():
            continue
        rows.append(
            {
                "name": name.strip(),
                "image": image.strip(),
                "ours": name.strip() == CONTAINER_NAME,
            }
        )
    return rows


def release(host: str) -> dict[str, Any]:
    """Stop serving and give up the card. Only this engine's own processes.

    Three process shapes, because covering fewer leaves the card held:
    ``vllm serve``, the ``vllm.entrypoints`` module form, and the engine core,
    which is a third name again.

    The bracket in each pattern keeps ``pkill -f`` from matching its own
    shell's command line.
    """
    steps: list[dict[str, Any]] = []

    def run(name: str, command: str) -> str | None:
        stdout: str | None = contract.ssh(host, command)
        steps.append({"step": name, "command": command, "stdout": stdout})
        return stdout

    # Stopped by NAME, never by image: what we started is what we stop, and
    # :data:`CONTAINER_NAME` is the whole of what we started.
    run(
        "stop_container",
        f"docker stop {shlex.quote(CONTAINER_NAME)} >/dev/null 2>&1; true",
    )
    run(
        "kill_processes",
        "pkill -f '[v]llm serve' 2>/dev/null; "
        "pkill -f '[v]llm.entrypoints' 2>/dev/null; "
        "pkill -f '[V]LLM::EngineCore' 2>/dev/null; sleep 8; true",
    )
    gpu = run("gpu_memory", "nvidia-smi --query-gpu=memory.used --format=csv,noheader")
    # `released` is a statement about THIS backend, not about the card. Host
    # processes and running containers are both counted.
    mine = run(
        "engine_processes",
        # `-f`: without it `pgrep` matches the process NAME, which can never
        # contain a space. The three patterns are the three this function kills.
        "{ pgrep -cf '[v]llm serve|[v]llm[.]entrypoints|[V]LLM::EngineCore' "
        "2>/dev/null || echo 0; } | head -1",
    )
    boxes = run(
        "engine_containers",
        # **Running only, deliberately.** `released` is the orchestrator's
        # exclusion gate, and what it must decide is whether anything of this
        # engine still holds the card. A stopped container holds none of it, and
        # `_start` removes it before the next launch either way;
        # :func:`readings` takes `-a` so the stopped one is still in the record.
        #
        # Matched on the repository, not on the pinned tag, for the reason
        # :data:`CONTAINER_REPOSITORY` records. Names and images both, because
        # the record has to show a reader which containers the gate counted.
        "docker ps --format '{{.Names}}\t{{.Image}}' 2>/dev/null "
        f"| grep {shlex.quote(CONTAINER_REPOSITORY + ':')} | head -20 || true",
    )
    remaining = contract.first_int(mine)
    engine_containers = _classify_containers(boxes)
    containers = len(engine_containers)
    used = contract.first_int(gpu)
    return {
        "backend": NAME,
        "steps": steps,
        "gpu_used_mib": used,
        # Neither reading is about ownership. The process count is a `pgrep`
        # for this engine's three patterns and matches any `vllm serve` on the
        # host, ours or not; the container count matches this engine's
        # repository the same way. Both are the right scope for an exclusion
        # gate — anything of this engine that is up holds the card we are about
        # to measure on.
        "engine_processes_remaining": remaining,
        "engine_containers_remaining": containers,
        # What is genuinely ours, recorded beside it and gating nothing: the
        # one container name :func:`_start` assigns.
        "our_containers_remaining": sum(
            1 for row in engine_containers if row["name"] == CONTAINER_NAME
        ),
        "engine_containers": engine_containers,
        "released": remaining == 0 and containers == 0,
        # A reading of the CARD, kept separate from the statement about this
        # backend: a backend holding nothing must not report failure because
        # another engine holds the card.
        "card_used_mib": used,
        "card_idle": None if used is None else used < contract.IDLE_GPU_MIB,
    }


def claim(
    host: str,
    base: str,
    model: str,
    serve: dict[str, Any] | None = None,
    expect: dict[str, Any] | None = None,
    **declared: Any,
) -> dict[str, Any]:
    """Be serving ``model`` under ``serve``, and prove it.

    ``**declared`` absorbs the per-entry declarations the orchestrator forwards
    for backends that model them — ``placement``, ``coresident``,
    ``coresident_with``. What it ignored is written down rather than dropped,
    because an entry that believes it declared something nothing reads is worse
    than one that was told.

    If a server is already up with the right model and the right parameters,
    nothing is restarted — this engine's startup is expensive and a needless
    restart is a minute of rig time. Otherwise it is stopped and relaunched with
    the requested parameters, because serving parameters ARE the experiment
    here: two servers differing only in batch width are two instruments.

    Verifies that the allocation is on the card. An empty card means the server
    is not holding one, which for this engine is a failure rather than the
    cleanliness it means elsewhere.
    """
    serve = serve or {}
    expect = expect or {}
    # `levels` is READ below, so it is not an ignored declaration. Everything
    # else this backend does not model still is, and still says so.
    ignored = {
        key: value for key, value in declared.items() if value and key != "levels"
    }
    # BEFORE anything ACTS. A pin naming a field this backend does not compute
    # is a config that believes it is pinned and is not — and the check has to
    # precede `_start`, which stops the running server and relaunches it.
    unknown = set(expect) - {"weights_sha256"}
    if unknown:
        raise contract.NotCleanError(
            f"{model} on {host}: {sorted(unknown)} is not this backend's pin. "
            "The only pin this backend computes is `weights_sha256`, a sha256 "
            "over every tensor's bytes in the checkpoint. Nothing was measured, "
            "and nothing was restarted."
        )
    # **The width the ramp will offer, against the width the engine was given.**
    # BEFORE anything ACTS: `_start` stops the running server, so a config error
    # raised after it has already destroyed the previous cell in order to
    # complain about a typo.
    levels = tuple(declared.get("levels") or serve.get("levels") or ())
    width = serve.get("max_num_seqs")
    if levels and width is not None and int(width) < max(levels):
        raise contract.NotCleanError(
            f"{model} on {host}: max_num_seqs={int(width)} is below the widest "
            f"level this cell will offer (n={max(levels)}). vLLM admits "
            f"{int(width)} sequences per scheduler step and queues the rest, so "
            "the aggregate flatlines while latency climbs -- a configuration "
            "artifact shaped exactly like hardware saturation. Set max_num_seqs to "
            "the top of the ladder. Nothing was measured, and nothing was restarted."
        )
    claim_started_at = contract.now()
    running = _running_config(base)
    if running and running.get("model") == model and _matches(running, serve):
        started = {"restarted": False, "reason": "already serving this configuration"}
    else:
        started = _start(host, model, serve)
        base = f"http://{host}:{PORT}"

    gpu = contract.ssh(host, "nvidia-smi --query-gpu=memory.used --format=csv,noheader")
    allocated = contract.first_int(gpu)
    # The card's state at the claim, beside its memory -- the point the ramp
    # that follows starts from. Null + the command when it did not answer.
    card = contract.card_state(contract.ssh(host, contract.CARD_STATE_COMMAND))
    config = _running_config(base)
    served = inventory(host, base)
    # **Two readbacks.** `launched_width` reads `--max-num-seqs` off the running
    # process argv (`provenance: observed`); `kv_capacity` reads what the engine
    # printed about the pool it actually allocated. The first catches a flag
    # that did not take, the second catches a flag that took and did not fit.
    observed_width = launched_width(host)
    capacity = (
        kv_capacity(_launch_log(host, str(started.get("launcher") or launcher(host))))
        if started.get("restarted")
        else kv_capacity(None)
    )
    if (
        levels
        and observed_width.get("value") is not None
        and int(observed_width["value"]) < max(levels)
    ):
        raise contract.NotCleanError(
            f"{model} on {host} is running at max_num_seqs="
            f"{int(observed_width['value'])} (read from "
            f"{observed_width.get('source')}), below the widest level this cell "
            f"will offer (n={max(levels)}). The width this run asked for is not "
            "the width the engine is serving at, so the ramp would record a "
            "scheduler queue as a plateau. Nothing was measured."
        )
    if (
        levels
        and capacity.get("max_concurrency") is not None
        and capacity["max_concurrency"] < max(levels)
    ):
        raise contract.NotCleanError(
            f"{model} on {host} allocated {capacity['kv_cache_tokens']:,} KV "
            f"tokens, which the engine itself states is "
            f"{capacity['max_concurrency']}x concurrency at "
            f"{capacity['per_request_tokens']} tokens per request -- below the "
            f"widest level this cell will offer (n={max(levels)}). The card "
            "cannot hold that many full-length sequences whatever max_num_seqs "
            "says, so the excess queues on KV blocks and the aggregate "
            "flatlines. Lower max_model_len, raise gpu_memory_utilization, or "
            "shorten the ladder. Nothing was measured."
        )
    # Where each process sits on the card, recorded and never gated:
    # `allocation_present` below is a threshold over the card's TOTAL, so it
    # says yes to a card whose memory belongs to somebody else.
    placed, placed_refused = _recorded_placements(host)
    digest = weights_sha256(host, model)
    wanted = expect.get("weights_sha256")
    check = {
        "started_at": claim_started_at,
        "ended_at": contract.now(),
        "started": started,
        "gpu_used_mib": allocated,
        "card": card,
        "allocation_present": (allocated or 0) >= MIN_ALLOCATION_MIB,
        "served_models": served,
        "engine_config": config,
        "weights": digest,
        "weights_sha256_expected": wanted,
        "resident_placements": placed,
        # Null carries the reason it is null, never a blank.
        "resident_placements_refused": placed_refused,
        # Recorded whether or not they gated anything above: the width the
        # engine is serving at, and the pool it allocated. A curve is read
        # against these two numbers, and a later reader cannot recover either
        # one from the row without them.
        "launched_width": observed_width,
        "kv_capacity": capacity,
    }
    check["ok"] = bool(
        model in served
        and check["allocation_present"]
        and (wanted is None or digest.get("weights_sha256") == wanted)
    )
    if check["ok"]:
        return {
            "backend": NAME,
            "model": model,
            "verified": True,
            "checks": check,
            # Written down rather than dropped: silence here would make a
            # declaration nothing reads invisible.
            "declarations_ignored": ignored or None,
        }

    if wanted is not None and digest.get("weights_sha256") != wanted:
        raise contract.NotCleanError(
            f"{model} on {host} is not the pinned weights: expected {wanted}, "
            f"the checkpoint hashes to {digest.get('weights_sha256')} "
            f"({digest.get('snapshot')}, {digest.get('tensors')} tensors). "
            "Every other check passed, which is why the digest is pinned — a "
            "model id is a name, and the bytes behind it can be replaced. "
            "Nothing was measured."
        )
    raise contract.NotCleanError(
        f"{model} on {host} is not being served cleanly: served={served}, "
        f"gpu={allocated} MiB. An empty card means the server is not holding "
        "its allocation, which for this engine means it did not come up. "
        "Nothing was measured."
    )


def describe(
    host: str,
    base: str,
    model: str,
    serve: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Everything this engine will say about ``model``.

    ``serve`` is the block this run launched with, the fallback width for
    :func:`declared_slots`.
    """
    return {
        "backend": NAME,
        "capture": contract.observed().capture(base, model),
        "engine_config": _running_config(base),
        "served": inventory(host, base),
        "weights": weights_sha256(host, model),
        "serving_config": serving_config(base),
        "declared_slots": declared_slots(serve, host),
    }


def weights_sha256(host: str, model: str) -> dict[str, Any]:
    """A true weights digest for ``model``, hashed on the serving host.

    **This engine publishes no weights digest on any endpoint** — the model card
    carries an id, an owner and a window, and the engine config names the model
    by string. So the digest is computed from the checkpoint the engine streams
    onto the card, which is host-access evidence rather than something the
    endpoint said, and is recorded as such.

    **It is NOT comparable with a digest from another backend**, and the field
    is named apart from any of them for that reason: this hashes tensor bytes
    out of a safetensors checkpoint, and an engine serving a different
    quantization of the same model computes something else entirely. Two
    backends disagreeing here is the expected result for the same model, not a
    contradiction — what it refutes is the claim that they are the same
    *instrument*, which is exactly what a family verdict should say.

    Cached per ``(host, model)``: the checkpoint does not change under a running
    survey, and the reading carries the snapshot path and mtime so a later
    reader can tell whether it still describes the files on disk.
    """
    key = (host, model)
    if key in _DIGEST_CACHE:
        return _DIGEST_CACHE[key]
    # A per-invocation path, removed after the run: a fixed name would let a
    # failed write leave a PREVIOUS run's script in place, and `contract.ssh`
    # reports neither the return code nor stderr.
    path = f"/tmp/mcgyvr-weights-digest-{os.getpid()}.py"
    # Run where torch is. One rig has it on the host; the other has it ONLY
    # inside the container, so hashing a checkpoint there means reaching into
    # the image that serves the model — which is the right place to read the
    # weights it loads anyway.
    if launcher(host) == "docker":
        runner = (
            "docker run --rm --entrypoint python3 "
            f"-v $HOME/.cache/huggingface:{CONTAINER_CACHE} "
            f"-v {path}:{path}:ro -e HF_HOME={CONTAINER_CACHE} "
            f"{CONTAINER_IMAGE} {path} {shlex.quote(model)}"
        )
    else:
        runner = (
            f"export PATH=$HOME/.local/bin:$PATH && python3 {path} {shlex.quote(model)}"
        )
    script = (
        f"cat > {path} <<'MCGYVR_EOF'\n"
        + _DIGEST_SCRIPT
        + "\nMCGYVR_EOF\n"
        + runner
        + f"; status=$?; rm -f {path}; exit $status"
    )
    began = time.monotonic()
    raw = contract.ssh(host, script, timeout=DIGEST_TIMEOUT_S)
    digest_seconds = round(time.monotonic() - began, 2)
    try:
        result = json.loads((raw or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        # `contract.ssh` answers None for a timeout and for every other
        # failure alike, so the timeout is derived from the clock this
        # function already reads. A digest that ran out of time is a point on
        # DIGEST_TIMEOUT_S's curve, not a blank.
        if raw is None and digest_seconds >= DIGEST_TIMEOUT_S:
            result = {
                "error": (
                    f"the digest did not finish inside DIGEST_TIMEOUT_S = "
                    f"{DIGEST_TIMEOUT_S:.0f} s"
                )
            }
        else:
            result = {
                "error": f"the digest script returned nothing usable: {raw!r}",
            }
    # Scrubbed before it is returned. `snapshot` is
    # `$HF_HOME/hub/models--…/snapshots/<hash>`, i.e. a home-directory path that
    # names a user — precisely what the redactor exists for — and this is
    # written to a tracked path.
    result = dict(contract.scrub(result))
    # `digest_seconds` beside `bytes` makes every digest a point on
    # DIGEST_TIMEOUT_S's curve.
    result["digest_seconds"] = digest_seconds
    result["method"] = (
        "sha256 over every tensor's bytes in sorted key order across all "
        "shards, computed on the serving host: this engine states no weights "
        "digest on any endpoint"
    )
    # A FAILURE is never cached. The cache exists because a checkpoint does not
    # change under a survey; an error is a fact about a moment — an ssh that
    # timed out, a host briefly unreachable — and caching it would make one bad
    # minute permanent for the rest of the run.
    if "error" not in result:
        _DIGEST_CACHE[key] = result
    return result


#: The image a containerised deployment runs. Pinned to a tag rather than
#: `latest`, because "the version that was current when it was pulled" is not a
#: version anybody can look up later.
CONTAINER_IMAGE = "vllm/vllm-openai:v0.26.0"

#: **The one name this module ever gives a container, and what "ours" means.**
#: :func:`_start` creates exactly one container and calls it this. Everything
#: else built from the same image belongs to somebody else.
CONTAINER_NAME = "mcgyvr-vllm"

#: The repository, tag stripped. :func:`readings` and :func:`release` match on
#: it; :func:`launched_width` filters on ``ancestor=`` :data:`CONTAINER_IMAGE`.
#:
#: **`--filter ancestor=<tag>` matches by resolved image ID, not by tag**, so a
#: filter pinned to one tag stops seeing a container whose tag has moved to
#: another image id. Matching the repository string does not depend on the ids.
CONTAINER_REPOSITORY = CONTAINER_IMAGE.split(":")[0]

#: Where the weights cache is mounted inside the container.
CONTAINER_CACHE = "/root/.cache/huggingface"


#: The probe that answers whether a host can serve through each launcher. The
#: SAME command decides a detection and verifies a declaration, so a declared
#: launcher is held to exactly the bar a detected one had to clear.
LAUNCHER_PROBES: dict[str, str] = {
    "pip": "command -v vllm 2>/dev/null || true",
    "docker": f"docker images -q {CONTAINER_IMAGE} 2>/dev/null || true",
}

#: Hosts whose launcher this RUN declares, ``{host: how}`` — empty unless a
#: caller declared one, so detection is still what happens by default.
#:
#: Detection is right for a rig that has one launcher and wrong for a
#: contrast: on a host with both, detection returns `pip` whenever `vllm`
#: answers on PATH. A declaration is VERIFIED against the host and refused when
#: the host cannot serve it, and the launch row records that the launcher was
#: declared.
DECLARED_LAUNCHERS: dict[str, str] = {}


def declare_launcher(host: str, how: str | None) -> None:
    """Declare (or with ``None``, un-declare) how ``host`` launches vllm.

    Nothing is checked here: the host is reached at
    :func:`launcher`, once, where a detection would have reached it anyway.
    Declaring costs no extra ssh.
    """
    if how is None:
        DECLARED_LAUNCHERS.pop(host, None)
        return
    if how not in LAUNCHER_PROBES:
        raise contract.NotCleanError(
            f"{how!r} is not a launcher. This engine is deployed as "
            f"{' or '.join(sorted(LAUNCHER_PROBES))} and a run may declare "
            "either; a name outside that set would be detected as `none` and "
            "read as a machine that cannot serve, which is a different fact."
        )
    DECLARED_LAUNCHERS[host] = how


def launcher(host: str) -> str:
    """How this engine is deployed here: ``pip``, ``docker``, or ``none``.

    **Both shapes exist and the difference is not cosmetic.** A host with only
    the container image has no ``vllm`` binary and may have no torch, so a
    launcher that assumed pip would simply fail there — and so would the
    weights digest, which needs torch to read a checkpoint. Detected rather than
    configured, because it is a property of the machine and a config that had to
    state it would be a config that could state it wrongly.

    A run may DECLARE one (:func:`declare_launcher`) when the launcher is part
    of what it is holding fixed. The declaration is verified with the probe
    detection uses and refused when the host cannot honour it, so the config
    that states it wrongly is caught by the machine rather than believed.
    """
    declared = DECLARED_LAUNCHERS.get(host)
    if declared is not None:
        if contract.ssh(host, LAUNCHER_PROBES[declared]):
            return declared
        raise contract.NotCleanError(
            f"{host} was declared to launch vllm through {declared!r} and does "
            f"not answer {LAUNCHER_PROBES[declared]!r}. Nothing was measured. A "
            "declared launcher is not a preference to fall back from: falling "
            "back would run the contrast on the launcher the declaration exists "
            "to exclude, and record the fallback nowhere a reader looks."
        )
    for how, probe in LAUNCHER_PROBES.items():
        if contract.ssh(host, probe):
            return how
    return "none"


#: The two ways an entry may state the memory it wants. **Exclusive, and
#: neither is defaulted.** This engine's own arithmetic is
#: ``requested = total_memory * gpu_memory_utilization`` with a hard
#: ``free >= requested`` precondition (``vllm/v1/worker/utils.py``), so a
#: fraction is a statement about a *card*. Bytes are a property of the model
#: and travel.
MEMORY_FIELDS: tuple[str, ...] = ("kv_cache_memory_bytes", "gpu_memory_utilization")


def _memory_args(serve: dict[str, Any]) -> list[str]:
    """The KV-cache declaration as CLI arguments, or a refusal.

    **There is no default**: a fallback fraction is a number nobody chose.

    **Both fields together is a refusal, not a precedence rule.** vLLM's own
    precedence is that ``kv_cache_memory_bytes`` silently ignores
    ``gpu_memory_utilization``; honouring that here would let a config state a
    fraction, have it discarded, and read as though it had been applied -- a
    config that believes it declared something it did not, which is the shape
    ``claim``'s ``expect`` guard already refuses.
    """
    declared = [field for field in MEMORY_FIELDS if serve.get(field) is not None]
    if len(declared) > 1:
        raise contract.NotCleanError(
            f"serve declares {sorted(declared)} together. They are exclusive: "
            "vLLM ignores gpu_memory_utilization whenever kv_cache_memory_bytes "
            "is set, so carrying both records a fraction that never applied. "
            "Declare one. Nothing was measured."
        )
    if not declared:
        raise contract.NotCleanError(
            "serve declares neither kv_cache_memory_bytes nor "
            "gpu_memory_utilization, and there is no default. "
            "Bytes are max_num_seqs * max_model_len * bytes_per_token at the "
            "launch's --kv-cache-dtype and are the same on every card; a "
            "fraction is a statement about one card and says which and why. "
            "Nothing was measured."
        )
    if declared[0] == "kv_cache_memory_bytes":
        return ["--kv-cache-memory-bytes", str(int(serve["kv_cache_memory_bytes"]))]
    return ["--gpu-memory-utilization", str(serve["gpu_memory_utilization"])]


#: Bytes one element of the KV cache takes under each ``--kv-cache-dtype`` this
#: gate can size. ``auto`` is the model's own dtype, and every checkpoint in the
#: tree resolves it to float16 or bfloat16: two bytes, the width each entry's
#: ``bytes_per_token`` is derived at (its note: "x 2 bytes"). An fp8 element is
#: one byte, and that is measured rather than read off the dtype's name: at one
#: ``max_model_len`` on one card, srv2's q15 held 332,160 KV tokens under
#: ``auto`` and 664,320 under ``fp8``
#: (``records/evidence/2026-09-01-prompt-realism/srv2-fp8-ab-and-lcp-smoke.tsv``),
#: and q34b 52,192 and 104,400
#: (``records/measurements/measuring-gaps-2026-09-10/results-q2-vllm-fp8.json``),
#: exactly 2.000x both times. A dtype missing here is refused, not defaulted.
KV_CACHE_DTYPE_BYTES: dict[str, int] = {
    "auto": 2,
    "float16": 2,
    "bfloat16": 2,
    "fp8": 1,
    "fp8_e4m3": 1,
    "fp8_e5m2": 1,
}

#: The element width every ``bytes_per_token`` in the tree is derived at.
BYTES_PER_TOKEN_ELEMENT_BYTES = 2


def kv_cache_dtype(serve: dict[str, Any]) -> str:
    """The ``--kv-cache-dtype`` this entry launches with, read as the launch reads it.

    From ``serve["flags"]``, the list ``_start`` appends to the argv, in either
    spelling (``--kv-cache-dtype fp8`` or ``--kv-cache-dtype=fp8``). No flag is
    no answer now: a serve block that does not state one is refused, because
    ``auto`` here is vLLM's own default, not a number the operator chose. A
    flag with no value, or a value this gate has no element width for, is
    refused by name: sized at two bytes it would over-declare a narrower cache
    and at one it would under-declare a wider one, and either is a number
    nobody chose.
    """
    flags = [str(flag) for flag in serve.get("flags") or []]
    declared: str | None = None
    for index, flag in enumerate(flags):
        if flag == "--kv-cache-dtype":
            declared = flags[index + 1] if index + 1 < len(flags) else ""
        elif flag.startswith("--kv-cache-dtype="):
            declared = flag.partition("=")[2]
    if declared is None:
        raise contract.NotCleanError(
            "serve launches with no --kv-cache-dtype in its flags, so "
            "this gate cannot size its KV cache. Declare one — every served "
            "unit states which cache it runs. Nothing was measured."
        )
    if declared not in KV_CACHE_DTYPE_BYTES:
        raise contract.NotCleanError(
            f"serve launches with --kv-cache-dtype {declared!r}, and this gate has "
            f"no element width for it (it sizes {sorted(KV_CACHE_DTYPE_BYTES)}). "
            "Refused rather than sized at a guessed width: a KV declaration is "
            "bytes, and bytes at the wrong width are a cache the card was never "
            "asked to hold. Nothing was measured."
        )
    return declared


def kv_bytes_per_token(serve: dict[str, Any]) -> int:
    """``bytes_per_token`` at the element width this entry's cache launches with.

    The declaration rule is ``max_num_seqs x max_model_len x bytes_per_token``,
    and ``bytes_per_token`` is derived at :data:`BYTES_PER_TOKEN_ELEMENT_BYTES`
    an element, so it is rescaled here to the cache's own element width: read
    at two bytes for an fp8 cache, the rule declares twice the KV the engine
    needs.
    """
    width = KV_CACHE_DTYPE_BYTES[kv_cache_dtype(serve)]
    return int(serve["bytes_per_token"]) * width // BYTES_PER_TOKEN_ELEMENT_BYTES


#: One vLLM allocation block: a declaration that leaves less than one block
#: spare does not launch, whatever the rest of the sum says.
ALLOCATOR_BLOCK_MIB = 256

#: What a vLLM process holds on this card BESIDES its weights and the KV cache
#: it declares, plus the one block it must still be able to take.
#:
#: **Measured, as a residue, not assembled from terms**:
#: ``card_mib_after_load - weights - declared_kv``. Assembling it from parts
#: double-counts, because ``nvidia-smi``'s view of the card already contains
#: the driver's reserve and the process's context. The refit campaign
#: (`records/evidence/2026-08-23-phase0-refit/`) measured it on three cells:
#:
#:     srv1 / Qwen3-4B   len 2048   card  5,222   residue  358 MiB
#:     srv2 / 14B        len 1024   card 11,479   residue  337 MiB
#:     srv2 / Qwen3-4B   len 7168   card 11,101   residue  477 MiB
#:
#: So the residue is 337-477 MiB and does not track model size — it tracks the
#: KV cache, which is what the block padding is on. **477 + 256 = 733**: the
#: largest residue any cell has produced, plus the block it must be able to
#: take on top of it. Both halves are readings.
#:
#: Ten vLLM cells now bear on it — phase 0's seven and the refit's three — and
#: they admit any value from **511 to 1,145 MiB** without changing a verdict.
#: 733 is not chosen inside that window; it is derived, and it lands there. The
#: check re-derives both the value and the window from the two campaigns' own
#: tables, so a cell with a larger residue fails it rather than quietly making
#: the constant wrong.
NON_KV_OVERHEAD_MIB = 733

#: Slack allowed when checking ``total == reserved + used + free``. The four
#: fields are rounded to whole MiB independently, so a healthy card misses the
#: identity by a MiB or so. What the check exists to catch is `used` changing
#: to NVML v2 semantics and absorbing the reserve, which moves the sum by the
#: reserve's own size, far above rounding.
IDENTITY_TOLERANCE_MIB = 8


def _mib(byte_count: float) -> int:
    """Bytes as whole MiB, rounded up — a partial block is a held block."""
    return int(-(-byte_count // (1024 * 1024)))


def free_mib(host: str) -> int | None:
    """How much card this host has free right now, or ``None`` if it did not say.

    Returns ``total - used``, the figure :data:`NON_KV_OVERHEAD_MIB` is fitted
    against; ``memory.free`` and ``memory.reserved`` are read on the same line
    only to check ``total == reserved + used + free``. ``None`` when the card
    did not answer — never ``0``, which would read as a full card and refuse
    every declaration on a host whose driver was merely wedged.
    """
    line = contract.ssh(
        host,
        "nvidia-smi --query-gpu=memory.total,memory.used,memory.free,memory.reserved "
        "--format=csv,noheader,nounits",
    )
    parts = (
        [p.strip() for p in (line or "").strip().splitlines()[:1][0].split(",")]
        if (line and line.strip())
        else []
    )
    if len(parts) < 2:
        return None
    total, used = contract.first_int(parts[0]), contract.first_int(parts[1])
    if total is None or used is None:
        return None
    free = contract.first_int(parts[2]) if len(parts) > 2 else None
    reserved = contract.first_int(parts[3]) if len(parts) > 3 else None
    # **The tripwire.** `total - used` is not what a process can allocate: the
    # card also carries a driver/firmware reserve that belongs to neither term.
    # This function still returns `total - used`, because NON_KV_OVERHEAD_MIB is
    # fitted as a residue against exactly that figure and already absorbs the
    # reserve; subtracting it here would charge it twice and refuse cells that
    # fit. The branch that DOES need it lowers its own ceiling -- see
    # `declaration_fits`.
    #
    # What is not safe is the identity moving under us: NVML v1 and v2 disagree
    # on whether `used` includes `reserved`, so a driver that switched
    # `nvidia-smi`'s field to v2 semantics would make `used` jump by the reserve
    # and silently tighten every gate with no error anywhere.
    #
    # Each field is an independently rounded whole MiB, so the identity closes
    # to within a MiB or two on a healthy card. The shift guarded against is the
    # size of the reserve itself, so the tolerance sits far above rounding and
    # far below that.
    if (
        free is not None
        and reserved is not None
        and abs(total - (reserved + used + free)) > IDENTITY_TOLERANCE_MIB
    ):
        raise contract.NotCleanError(
            f"{host}: the card reports total {total:,} MiB but "
            f"reserved {reserved:,} + used {used:,} + free {free:,} = "
            f"{reserved + used + free:,} MiB. This function returns "
            "`total - used`, and NON_KV_OVERHEAD_MIB is fitted against that "
            "figure on the assumption that `used` excludes the driver reserve. "
            "The identity says it no longer does, so the pairing that makes the "
            "gate conservative cannot be relied on and the overhead constant "
            "must be refitted before anything launches. Nothing was measured."
        )
    allocatable: int = total - used
    return allocatable


def reserved_mib(host: str) -> int | None:
    """The card's driver/firmware reserve, or ``None`` if the driver withheld it.

    It belongs to no process, so it appears in neither ``memory.used`` nor
    ``memory.free``; the identity is ``total = reserved + used + free`` and
    :func:`free_mib` returns only ``total - used``. See
    ``okf/must-read/touching-rigs.md``.

    Read on its own rather than on :func:`free_mib`'s line: the reserve does not
    move while a run is in flight, so a second reading of it cannot describe a
    different moment the way a free-memory reading can.
    """
    line = contract.ssh(
        host,
        "nvidia-smi --query-gpu=memory.reserved --format=csv,noheader,nounits",
    )
    if not (line and line.strip()):
        return None
    reserved: int | None = contract.first_int(line.strip().splitlines()[0])
    return reserved


#: `--cpu-offload-gb` is not subtracted from the weights:
#: :func:`declaration_fits` weighs a declaration at its full weight. See
#: ``okf/config/vllm.md``.
_CPU_OFFLOAD_IS_NOT_A_DISCOUNT = True


def declaration_fits(
    host: str, model: str, serve: dict[str, Any], free_mib: int | None
) -> None:
    """Refuse a KV declaration this card cannot hold — before the launch.

    The declaration rule is
    ``max_num_seqs x max_model_len x bytes_per_token``. It is arithmetically
    correct and can still produce a declaration a card cannot hold; without
    this check nothing refuses it until vLLM does, minutes later, with
    ``torch.OutOfMemoryError`` at load. This is the same arithmetic, run in
    milliseconds, against figures that already exist.

    **Two sources, and the measured one wins.** An entry that has already loaded
    on this host carries ``_footprint_mib`` — what the card said the process
    took — and that is a fact, not a prediction: a footprint that was observed
    to fit needs no model of why. Only an entry with no measurement for this
    host is predicted, from its declared weights plus its declared KV plus
    :data:`NON_KV_OVERHEAD_MIB`. The refusal says which of the two it used, so a
    reader is never left to guess whether a number was seen or computed.

    **A fraction is not checked here.** Under ``gpu_memory_utilization`` this
    engine enforces its own ``free >= total x util`` precondition before it
    allocates anything, so the failure is already immediate and already names
    the card. It is the byte declaration that skips profiling and finds out
    late.

    Raises ``NotCleanError``; returns ``None`` when the declaration fits or when
    there is nothing here to check.
    """
    kv_bytes = serve.get("kv_cache_memory_bytes")
    if kv_bytes is None:
        return
    # Before anything is weighed: a cache dtype this gate has no width for is
    # refused by name, and the ways out below count tokens at the one it has.
    kv_cache_dtype(serve)
    if free_mib is None:
        raise contract.NotCleanError(
            f"{model} on {host}: the card did not answer how much memory is "
            "free, so a declaration of "
            f"{int(kv_bytes):,} B of KV cache cannot be checked against it. "
            "Refused rather than launched: this engine skips memory profiling "
            "under a byte declaration, so an unchecked one is found out by "
            "torch.OutOfMemoryError minutes later (#354). Nothing was measured."
        )

    kv_mib = _mib(int(kv_bytes))
    measured = (serve.get("_footprint_mib") or {}).get(host)
    # **The two branches are weighed against DIFFERENT ceilings, deliberately.**
    # Do not reconcile them. `free_mib` returns `total - used`, which overstates
    # what a process can allocate by the driver/firmware reserve (see
    # `reserved_mib`). The predicted branch is already correct against that
    # figure because NON_KV_OVERHEAD_MIB is FITTED as a residue against it and
    # so already carries the reserve inside itself; subtracting the reserve
    # there as well would charge it twice and refuse cells that fit. The
    # measured branch has no such constant -- a footprint is exact -- so nothing
    # there absorbs the reserve and the ceiling must be lowered by hand. Left
    # unlowered, a footprint between `total - used - reserved` and
    # `total - used` is admitted and then dies at load.
    reserve_mib = None
    if measured is not None:
        reserve_mib = reserved_mib(host)
        if reserve_mib is None:
            raise contract.NotCleanError(
                f"{model} on {host}: this entry is weighed on its measured "
                f"footprint of {int(measured):,} MiB, and that comparison needs "
                "the card's driver/firmware reserve, which this driver did not "
                "report. It is NOT assumed to be zero: treating it as absent is "
                "exactly the optimism that admits a cell which then dies in "
                "torch.OutOfMemoryError at load. Query "
                "`nvidia-smi --query-gpu=memory.reserved` on this host and "
                "refuse until it answers. Nothing was measured."
            )
        free_mib = free_mib - reserve_mib
        required_mib, weights_mib, how = int(measured), None, "measured"
    else:
        weights = serve.get("weights_bytes")
        if weights is None:
            raise contract.NotCleanError(
                f"{model} on {host}: the entry declares "
                f"{int(kv_bytes):,} B of KV cache and neither a measured "
                f"`_footprint_mib` for {host} nor a `weights_bytes`, so nothing "
                "here can say whether the card can hold it. Declare the "
                "weights with a note showing where the figure came from — this "
                "engine prints `Model loading took X GiB` on every start. "
                "Nothing was measured."
            )
        weights_mib = _mib(int(weights))
        required_mib = weights_mib + kv_mib + NON_KV_OVERHEAD_MIB
        how = "predicted"

    if required_mib <= free_mib:
        return

    if how == "measured":
        assert reserve_mib is not None
        raise contract.NotCleanError(
            f"{model} on {host}: this entry took {required_mib:,} MiB on this "
            f"card when it was measured, and {free_mib:,} MiB is allocatable "
            f"now — that is the free reading less the {reserve_mib:,} MiB this "
            "card reserves for driver and GSP firmware, which belongs to no "
            f"process and cannot be allocated. {required_mib - free_mib:,} MiB "
            f"short. The declaration is {int(kv_bytes):,} B of KV cache. "
            "Refused before the launch (#354). Nothing was measured."
        )

    assert weights_mib is not None
    budget_mib = free_mib - weights_mib - NON_KV_OVERHEAD_MIB
    ways_out = _ways_out(serve, budget_mib)
    raise contract.NotCleanError(
        f"{model} on {host}: the declaration does not fit this card. "
        f"weights {weights_mib:,} MiB + declared KV {kv_mib:,} MiB + "
        f"{NON_KV_OVERHEAD_MIB:,} MiB the process holds besides them "
        f"= {required_mib:,} MiB, and the card has {free_mib:,} MiB free. "
        f"Short by {required_mib - free_mib:,} MiB. "
        f"{ways_out} "
        "This picks neither: which one to give up is the entry's decision, and "
        "a launcher that quietly chose would have the run measure a "
        "configuration nobody declared. "
        "Nothing was measured."
    )


def _ways_out(serve: dict[str, Any], budget_mib: int) -> str:
    """The two declarations that would fit, each with its figure.

    ``max_num_seqs`` and ``max_model_len`` enter the requirement as a product,
    so either one alone can be brought under the budget and both land on the
    same number of KV tokens. They are named together and neither is applied.
    Tokens are counted at the cache dtype the entry launches with
    (:func:`kv_bytes_per_token`): at the fp16 width an fp8 budget reads as half
    the batch and half the window it can hold.
    """
    per_token = serve.get("bytes_per_token") and kv_bytes_per_token(serve)
    seqs = serve.get("max_num_seqs")
    length = serve.get("max_model_len")
    if budget_mib <= 0:
        return (
            "No KV declaration fits: the weights alone leave nothing on this "
            "card, so a shorter context or a narrower batch does not help and "
            "the model does not belong on this host."
        )
    if not (per_token and seqs and length):
        return (
            "The two ways out cannot be costed here: the entry does not "
            "declare bytes_per_token, max_num_seqs and max_model_len, which "
            "are what turn a budget back into a shape."
        )
    tokens = (budget_mib * 1024 * 1024) // int(per_token)
    return (
        f"{budget_mib:,} MiB is {tokens:,} KV tokens at this model's "
        f"{int(per_token):,} B/token, which is either "
        f"max_num_seqs {tokens // int(length)} at the declared "
        f"max_model_len {int(length):,}, or max_model_len "
        f"{tokens // int(seqs):,} at the declared max_num_seqs {int(seqs)}."
    )


#: What the engine says it allocated, in its own words, at startup.
#: `GPU KV cache size: 131,104 tokens` is the pool; `Maximum concurrency for
#: 2048 tokens per request: 64.01x` is that pool divided by `max_model_len`
#: -- the engine's own statement of how many full-length sequences it can hold
#: at once. Both are printed once, at start, and scroll off the tail of a busy
#: log, so a capacity that cannot be read is null and not a refusal.
_KV_TOKENS = re.compile(r"GPU KV cache size:\s*([\d,]+)\s*tokens")
_MAX_CONCURRENCY = re.compile(
    r"Maximum concurrency for\s*([\d,]+)\s*tokens per request:\s*([\d.]+)x"
)


def kv_capacity(text: str | None) -> dict[str, Any]:
    """The KV pool and the concurrency it affords, read off the engine's log.

    **Why this is read at all.** ``max_num_seqs`` is the width the scheduler is
    *allowed*; this is the width the card can actually *hold*. They are
    different numbers and the smaller one binds. A cell launched at
    ``max_num_seqs 32`` whose KV pool fits 9 full-length sequences serves the
    other 23 in a second batch, and the aggregate flatlines exactly as hardware
    saturation does -- and this engine publishes no slot count to read back.

    Null when the lines are absent. A server that was already up when the claim
    arrived has a log tail full of requests rather than its own startup, and a
    capacity nobody could read must not become a refusal that was never true.
    """
    tokens = _KV_TOKENS.search(text or "")
    concurrency = _MAX_CONCURRENCY.search(text or "")
    return {
        "kv_cache_tokens": int(tokens.group(1).replace(",", "")) if tokens else None,
        "per_request_tokens": (
            int(concurrency.group(1).replace(",", "")) if concurrency else None
        ),
        "max_concurrency": float(concurrency.group(2)) if concurrency else None,
    }


def _launch_log(host: str, how: str) -> str:
    """The engine's own last words, read before anything removes them (#352).

    **The decision this implements.** A failed cell's container is removed at
    once — :func:`_start` still opens with `docker rm -f mcgyvr-vllm`, which is
    what makes the next launch reliable — *because its reason is read first*.
    The alternative, keeping the container until somebody has looked, makes
    every launch depend on a human having been there, and a campaign that runs
    for five hours unattended is exactly where that fails.

    **The pip rig loses it the same way**: the launch redirects
    `> /tmp/vllm-serving.log`, so the next cell truncates the previous cell's
    log rather than appending to it. Both launchers are read here for that
    reason.

    Never raises. :func:`contract.ssh` answers `None` for a host it could not
    reach, and a log that could not be read must not replace a refusal that was
    already true — the launch failed either way, and that is what is reported.
    """
    command = (
        f"docker logs --tail {LAUNCH_LOG_LINES} mcgyvr-vllm 2>&1"
        if how == "docker"
        else f"tail -n {LAUNCH_LOG_LINES} /tmp/vllm-serving.log 2>/dev/null"
    )
    raw = contract.ssh(host, command)
    if raw is None:
        return "<the host did not answer, so the engine's own log was not read>"
    # Scrubbed through the one scrubber, because this text reaches the log and
    # the run record through the exception message, and a vLLM traceback quotes
    # the argv and the paths beneath it. What that catches is credential URLs,
    # home-directory prefixes and the published token shapes — not an arbitrary
    # `KEY=value` an operator invented, which no reading in this tree redacts
    # either. Stated rather than implied: this is the same guarantee every other
    # host reading here carries, and not a stronger one.
    return str(contract.scrub(raw))


def _start(host: str, model: str, serve: dict[str, Any]) -> dict[str, Any]:
    """Launch the server with ``serve``, and wait for it to answer.

    ``VLLM_SERVER_DEV_MODE=1`` is set deliberately: it is what makes the
    quantization and the seed readable at all, and this is a measurement rig on
    a private network. It should not be set on anything exposed — the flag also
    opens routes that change the server, including one that executes a method
    inside the engine process.
    """
    release(host)
    how = launcher(host)
    if how == "none":
        raise contract.NotCleanError(
            f"{host} has neither a vllm binary nor the {CONTAINER_IMAGE} image, "
            "so this engine cannot be started here. Nothing was measured."
        )
    # **#354, and it sits HERE for two reasons.** After `release`, because the
    # free memory a declaration is checked against is the memory it will
    # actually get, and the card is not clear until the previous engine has let
    # go. And inside `_start` rather than in `claim`, because `claim`'s other
    # branch is a server already up on this configuration: that one has proved
    # it fits by running, and checking it would read the free memory of a card
    # the process itself is holding and refuse a cell that is serving.
    declaration_fits(host, model, serve, free_mib(host))
    args = [
        "--max-model-len",
        str(serve.get("max_model_len", 8192)),
        *_memory_args(serve),
        "--max-num-seqs",
        str(serve.get("max_num_seqs", 8)),
        "--port",
        str(PORT),
        *serve.get("flags", []),
    ]
    environment = {"VLLM_SERVER_DEV_MODE": "1", **serve.get("env", {})}
    # Values are quoted and KEYS are validated: a variable name is a narrow
    # shape, and quoting a key would produce a name no shell would export,
    # hiding the typo instead of naming it.
    for key in environment:
        if not key.replace("_", "").isalnum() or key[:1].isdigit():
            raise contract.NotCleanError(
                f"{key!r} is not a usable environment variable name. Serving "
                "config is interpolated into a shell on the serving host, so a "
                "name is held to letters, digits and underscores rather than "
                "escaped into something no shell would set."
            )
    command = (
        "export "
        + " ".join(
            f"{key}={shlex.quote(str(value))}" for key, value in environment.items()
        )
        + "; export PATH=$HOME/.local/bin:$PATH; cd /tmp && nohup vllm serve "
        + shlex.quote(model)
        + " "
        + " ".join(shlex.quote(arg) for arg in args)
        + " > /tmp/vllm-serving.log 2>&1 < /dev/null & disown; echo launched"
    )
    if how == "docker":
        # The container carries its own environment, so the flags are passed as
        # `-e` rather than exported into a shell that will not be its parent.
        environment_flags = " ".join(
            f"-e {shlex.quote(f'{key}={value}')}" for key, value in environment.items()
        )
        command = (
            "docker rm -f mcgyvr-vllm >/dev/null 2>&1; "
            "docker run -d --name mcgyvr-vllm --runtime=nvidia --gpus all "
            f"-v $HOME/.cache/huggingface:{CONTAINER_CACHE} "
            f"-p {PORT}:{PORT} --ipc=host {environment_flags} "
            f"{CONTAINER_IMAGE} {shlex.quote(model)} "
            + " ".join(shlex.quote(arg) for arg in args)
        )
    began = time.monotonic()
    launched = contract.ssh(host, command)
    # Each round is `curl -m 5` + `nvidia-smi` + `sleep 10`. //20 keeps the
    # loop's worst case inside the ssh budget below, with room for a slow
    # `nvidia-smi` — a start cut off by the client would be recorded as a server
    # that never came up.
    rounds = int(START_TIMEOUT_S // 20)
    # Ready is /health 200 AND the card carrying an allocation of at least
    # MIN_ALLOCATION_MIB.
    ready = contract.ssh(
        host,
        f"for i in $(seq 1 {rounds}); do "
        f"code=$(curl -s -m 5 -o /dev/null -w '%{{http_code}}' "
        f"http://127.0.0.1:{PORT}/health); "
        "mib=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits "
        "2>/dev/null | head -1); "
        f'[ "$code" = "200" ] && [ "${{mib:-0}}" -ge {int(MIN_ALLOCATION_MIB)} ] '
        "&& { echo ready; exit 0; }; sleep 10; done; "
        'echo "timeout code=$code mib=$mib"',
        timeout=START_TIMEOUT_S + 120,
    )
    # **Asserted, not merely recorded**: a server that never came up must not
    # be measured against anyway.
    if (ready or "").split()[:1] != ["ready"]:
        # **Read before it is destroyed.** Taken here, on the failure path, and
        # not left as an instruction to the reader: the next cell opens with
        # `docker rm -f mcgyvr-vllm` on the docker rig and truncates
        # `/tmp/vllm-serving.log` on the pip rig.
        tail = _launch_log(host, how)
        raise contract.NotCleanError(
            f"vllm on {host} did not reach health with an allocation within "
            # SCRUBBED. Host output carries credentials — a systemd
            # `Environment=` line, an exported launch command — and an exception
            # message is written to logs and to the run record like any other
            # field.
            f"START_TIMEOUT_S // 20 polls with a 10 s sleep after each, under "
            f"an ssh timeout of START_TIMEOUT_S + 120 s "
            f"(START_TIMEOUT_S={START_TIMEOUT_S:.0f}s); the wait returned "
            f"{contract.scrub(ready)!r}. "
            "Launcher was "
            f"{how!r}. Nothing "
            "was measured. The known causes here are a cold weights download "
            "inside the start budget and a KV cache that will not fit the card "
            "at the requested max_model_len. The engine's own last "
            f"{LAUNCH_LOG_LINES} log lines, read on the failure and before the "
            f"next launch removes them: {tail!r}"
        )
    # The recorded command contains the exported environment VALUES — the very
    # thing an `env` block is used to pass a key through — so what is written
    # down is scrubbed even though what was executed was not.
    restarted: dict[str, Any] = contract.scrub(
        {
            "restarted": True,
            "launcher": how,
            # Whether that launcher was the machine's answer or the run's.
            # Detection and declaration produce the same string, and a reader
            # of a cross-host contrast needs to know which one the two hosts
            # agreeing came from.
            "launcher_declared": host in DECLARED_LAUNCHERS,
            "command": command,
            "launched": launched,
            "ready": ready,
            # Every launch adds a point to START_TIMEOUT_S's calibration at no
            # cost.
            "start_seconds": round(time.monotonic() - began, 2),
            "serve": serve,
        }
    )
    return restarted


def build(host: str) -> dict[str, Any]:
    """This engine's version on ``host``, for the identity block (#326).

    ``GET /version`` on a running server; a server that is not up answers
    nothing, and then the pip package or the container tag is asked. Each
    is named, so a ``null`` says which reads were tried.

    **The launcher is part of the build.** ``GET /version`` returns the
    PACKAGE's version, which is the same from a pip install and from the
    container of the same release. A build string therefore names both, and two
    runs on the same version through different launchers differ here.
    """
    answered = contract.get_json(
        contract.url(f"http://{host}:{PORT}", "/version"), timeout=10.0
    )
    if isinstance(answered, dict) and answered.get("version"):
        return {
            "serving_build": f"vllm {answered['version']} via {launcher(host)}",
            "refused": None,
        }
    command = (
        "vllm --version 2>/dev/null || "
        "python3 -c 'import vllm; print(vllm.__version__)' "
        f"2>/dev/null || (docker images -q {CONTAINER_IMAGE} >/dev/null 2>&1 "
        f"&& echo {CONTAINER_IMAGE})"
    )
    raw = contract.ssh(host, command)
    if raw:
        return {
            "serving_build": (
                f"vllm {raw.strip().splitlines()[-1]} via {launcher(host)}"
            ),
            "refused": None,
        }
    return {
        "serving_build": None,
        "refused": f"GET /version on port {PORT} answered nothing, then: {command}",
    }


def launched_width(host: str) -> dict[str, Any]:
    """The width the running server was actually started with, read off the host.

    The flag is in the running process's own argv on the pip rig and in the
    container's ``Config.Cmd`` on the docker rig, and the harness reads both
    over ssh.

    That is a genuine observation and it is strictly better than reading back the
    value this run intended, because the two can differ. ``claim`` has a path
    that does NOT restart a server already serving the wanted configuration, so
    on that path a server started by someone else — at some other width — would
    otherwise be described using our own variable.
    """
    for source, command in (
        (
            "process",
            # `COLUMNS=` explicitly: `ps` truncates its output to that width
            # when the variable is set, and the flag sits deep in this argv.
            "COLUMNS=1000 ps -eo args | grep -E '[v]llm (serve|.*api_server)' "
            "| head -1",
        ),
        (
            "container",
            f"docker ps --filter ancestor={CONTAINER_IMAGE} --format '{{{{.Names}}}}' "
            "| head -1 | xargs -r -I{} docker inspect {} "
            "--format '{{{{json .Config.Cmd}}}}'",
        ),
    ):
        line = contract.ssh(host, command)
        if not line:
            continue
        # Both shapes reduce to the same thing: the flag followed by its value,
        # separated either by whitespace or by the JSON array's quoting.
        found = re.search(r'max-num-seqs["\s,]+"?(\d+)', line)
        if found:
            return {"value": int(found.group(1)), "source": source}
    return {"value": None, "source": None}


def declared_slots(
    serve: dict[str, Any] | None = None,
    host: str | None = None,
) -> dict[str, Any]:
    """What this engine is running at — read off the host, not off the wire.

    ``/v1/models`` and the text form of ``/server_info`` do not carry it. The
    JSON form (``?config_format=json``) does, under ``scheduler_config``, and
    nothing here reads it there.

    **The host has it**, in the server's own argv — see
    :func:`launched_width`. So this is an observation after all, and the
    dispatched value is only the fallback for when the host read fails.

    When both are available and they DISAGREE, that is reported and refused
    rather than resolved: it means the server being measured is not the one this
    run launched, and picking either number would be picking which of two
    contradictory facts to believe.

    **Do not read the width off `/metrics`.**
    ``vllm:cache_config_info`` carries ``kv_cache_max_concurrency``, which
    looks like the width and is not the flag: it is KV-cache capacity.
    """
    serve = serve or {}
    dispatched = serve.get("max_num_seqs")
    observed = launched_width(host) if host else {"value": None, "source": None}

    if (
        observed["value"] is not None
        and dispatched is not None
        and observed["value"] != dispatched
    ):
        return {
            "value": None,
            "provenance": "contradicted",
            "refused": (
                f"the running server reports --max-num-seqs "
                f"{observed['value']} in its {observed['source']} arguments, "
                f"and this run dispatched {dispatched}. The server being "
                "measured is not the one this run launched."
            ),
            "observed": observed["value"],
            "dispatched": dispatched,
        }
    if observed["value"] is not None:
        return {
            "value": observed["value"],
            "provenance": "observed",
            "source": f"--max-num-seqs in the server's {observed['source']} arguments",
            "dispatched": dispatched,
            "refused": None,
        }
    if dispatched is not None:
        return {
            "value": dispatched,
            "provenance": "dispatched",
            "source": (
                "serve.max_num_seqs passed by this run; the host read returned "
                "nothing, so this is what we asked for rather than what is running"
            ),
            "refused": None,
        }
    return {
        "value": None,
        "provenance": None,
        "refused": (
            "no width could be read from the running server and this run did "
            "not dispatch one"
        ),
    }


_RUNNING = re.compile(r"^vllm:num_requests_running(?:\{[^}]*\})?\s+([\d.]+)", re.M)
_WAITING = re.compile(r"^vllm:num_requests_waiting(?:\{[^}]*\})?\s+([\d.]+)", re.M)


def in_flight(base: str) -> dict[str, Any] | None:
    """How many requests this engine is running, and how many are queued.

    The metrics surface shows the width live: ``vllm:num_requests_running`` is
    what the scheduler admitted, ``vllm:num_requests_waiting`` is what it did
    not. Asked while a level is in flight, the pair says whether the width ever
    opened.

    ``None`` on any failure. This is an observation offered beside a
    measurement, not a gate: a metrics endpoint that did not answer must not
    turn a good curve into a refusal.
    """
    text = contract.get_text(contract.url(base, "/metrics"), timeout=5.0)
    if text is None:
        return None
    running = _RUNNING.search(text)
    waiting = _WAITING.search(text)
    if running is None and waiting is None:
        return None
    return {
        "running": int(float(running.group(1))) if running else None,
        "waiting": int(float(waiting.group(1))) if waiting else None,
    }


def serving_config(base: str) -> dict[str, Any]:
    """The whole engine config, parsed and pinned as two digests.

    `product_sha256` pins the code and `weights_sha256` the weights; the
    settings between them — dtype, KV dtype, prefix caching, the kernels,
    structured-output enforcement — decide the output, and this is where they
    are recorded.
    """
    info = contract.get_json(contract.url(base, "/server_info"), timeout=15.0)
    raw = (info or {}).get("vllm_config") if isinstance(info, dict) else None
    if not isinstance(raw, str):
        return {
            "refused": (
                "the engine config is on /server_info, which exists only under "
                "VLLM_SERVER_DEV_MODE=1 — measured 404 without it"
            )
        }
    # The engine config carries `model='/path/…'` and `download_dir`, so it is
    # scrubbed like any other host reading before anything is derived from it.
    parsed = dict(contract.scrub(fingerprint.parse_repr("Config(" + raw + ")")))
    parsed.pop("_type", None)
    try:
        printed: dict[str, Any] = fingerprint.fingerprint(parsed)
        return printed
    except fingerprint.UnclassifiedError as error:
        # Recorded, never guessed at. A field this build has and the
        # classification does not is a fact about a version gap.
        return {"refused": str(error), "parsed": parsed}


def _running_config(base: str) -> dict[str, Any]:
    """What the server says it was configured with, where it will say it.

    The engine config arrives as a Python ``repr`` rather than a JSON object,
    so a handful of settings are lifted by name. Narrow on purpose: the whole
    string is captured verbatim by the description, so a value this misses is
    still on disk, and a repr that changes shape degrades to nothing found
    rather than to a wrong number.
    """
    info = contract.get_json(contract.url(base, "/server_info"), timeout=15.0)
    raw = (info or {}).get("vllm_config") if isinstance(info, dict) else None
    if not isinstance(raw, str):
        return {}
    raw = str(contract.scrub(raw))
    found: dict[str, Any] = {}
    for key in ("model", "quantization", "seed", "max_seq_len", "dtype"):
        for token in raw.split(","):
            name, _, value = token.strip().partition("=")
            if name == key and value:
                found[key] = _number(value.strip().strip("'\""))
                break
    return found


def _matches(running: dict[str, Any], serve: dict[str, Any]) -> bool:
    """Whether a running server already has the requested serving parameters.

    Only the window is compared — ``running`` comes from the text form of
    ``/server_info``, which leaves the batch width out, so a requested width
    always forces a restart.
    That is the safe direction: restarting costs a minute, and measuring the
    wrong width costs the result.
    """
    if "max_num_seqs" in serve:
        return False
    wanted = serve.get("max_model_len")
    return wanted is None or running.get("max_seq_len") == wanted


def _container_names(readings: dict[str, Any]) -> list[str]:
    raw = (readings.get("containers") or {}).get("stdout") or ""
    return [line.split()[0] for line in raw.splitlines() if line.strip()][:5]


def _number(raw: str) -> Any:
    """``raw`` as an int where it is one, else unchanged."""
    try:
        return int(raw)
    except ValueError:
        return raw


#: Where a launched server's startup log lives, per launcher. Both are written
#: by :func:`_start` — the pip path redirects into the file, the docker path
#: leaves it to the daemon — so this is a fact about our own launcher and not a
#: guess about the host.
RESOLVED_LOG_READS: dict[str, str] = {
    "pip": "cat /tmp/vllm-serving.log 2>/dev/null || true",
    "docker": f"docker logs {CONTAINER_NAME} 2>&1 || true",
}


def resolved_serving(
    host: str, base: str, serve: dict[str, Any] | None = None
) -> dict[str, Any]:
    """What the engine RESOLVED on ``host``, read from a server that came up.

    **The success-path reader.** :func:`_start` reads the log only when a cell
    has already died, so a configuration that serves perfectly is one nothing
    else describes.

    Two sources, both required, because neither alone holds the fields:
    ``/server_info`` carries the numerics and calls the kernels ``'auto'``; the
    startup log names the kernels the engine actually chose. See
    :data:`fingerprint.RESOLVED_READS`.

    The ``asked`` side comes from this run's own ``serve`` dict, so a
    disagreement is between what we dispatched and what came back — not between
    two readings of the server.
    """
    serve = serve or {}
    info = contract.get_json(
        contract.url(base, "/server_info?config_format=json"), timeout=30.0
    )
    config = (info or {}).get("vllm_config") if isinstance(info, dict) else None
    if not isinstance(config, dict):
        # The bare endpoint answers the same config as a Python repr, which
        # `serving_config` already parses. Falling back to it rather than
        # refusing: a build that does not honour `config_format=json` still
        # states its configuration, and the fields are reached by leaf name.
        raw = (info or {}).get("vllm_config") if isinstance(info, dict) else None
        if not isinstance(raw, str):
            raw = None
            answered = contract.get_json(
                contract.url(base, "/server_info"), timeout=30.0
            )
            if isinstance(answered, dict) and isinstance(
                answered.get("vllm_config"), str
            ):
                raw = answered["vllm_config"]
        if raw is None:
            return {
                "serving_resolved_sha256": None,
                "refused": (
                    "/server_info answered no engine config in either format. It "
                    "exists only under VLLM_SERVER_DEV_MODE=1 — measured 404 "
                    "without it"
                ),
                "resolved": {},
                "disagreements": [],
            }
        config = dict(
            contract.scrub(fingerprint.parse_repr("Config(" + str(raw) + ")"))
        )
        config.pop("_type", None)

    how = launcher(host)
    read = RESOLVED_LOG_READS.get(how)
    log = contract.ssh(host, read) if read else None
    block = fingerprint.resolved(
        log_lines=str(contract.scrub(log or "")).splitlines(),
        config=config,
        asked=_asked(serve),
    )
    block["launcher"] = how
    block["log_read"] = read
    described: dict[str, Any] = block
    return described


def _asked(serve: dict[str, Any]) -> dict[str, Any]:
    """This run's request, keyed by the flag or variable that carries it.

    Flags arrive as a flat list (``["--dtype", "float16"]``), which is the shape
    `_start` builds and the shape the sweep records, so a value is the token
    after its name. A bare flag with no value — ``--enforce-eager`` — maps to
    ``True``: it is asked-for-ness itself, and recording it as ``None`` would put
    it in the same state as a flag nobody passed.
    """
    asked: dict[str, Any] = dict(serve.get("env") or {})
    flags = list(serve.get("flags") or [])
    for index, token in enumerate(flags):
        if not token.startswith("--"):
            continue
        following = flags[index + 1] if index + 1 < len(flags) else None
        asked[token] = (
            True if following is None or following.startswith("--") else following
        )
    return asked
