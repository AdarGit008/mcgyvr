#!/usr/bin/env python3
"""The vLLM backend: how this engine yields the card, takes it, and describes itself.

Implements the contract in :mod:`contract`. **This file names no other backend
and must not**: it knows how to stop being on the GPU and how to get itself onto
it, and who else wants the card is the orchestrator's decision, never this
module's.

**This engine claims the card for the life of the process, not per model.** It
allocates its whole budget at startup — weights, then KV cache filling the rest —
and holds it whether or not a request is in flight. Since ADR-0039 that budget
is declared in **bytes of KV cache** (:func:`_memory_args`) rather than as a
fraction of the card, because ``requested = total_memory * util`` means one
fraction is a different KV cache on every card it is carried to.

So :func:`claim` is not "load a model" but "be running, with these serving
parameters, and prove it": an *empty* card
means the server died, which is the opposite sense from an engine that loads
per request. That asymmetry is why cleanup is parameterised by which engine is
under test rather than applied uniformly — an earlier uniform version stopped
this engine immediately before measuring it.

**One flag decides how much this engine will say about itself.**
``/server_info`` carries the quantization, the seed and the served window, and
exists only when the server was launched with ``VLLM_SERVER_DEV_MODE=1``.
Measured 2026-08-18 by diffing the server's own route table with and without it:
43 routes declared against 25, exactly 18 gated, and ``/server_info`` returning
404 when unset. With the flag this engine answers three of the four probe-set
fields; without it, one. That is a fact about how the server was started rather
than a limit on what it can report, and the launcher below sets it deliberately.

**The batch width is on no endpoint.** ``max_num_seqs`` appears nowhere:
searched across every parameterless GET in the server's own ``/openapi.json``
route table, on two hosts — not in ``/server_info``'s engine config, not in any
of the 122 metrics series, not on the model card. ``cache_config_info`` carries
``kv_cache_max_concurrency``, which looks like the answer and is KV-cache
capacity: a server launched with 8 reported 16.004, one launched with 16
reported 5.314. It moves *opposite* to the quantity it resembles, so it is never
substituted. The width is recovered by the ramp instead.
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

NAME = "vllm"

#: The port this engine ships on.
PORT = 8000

#: How long to wait for a server to become ready after being started.
START_TIMEOUT_S = 900.0

#: How long a weights digest may take. Measured 7.3s per 1.61 GB, so this
#: covers a checkpoint far larger than anything these rigs hold.
DIGEST_TIMEOUT_S = 1800.0

#: Hashed on the serving host, because the checkpoint is there and the client
#: is not. Tensor-wise in sorted key order across every shard, so the digest is
#: a property of the WEIGHTS rather than of how they happen to be sharded or
#: laid out — two identical models split into different numbers of files hash
#: the same, and a re-quantization does not.
#:
#: Measured cost on a 1.61 GB checkpoint: 731 tensors, 7.3 seconds. A 5.3 GB
#: model is proportionally ~25s, which is why the result is cached by snapshot
#: path and mtime rather than recomputed per survey.
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
                # `.numpy()` REFUSES bfloat16 — the default dtype for a great
                # many checkpoints — so the bytes come from the tensor's own
                # untyped storage instead. Measured on this host's torch:
                # float16, bfloat16, int32 and uint8 all yield bytes this way,
                # while `.numpy()` fails on bfloat16 alone. A first attempt used
                # `view(dtype=None)`, which is not a valid call at all and
                # failed on every dtype — caught by running it.
                # `.numpy()` REFUSES bfloat16 and `untyped_storage()` is worse
                # than wrong: safetensors MMAPS the shard, so a tensor is a view
                # into the whole file and its storage is the entire mapping —
                # hashing it would digest the file once per tensor. Reinterpret
                # the tensor's own elements as bytes instead. Measured on this
                # host's torch: float16, bfloat16, int32 and uint8 all work.
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


#: What the process holding the card is called. vLLM renames its GPU worker
#: with ``setproctitle``, so the process ``nvidia-smi`` attributes the memory to
#: has a command line of exactly this — **no model, no flags, nothing to join
#: on**. Measured on both rigs 2026-08-22, and it is why the reading below walks
#: to the parent instead of matching the pid's own line.
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

#: How far up the parent chain a compute-app pid is followed. Measured: the
#: model is on the **immediate** parent in both deployment shapes, so this is
#: slack, not a search — three hops and then the answer is ``None``.
_OWNER_HOPS = 3


def _process_tree(raw: str | None) -> dict[int, dict[str, Any]]:
    """:data:`PROCESS_TREE_COMMAND`'s output as ``{pid: {"ppid", "args"}}``.

    A pure parser over what the host printed, so the join it feeds is testable
    against the lines the rigs really produced (ADR-0016) rather than against a
    shape imagined for it.
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
    <model>``, which is what both rigs run:

    - srv1, installed with pip:  ``/usr/bin/python3 ~/.local/bin/vllm serve Qwen/…``
    - srv2, inside the container: ``/usr/bin/python3 /usr/local/bin/vllm serve Qwen/…``

    Measured 2026-08-22. The two deployment shapes differ only in the path to
    the ``vllm`` binary, which is why one join covers both.
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
    engine's, and it is never *guessed* to be. The llama-server that shares the
    card in a co-residency cell arrives here and leaves as ``None``: naming it
    would be this backend claiming about another engine's model, which is the
    one thing this module must not do.
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

    Public, and shaped like the other backend's ``residents``, because ``run.py``
    calls it on every backend after a ramp (BL-6). Until #345 only one backend
    defined it, so a vLLM co-residency cell recorded an ``AttributeError`` as
    its evidence.

    **It answers about this engine only, and so does the other backend's.** A
    neighbour served by the other engine is missing from both lists, so a
    cross-engine cell's post-ramp verdict read ``held: false``. That is #343 and
    #346's layer, not this one's, and it is stated here so the gap is read as
    filed rather than as fixed.
    """
    base = probe(host)
    return [] if base is None else inventory(host, base)


def placements(host: str) -> list[dict[str, Any]]:
    """Where every process on this card sits, as far as this engine can say.

    **The fraction has no analogue here, and that is a decision, not a gap**
    (ADR-0040). An engine that loads through llama.cpp can report
    ``size_vram / size`` because it *spills*: a model can be 6.8% on the card
    and answer ``200`` anyway. vLLM cannot —
    ``requested = ceil(total * util)`` with a hard ``free >= requested``
    precondition means it takes its whole allocation or refuses to start — so
    there is no denominator to divide by. Every row therefore carries
    ``fraction: None`` **with the reason beside it**, rather than the ``1.0``
    that would be true by this engine's contract and would invite a reader to
    compare it against the other engine's ``0.068`` as though the two were one
    measurement (ADR-0038 D4).

    The absolute number is reported instead, in MiB, from the driver:

    - srv1, pip, 2026-08-22: pid 1133972 (``VLLM::EngineCore``) **3126 MiB**,
      its parent the ``vllm serve Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ`` line.
    - srv2, docker, same day, same entry: pid 364842, **3174 MiB**.
    - Co-resident on srv1 with a 1.5B served by the other engine: a second
      holder, 1196 MiB, whose parent is that engine's server — reported as a
      row this engine cannot name rather than dropped.

    MiB and not bytes: ``nvidia-smi`` attributes per-process memory to the MiB,
    so a byte count here would be precision nobody measured, and the tree
    already records footprints in MiB (``srv-full.json``'s ``_footprint_mib``).

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
                    "is no denominator (ADR-0040)"
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
                        "there is no denominator (ADR-0040)"
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
    that looks like (ADR-0027 D2). Broad on purpose — every exception here is a
    failure to observe, and there is no shape of it that should end a claim.
    """
    try:
        return placements(host), None
    except Exception as error:
        return None, f"{type(error).__name__}: {error}"


def readings(host: str) -> dict[str, Any]:
    """This engine's own footprint on the machine."""
    reads = {
        "processes": "ps -eo args | grep -E '[v]llm (serve|.*api_server)' || true",
        "containers": f"docker ps --filter ancestor={CONTAINER_IMAGE} "
        "--format '{{.Names}} {{.Status}}' | head -5 || true",
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


def release(host: str) -> dict[str, Any]:
    """Stop serving and give up the card. Only this engine's own processes.

    Three process shapes, because covering fewer leaves the card held: a pip
    install runs as ``python3 .../bin/vllm serve``, a container runs
    ``vllm.entrypoints.openai.api_server``, and the engine core is a third name
    again. Measured 2026-08-18 — patterns covering only the last two left a
    server holding 4,916 MiB through an entire survey, and every model measured
    behind it was loaded onto the CPU.

    The bracket in each pattern is not cosmetic: ``pkill -f`` matches against
    its own shell's command line, and an unbracketed pattern kills the session
    before it kills the server.
    """
    steps: list[dict[str, Any]] = []

    def run(name: str, command: str) -> str | None:
        stdout = contract.ssh(host, command)
        steps.append({"step": name, "command": command, "stdout": stdout})
        return stdout

    # **E8, 2026-08-19.** This filtered on the bare repo name, which docker
    # resolves to `:latest`. It matched a `:v0.26.0` container only because both
    # tags happened to share an image id — verified empirically on srv2, and a
    # coincidence, not a mechanism. Pull a newer `latest` and the filter stops
    # matching while `released` below still reports True, because that flag is a
    # `pgrep` for a bare process a container never shows. `run.py` trusts it as
    # the ONLY exclusion gate, so the campaign would have measured the next
    # engine behind a live allocation of ours, with nothing in the record
    # looking wrong.
    run(
        "stop_containers",
        f"docker ps --filter ancestor={CONTAINER_IMAGE} "
        "--format '{{.Names}}' | xargs -r docker stop >/dev/null 2>&1; true",
    )
    run(
        "kill_processes",
        "pkill -f '[v]llm serve' 2>/dev/null; "
        "pkill -f '[v]llm.entrypoints' 2>/dev/null; "
        "pkill -f '[V]LLM::EngineCore' 2>/dev/null; sleep 8; true",
    )
    gpu = run("gpu_memory", "nvidia-smi --query-gpu=memory.used --format=csv,noheader")
    # `released` is a statement about THIS backend, not about the card. Reading
    # total VRAM made a backend that holds nothing report failure whenever
    # ANOTHER engine held the card — so the orchestrator's exclusion gate
    # refused the very engine it was about to measure. With the shipped config
    # that meant the third entry was refused on every host while the family
    # verdict quietly reported "2 of 3".
    # A containerised server is NOT a `vllm serve` process on the host, so this
    # count alone read 0 on the docker rig no matter what the container was
    # doing — `released: True` on a card we had not freed. Both are counted.
    mine = run(
        "own_processes",
        # **BL-B: `-f`.** Without it `pgrep` matches the process NAME, which can
        # never contain a space, so this counted 0 against a live
        # `vllm serve …` every time — verified at 0 where `pgrep -cf` returns 2.
        # On the pip rig, with no container to count either, `released` was
        # therefore unconditionally True, and `run.py` trusts that flag as the
        # ONLY exclusion gate before every entry of the next engine. The three
        # patterns are the three this function actually kills.
        "{ pgrep -cf '[v]llm serve|[v]llm[.]entrypoints|[V]LLM::EngineCore' "
        "2>/dev/null || echo 0; } | head -1",
    )
    boxes = run(
        "own_containers",
        f"docker ps --filter ancestor={CONTAINER_IMAGE} -q 2>/dev/null | wc -l "
        "|| echo 0",
    )
    remaining = contract.first_int(mine)
    containers = contract.first_int(boxes)
    used = contract.first_int(gpu)
    return {
        "backend": NAME,
        "steps": steps,
        "gpu_used_mib": used,
        "own_processes_remaining": remaining,
        "own_containers_remaining": containers,
        "released": remaining == 0 and (containers or 0) == 0,
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

    **DE-7, 2026-08-19.** ``**declared`` absorbs the per-entry declarations the
    orchestrator forwards for backends that model them — ``placement``,
    ``coresident``, ``coresident_with``. Without it, a config entry naming any
    of those on a vLLM entry raised ``TypeError`` inside the claim guard and was
    recorded as a refusal, with the orchestrator's own comment three lines away
    asserting that "a backend that does not model placement is unaffected". What
    it ignored is written down rather than dropped, because an entry that
    believes it declared something nothing reads is the defect D4's whole
    replacement mechanism exists to avoid.

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
    ignored = {key: value for key, value in declared.items() if value}
    # BEFORE anything ACTS. A pin naming a field this backend does not compute
    # is a config that believes it is pinned and is not — and the check has to
    # precede `_start`, which stops the running server and relaunches it. Placed
    # after, it "refused" a run whose server had already been killed, and its
    # message called `weights_sha256`, a remote tensor hash budgeted at 1800s:
    # a config typo cost a restart and up to half an hour to render a sentence.
    unknown = set(expect) - {"weights_sha256"}
    if unknown:
        raise contract.NotCleanError(
            f"{model} on {host}: {sorted(unknown)} is not this backend's pin. "
            "`model_sha256` is a manifest digest — another engine's addressing "
            "of a packaged model — and this engine has none. The weights pin "
            "here is `weights_sha256`, a sha256 over every tensor's bytes in "
            "the checkpoint. Nothing was measured, and nothing was restarted."
        )
    # #325: the whole claim on a timeline, not only its launch as a delta.
    # `start_seconds` below says how long the launch took; this says WHEN the
    # claim ran, so a ramp phase's minutes can be attributed row by row.
    claim_started_at = contract.now()
    running = _running_config(base)
    if running and running.get("model") == model and _matches(running, serve):
        started = {"restarted": False, "reason": "already serving this configuration"}
    else:
        started = _start(host, model, serve)
        base = f"http://{host}:{PORT}"

    gpu = contract.ssh(host, "nvidia-smi --query-gpu=memory.used --format=csv,noheader")
    allocated = contract.first_int(gpu)
    # #327: the card's state at the claim, beside its memory -- the point the
    # ramp that follows starts from. Null + the command when it did not answer.
    card = contract.card_state(contract.ssh(host, contract.CARD_STATE_COMMAND))
    config = _running_config(base)
    served = inventory(host, base)
    # **#345, the claim side.** The same question the other backend's `claim`
    # asks of the card since #335: not "did it come up" but "what is on this card, and
    # where". `allocation_present` above is a threshold over the card's TOTAL,
    # so it says yes to a card whose memory belongs to somebody else. Recorded
    # and never gated, for the campaign's own reason — a shared card is the
    # frontier being mapped, and a claim that refused one would refuse its own
    # question.
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
        # ADR-0027 D2: null carries the reason it is null, never a blank.
        "resident_placements_refused": placed_refused,
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
            # Written down rather than dropped: a config that declares something
            # nothing reads is the defect D4's replacement exists to avoid, and
            # silence here would make it invisible.
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

    ``serve`` is the block this run launched with. It is a parameter rather
    than something read back because this engine states ``max_num_seqs``
    nowhere on the wire — see :func:`declared_slots`.
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
    # Per-invocation path and `&&`-chained. Newline-separated with a fixed
    # name, a failed write left a PREVIOUS run's script in place and its output
    # was taken as this model's digest — and `contract.ssh` reports neither the
    # return code nor stderr, so nothing would have said so.
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
        # #326: `contract.ssh` answers None for a timeout and for every other
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
    # written to a tracked path. The three host-derived returns on this backend
    # each bypassed it; a leak test that planted secrets only in the other
    # readings could not have found that.
    result = dict(contract.scrub(result))
    # **D6/D7 item 7.** DIGEST_TIMEOUT_S has no scaling curve behind it because
    # the duration was never recorded next to the size. `bytes` is already in
    # the result, so one number here turns every campaign digest into a point on
    # that curve — at no rig time, and unrecoverable afterwards.
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

#: Where the weights cache is mounted inside the container.
CONTAINER_CACHE = "/root/.cache/huggingface"


def launcher(host: str) -> str:
    """How this engine is deployed here: ``pip``, ``docker``, or ``none``.

    **Both shapes exist on these rigs and the difference is not cosmetic.** One
    host has the package installed and runs ``vllm serve``; the other has only
    the container image and no ``vllm`` binary *and no torch at all*, so a
    launcher that assumed the first would simply fail there — and so would the
    weights digest, which needs torch to read a checkpoint. Detected rather than
    configured, because it is a property of the machine and a config that had to
    state it would be a config that could state it wrongly.
    """
    if contract.ssh(host, "command -v vllm 2>/dev/null || true"):
        return "pip"
    if contract.ssh(host, f"docker images -q {CONTAINER_IMAGE} 2>/dev/null || true"):
        return "docker"
    return "none"


#: The two ways an entry may state the memory it wants. **Exclusive, and
#: neither is defaulted** (ADR-0039). This engine's own arithmetic is
#: ``requested = total_memory * gpu_memory_utilization`` with a hard
#: ``free >= requested`` precondition (``vllm/v1/worker/utils.py``), so a
#: fraction is a statement about a *card*: 1,792 MiB of KV cache is 0.565 on
#: srv1 and 0.273 on srv2, and one number cannot be right for both. Bytes are a
#: property of the model and travel.
MEMORY_FIELDS: tuple[str, ...] = ("kv_cache_memory_bytes", "gpu_memory_utilization")


def _memory_args(serve: dict[str, Any]) -> list[str]:
    """The KV-cache declaration as CLI arguments, or a refusal (ADR-0039).

    **There is no default.** This read ``serve.get("gpu_memory_utilization",
    0.85)``, and that fallback is how a number nobody chose -- traced to
    local-ai's OOM fix for a 12 GB card, applied unchanged to a 6 GB one --
    reached five sites and every vLLM figure this project holds. Measured
    2026-08-22 at ``max_num_seqs 8``: 0.85 buys 131,104 KV tokens on srv1 and
    322,304 on srv2 where the declaration can reach 65,536, so the entry paid
    for 2.0x and 4.9x what it could use and left a neighbour 93% on the CPU.

    **Both fields together is a refusal, not a precedence rule.** vLLM's own
    precedence is that ``kv_cache_memory_bytes`` silently ignores
    ``gpu_memory_utilization``; honouring that here would let a config state a
    fraction, have it discarded, and read as though it had been applied -- a
    config that believes it declared something it did not, which is the shape
    ``claim``'s ``expect``/``placement`` guards above already refuse.
    """
    declared = [field for field in MEMORY_FIELDS if serve.get(field) is not None]
    if len(declared) > 1:
        raise contract.NotCleanError(
            f"serve declares {sorted(declared)} together. They are exclusive: "
            "vLLM ignores gpu_memory_utilization whenever kv_cache_memory_bytes "
            "is set, so carrying both records a fraction that never applied. "
            "Declare one (ADR-0039). Nothing was measured."
        )
    if not declared:
        raise contract.NotCleanError(
            "serve declares neither kv_cache_memory_bytes nor "
            "gpu_memory_utilization, and there is no default (ADR-0039 rule 3). "
            "Bytes are max_num_seqs * max_model_len * bytes_per_token and are "
            "the same on every card; a fraction is a statement about one card "
            "and says which and why. Nothing was measured."
        )
    if declared[0] == "kv_cache_memory_bytes":
        return ["--kv-cache-memory-bytes", str(int(serve["kv_cache_memory_bytes"]))]
    return ["--gpu-memory-utilization", str(serve["gpu_memory_utilization"])]


#: One vLLM allocation block. All three refusals of 2026-08-23 died on the same
#: sentence — *"Tried to allocate 256.00 MiB"* — so a declaration that leaves
#: less than one block spare does not launch, whatever the rest of the sum says.
ALLOCATOR_BLOCK_MIB = 256

#: What a vLLM process holds on this card BESIDES its weights and the KV cache
#: it declares, plus the one block it must still be able to take.
#:
#: **Measured, as a residue, not assembled from terms.** The first version of
#: this constant added up ADR-0039's parts — 470 MiB driver and CUDA context,
#: 133 MiB peak activation, 51 MiB non-torch, one 256 MiB block — and got 910.
#: That sum double-counts: ``nvidia-smi``'s view of the card already contains
#: the driver's reserve and the process's context, so those terms were being
#: charged twice. The refit campaign of 2026-08-23 measured the residue
#: directly, as ``card_mib_after_load - weights - declared_kv``, on three cells
#: spanning 2.5 and 9.38 GiB of weights and 1.5 to 7.9 GiB of KV cache:
#:
#:     srv1 / Qwen3-4B   len 2048   card  5,222   residue  358 MiB
#:     srv2 / 14B        len 1024   card 11,479   residue  337 MiB
#:     srv2 / Qwen3-4B   len 7168   card 11,101   residue  477 MiB
#:
#: So the residue is 337–477 MiB and does not track model size — it tracks the
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


def _mib(byte_count: float) -> int:
    """Bytes as whole MiB, rounded up — a partial block is a held block."""
    return int(-(-byte_count // (1024 * 1024)))


def free_mib(host: str) -> int | None:
    """How much card this host has free right now, or ``None`` if it did not say.

    Total minus used rather than a ``memory.free`` query, so the two figures the
    arithmetic quotes come off one line and cannot describe two moments. ``None``
    when the card did not answer — never ``0``, which would read as a full card
    and refuse every declaration on a host whose driver was merely wedged.
    """
    line = contract.ssh(
        host,
        "nvidia-smi --query-gpu=memory.total,memory.used --format=csv,noheader,nounits",
    )
    parts = (
        [p.strip() for p in (line or "").strip().splitlines()[:1][0].split(",")]
        if (line and line.strip())
        else []
    )
    if len(parts) != 2:
        return None
    total, used = contract.first_int(parts[0]), contract.first_int(parts[1])
    return None if total is None or used is None else total - used


def declaration_fits(
    host: str, model: str, serve: dict[str, Any], free_mib: int | None
) -> None:
    """Refuse a KV declaration this card cannot hold — before the launch.

    **#354.** ADR-0039's rule is
    ``max_num_seqs x max_model_len x bytes_per_token``, and it is right: three
    cells of the 2026-08-23 footprint campaign refused on an *empty* card with
    ``torch.OutOfMemoryError`` inside ``_allocate_kv_cache``, and in every one
    of the three the declared figure was **exactly** what the entry's own shape
    computes. Qwen3-4B is 36 layers x 8 KV heads x 128 x 2 x 2 = 147,456 B/token
    and 65,536 tokens of it is 9,663,676,416 bytes, which is 9.0 GiB on a card
    that holds 6.0. The rule is arithmetically correct and produces a
    declaration these cards cannot hold, because every vLLM figure this project
    had came from the 1.5B, whose KV geometry is four times narrower per layer.

    Nothing refused it until vLLM did, **three minutes and one cell later**, in
    a message about a number the entry had computed correctly. This is the same
    arithmetic, run in milliseconds, against figures that already exist.

    **Two sources, and the measured one wins.** An entry that has already loaded
    on this host carries ``_footprint_mib`` — what the card said the process
    took — and that is a fact, not a prediction: a footprint that was observed
    to fit needs no model of why. Only an entry with no measurement for this
    host is predicted, from its declared weights plus its declared KV plus
    :data:`NON_KV_OVERHEAD_MIB`. The refusal says which of the two it used, so a
    reader is never left to guess whether a number was seen or computed.

    **A fraction is not checked here** (ADR-0039 rule 5 keeps one legal for a
    run whose question *is* the fraction). Under ``gpu_memory_utilization`` this
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
    if measured is not None:
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
                "engine prints `Model loading took X GiB` on every start "
                "(ADR-0039 rule 2's idiom, extended to weights by #354). "
                "Nothing was measured."
            )
        weights_mib = _mib(int(weights))
        required_mib = weights_mib + kv_mib + NON_KV_OVERHEAD_MIB
        how = "predicted"

    if required_mib <= free_mib:
        return

    if how == "measured":
        raise contract.NotCleanError(
            f"{model} on {host}: this entry took {required_mib:,} MiB on this "
            f"card when it was measured, and {free_mib:,} MiB is free now — "
            f"{required_mib - free_mib:,} MiB short. The declaration is "
            f"{int(kv_bytes):,} B of KV cache. Refused before the launch "
            "(#354). Nothing was measured."
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
        "configuration nobody declared (ADR-0039 rule 2, #354). "
        "Nothing was measured."
    )


def _ways_out(serve: dict[str, Any], budget_mib: int) -> str:
    """The two declarations that would fit, each with its figure.

    ``max_num_seqs`` and ``max_model_len`` enter the requirement as a product,
    so either one alone can be brought under the budget and both land on the
    same number of KV tokens. They are named together and neither is applied.
    """
    per_token = serve.get("bytes_per_token")
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


def _start(host: str, model: str, serve: dict[str, Any]) -> dict[str, Any]:
    """Launch the server with ``serve``, and wait for it to answer.

    ``VLLM_SERVER_DEV_MODE=1`` is set deliberately: it is what makes the
    quantization and the seed readable at all, and this is a measurement rig on
    a private network. It should not be set on anything exposed — the flag also
    opens 18 routes that change the server, including one that executes a method
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
    # Values were quoted and KEYS were not, which put config text straight into
    # a shell: an `env` key of `A; touch /tmp/x; B` became a command. A variable
    # name is a narrow shape, so it is validated rather than quoted — quoting a
    # key would produce a name no shell would export, hiding the typo instead of
    # naming it.
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
    # The loop's own worst case is (curl 5s + sleep 10s) per iteration, so the
    # ssh budget has to cover THAT, not START_TIMEOUT_S alone. It previously
    # allotted 960 s to a loop that could run 1350 s, so a slow start was cut
    # off by the client and recorded as if the server had never come up.
    # //20, not //15: each round is `curl -m 5` + `nvidia-smi` + `sleep 10`,
    # and on a box loading a 19 GB model the nvidia-smi is not free. At //15 the
    # loop's worst case was 900 s + 60 nvidia-smi calls against a 1020 s ssh
    # budget, which a 2 s nvidia-smi is enough to overrun — reinstating, in
    # smaller form, the very mismatch this fix was for.
    rounds = int(START_TIMEOUT_S // 20)
    # **A model is not ready when /health says 200.** Measured on these rigs:
    # /health answers before the weights are on the card. The check that holds
    # is 200 AND the card carrying an allocation — which is what
    # MIN_ALLOCATION_MIB exists for, and it was not being used here.
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
    # **Asserted, not merely recorded.** This was stored and never read, so a
    # server that never came up was measured against anyway — the exact shape of
    # failure the rest of this module exists to prevent.
    if (ready or "").split()[:1] != ["ready"]:
        raise contract.NotCleanError(
            f"vllm on {host} did not reach health with an allocation inside "
            # SCRUBBED. Host output carries credentials — a systemd
            # `Environment=` line, an exported launch command — and an exception
            # message is written to logs and to the run record like any other
            # field. The first version of this interpolated it raw.
            f"{START_TIMEOUT_S:.0f}s: {contract.scrub(ready)!r}. Launcher was "
            f"{how!r}. Nothing "
            "was measured. Check /tmp/vllm-serving.log on the host (pip) or "
            "`docker logs mcgyvr-vllm` (docker); the known causes here are a "
            "cold weights download inside the start budget and a KV cache that "
            "will not fit the card at the requested max_model_len."
        )
    # The recorded command contains the exported environment VALUES — the very
    # thing an `env` block is used to pass a key through — so what is written
    # down is scrubbed even though what was executed was not.
    return contract.scrub(
        {
            "restarted": True,
            "launcher": how,
            "command": command,
            "launched": launched,
            "ready": ready,
            # **D6/D7 item 7.** START_TIMEOUT_S has never been calibrated
            # against anything, because the one number that would calibrate it
            # was not recorded. Measured on the rigs at 33 s (srv1) and 109 s
            # (srv2) for a 1.5B; every launch in the campaign adds a point at
            # no cost, and the campaign is the only chance to collect them.
            "start_seconds": round(time.monotonic() - began, 2),
            "serve": serve,
        }
    )


def build(host: str) -> dict[str, Any]:
    """This engine's version on ``host``, for the identity block (#326).

    ``GET /version`` on a running server; a server that is not up answers
    nothing, and then the pip package or the container tag is asked. Each
    is named, so a ``null`` says which reads were tried.
    """
    answered = contract.get_json(
        contract.url(f"http://{host}:{PORT}", "/version"), timeout=10.0
    )
    if isinstance(answered, dict) and answered.get("version"):
        return {"serving_build": f"vllm {answered['version']}", "refused": None}
    command = (
        "vllm --version 2>/dev/null || "
        "python3 -c 'import vllm; print(vllm.__version__)' "
        f"2>/dev/null || (docker images -q {CONTAINER_IMAGE} >/dev/null 2>&1 "
        f"&& echo {CONTAINER_IMAGE})"
    )
    raw = contract.ssh(host, command)
    if raw:
        return {
            "serving_build": f"vllm {raw.strip().splitlines()[-1]}",
            "refused": None,
        }
    return {
        "serving_build": None,
        "refused": f"GET /version on port {PORT} answered nothing, then: {command}",
    }


def launched_width(host: str) -> dict[str, Any]:
    """The width the running server was actually started with, read off the host.

    **E5, revised 2026-08-19.** The first version concluded there was no observed
    source because no HTTP endpoint carries ``max_num_seqs`` — which is true, and
    was the wrong place to stop looking. The harness has ssh, and the flag is in
    the running process's own argv on the pip rig and in the container's
    ``Config.Cmd`` on the docker rig. Verified on both:
    ``vllm serve … --max-num-seqs 16 --port 8000`` and
    ``["…","--max-num-seqs","16",…]``.

    That is a genuine observation and it is strictly better than reading back the
    value this run intended, because the two can differ. ``claim`` has a path
    that does NOT restart a server already serving the wanted configuration, so
    on that path a server started by someone else — at some other width — would
    otherwise have been described using our own variable and nothing would have
    looked wrong.
    """
    for source, command in (
        (
            "process",
            # `COLUMNS=` explicitly: `ps` truncates its output to that width
            # when the variable is set, and `--max-num-seqs` sits ~110
            # characters into this argv. Non-interactive ssh normally does not
            # set it — normally is not a property worth depending on when the
            # consequence is silently reading no width at all.
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

    **No HTTP endpoint carries it.** Searched on a live vLLM 0.26.0 started
    ``--max-num-seqs 16``: ``/server_info`` (three top-level keys,
    ``vllm_config`` 3,118 characters), ``/v1/models``, and every environment
    block — ``'num_seqs'`` 0 hits, ``'seqs'`` 0 hits, ``'scheduler'`` 0 hits.

    **But the host has it**, in the server's own argv — see
    :func:`launched_width`. So this is an observation after all, and the
    dispatched value is only the fallback for when the host read fails.

    When both are available and they DISAGREE, that is reported and refused
    rather than resolved: it means the server being measured is not the one this
    run launched, and picking either number would be picking which of two
    contradictory facts to believe.

    **Do not "fix" the missing endpoint by reading `/metrics`.** It carries
    ``vllm:cache_config_info{kv_cache_max_concurrency="16.001953125"}``, which
    reads as 16 and is not the flag: it is
    ``kv_cache_size_tokens / max_model_len``. Measured on srv1 at **16.004 on a
    server launched ``--max-num-seqs 8``** — a positive disproof, not a caveat.
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


def serving_config(base: str) -> dict[str, Any]:
    """The whole engine config, parsed and pinned as two digests.

    Nothing else records HOW this engine was serving. `product_sha256` pins the
    code and `weights_sha256` the weights; the settings between them — dtype,
    KV dtype, prefix caching, the kernels, structured-output enforcement —
    decided the output and were on disk nowhere.
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
        return fingerprint.fingerprint(parsed)
    except fingerprint.UnclassifiedError as error:
        # Recorded, never guessed at. A field this build has and the
        # classification does not is a fact about a version gap.
        return {"refused": str(error), "parsed": parsed}


def _running_config(base: str) -> dict[str, Any]:
    """What the server says it was configured with, where it will say it.

    The engine config arrives as a Python ``repr`` rather than a JSON object —
    3,118 characters on the rig it was measured against — so the three settings
    that live only there are lifted by name. Narrow on purpose: the whole string
    is captured verbatim by the description, so a value this misses is still on
    disk, and a repr that changes shape degrades to nothing found rather than to
    a wrong number.
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

    Only the window is checkable here — the batch width is on no endpoint, so a
    requested change to it always forces a restart rather than being compared.
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
