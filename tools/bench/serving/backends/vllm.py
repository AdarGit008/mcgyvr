#!/usr/bin/env python3
"""The vLLM backend: how this engine yields the card, takes it, and describes itself.

Implements the contract in :mod:`contract`. **This file names no other backend
and must not**: it knows how to stop being on the GPU and how to get itself onto
it, and who else wants the card is the orchestrator's decision, never this
module's.

**This engine claims the card for the life of the process, not per model.** It
allocates a fraction of VRAM at startup — 0.85 or 0.90 on these rigs — and holds
it whether or not a request is in flight. So :func:`claim` is not "load a model"
but "be running, with these serving parameters, and prove it": an *empty* card
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
        "own_processes", "{ pgrep -c '[v]llm serve' 2>/dev/null || echo 0; } | head -1"
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
    running = _running_config(base)
    if running and running.get("model") == model and _matches(running, serve):
        started = {"restarted": False, "reason": "already serving this configuration"}
    else:
        started = _start(host, model, serve)
        base = f"http://{host}:{PORT}"

    gpu = contract.ssh(host, "nvidia-smi --query-gpu=memory.used --format=csv,noheader")
    allocated = contract.first_int(gpu)
    config = _running_config(base)
    served = inventory(host, base)
    digest = weights_sha256(host, model)
    wanted = expect.get("weights_sha256")
    check = {
        "started": started,
        "gpu_used_mib": allocated,
        "allocation_present": (allocated or 0) >= MIN_ALLOCATION_MIB,
        "served_models": served,
        "engine_config": config,
        "weights": digest,
        "weights_sha256_expected": wanted,
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
        "declared_slots": declared_slots(serve),
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
    args = [
        "--max-model-len",
        str(serve.get("max_model_len", 8192)),
        "--gpu-memory-utilization",
        str(serve.get("gpu_memory_utilization", 0.85)),
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


def declared_slots(serve: dict[str, Any] | None = None) -> dict[str, Any]:
    """What this engine was LAUNCHED with — it states this nowhere on the wire.

    **D1 split `declared_slots` from `saturation_n` on the understanding that
    the declaration is a read. For this engine it is not, and B1 of the step 0.1
    gaps list is the evidence.** Searched on a live vLLM 0.26.0 started
    `--max-num-seqs 16`: `/server_info` (three top-level keys, `vllm_config`
    3,118 characters), `/v1/models`, and every environment block — `'num_seqs'`
    0 hits, `'seqs'` 0 hits, `'scheduler'` 0 hits. There is no JSON path.

    So the value here can only come from what we dispatched, and it says so.
    A dispatched value labelled as an observation would be the one-field-two-
    meanings defect D1 fixed, reintroduced a level down.

    **Do not "fix" this by reading `/metrics`.** That endpoint carries
    ``vllm:cache_config_info{kv_cache_max_concurrency="16.001953125"}`` on that
    same server, which reads as 16 and is not the flag: it is
    ``kv_cache_size_tokens / max_model_len`` = 131088 / 8192. It agrees with the
    flag today by coincidence and diverges the moment either term moves.
    """
    serve = serve or {}
    value = serve.get("max_num_seqs")
    if value is None:
        return {
            "value": None,
            "provenance": "dispatched",
            "refused": (
                "this run did not launch the server, so there is no dispatched "
                "width — and this engine states max_num_seqs on no endpoint"
            ),
        }
    return {
        "value": value,
        "provenance": "dispatched",
        "source": "serve.max_num_seqs passed to `vllm serve` by this run",
        "refused": None,
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
