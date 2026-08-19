#!/usr/bin/env python3
"""The ollama backend: how this engine yields the card, takes it, and describes itself.

Implements the contract in :mod:`contract`. **This file names no other backend
and must not**: it knows how to stop being on the GPU and how to get itself onto
it, and who else wants the card is the orchestrator's decision, never this
module's. Adding a third engine must require no edit here.

**This engine does not serve models itself.** It starts llama.cpp's
``llama-server`` per loaded model and proxies to it, and that child carries the
settings the public API never exposes. Measured 2026-08-18: a host serving
``qwen2.5-coder:1.5b`` ran it as ``-c 8192 -np 2 --flash-attn auto -b 1024
-ub 1024 --context-shift --keep 4 --no-jinja --chat-template chatml``, and the
child's own ``/props`` and ``/slots`` on ``127.0.0.1`` answer two fields the
public API refuses outright — the slot count and the seed.

**Three facts are per MODEL, not per host, and assuming otherwise was wrong.**
On a host configured for two parallel slots, four of its five models were served
``-c 8192 -np 2`` and one was served ``-c 4096 -np 1``: the engine sizes context
and slots per model against the memory it has, so the configured value is a
ceiling rather than a setting. A one-model sample records 2 for a model that
gets 1, which is why :func:`claim` loads exactly the model it is asked about.

**Placement is decided at load time and is sticky.** A model loaded while
something else holds the card is placed on the CPU and stays there for the life
of its ``llama-server`` — measured at 0.08 GB of VRAM against a 1.17 GB model,
serving happily and 20x slower. Freeing the card afterwards does not migrate it
back. So :func:`claim` clears first and then *verifies the placement*, because
that ratio is the only reading which shows it.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import sys
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

NAME = "ollama"

#: The port this engine ships on.
PORT = 11434

#: A card holding less than this, after a release, is carrying nothing of ours.
#: Used to decide whether the card was actually idle before a load — a reading
#: of the CARD, which is what `card_idle_before_load` claimed to be and was not.
IDLE_BEFORE_LOAD_MIB = contract.IDLE_GPU_MIB

# **D4, 2026-08-19: `MIN_VRAM_FRACTION` is withdrawn as a gate.** It was 0.8, and
# it refused five real models as unmeasurable. The refusal it was built around —
# `gpt-oss:20b` at 0.794 — was never a failure: that model is a **MoE**, and a
# MoE holding a fifth of its bytes off-card is working as designed, not failing
# to load.
#
# No single number can be right here, because the fraction's MEANING depends on
# three things the number does not carry: the architecture (dense vs MoE),
# whether co-residency was intended, and the moment in the load at which the
# sample was taken. A gate that cannot state its own conditions is not a gate.
#
# What replaces it is a DECLARATION, per entry, in the survey config:
# `placement.expect`. An entry says what placement it expects and the run
# records what it got; a mismatch is reported against a stated expectation
# rather than against a constant that means different things per model.

#: How many times the whole clear-load-verify cycle is retried. The load is not
#: retried alone: what fails is a dirty card, and reloading onto one reproduces
#: the failure.
LOAD_ATTEMPTS = 2

#: A model may take this long to become resident. Generous because the point is
#: to record what a big model actually does — a 36 GB model against a 12 GB card
#: spills to RAM and takes minutes, and a wait that expired early would
#: attribute the NEXT model's readings to this one.
LOAD_TIMEOUT_S = 2400.0


def probe(host: str) -> str | None:
    """The base URL this engine answers on, or ``None``. Read-only."""
    base = f"http://{host}:{PORT}"
    return base if contract.get_json(contract.url(base, "/api/tags")) else None


def inventory(host: str, base: str) -> list[str]:
    """Every model this engine holds, loaded or not."""
    tags = contract.get_json(contract.url(base, "/api/tags"), timeout=20.0)
    rows = (tags or {}).get("models") if isinstance(tags, dict) else None
    if not isinstance(rows, list):
        return []
    return [str(row.get("name")) for row in rows if isinstance(row, dict)]


def readings(host: str) -> dict[str, Any]:
    """This engine's own footprint on the machine."""
    reads = {
        "service_environment": "systemctl show ollama -p Environment",
        "version": "ollama --version 2>/dev/null || true",
        "server_processes": "pgrep -af '[l]lama-server' || true",
        "resident": "curl -s -m 10 http://127.0.0.1:11434/api/ps || true",
    }
    # Scrubbed: a unit's `Environment=` line is where a key lives, and this is
    # written to a tracked path.
    return {
        name: {
            "command": command,
            "stdout": contract.scrub(contract.ssh(host, command)),
        }
        for name, command in reads.items()
    }


def release(host: str) -> dict[str, Any]:
    """Stop serving and give up the card. Only this engine's own processes.

    Three steps, because the first two are each insufficient on their own:

    1. Unload every resident model. Misses a model still *loading*, which is not
       yet listed — measured: a 36 GB model mid-load left the card at 9,985 MiB
       and the next measurement was taken on top of it.
    2. Kill the ``llama-server`` children, which frees the card immediately.
    3. Restart the service. Step 2 alone is not enough: the parent still
       believes a load is pending and respawns the child for a queued request,
       so the card is dirty again moments later. This is the only step measured
       to reliably return a host to an idle card.
    """
    steps: list[dict[str, Any]] = []

    def run(name: str, command: str) -> str | None:
        stdout = contract.ssh(host, command)
        steps.append({"step": name, "command": command, "stdout": stdout})
        return stdout

    run(
        "unload_resident",
        "curl -s -m 10 http://127.0.0.1:11434/api/ps "
        "| python3 -c \"import json,sys;print(' '.join(m['name'] "
        "for m in json.load(sys.stdin).get('models',[])))\" "
        "| tr ' ' '\\n' | while read -r m; do [ -n \"$m\" ] && "
        "curl -s -m 30 -X POST http://127.0.0.1:11434/api/generate "
        '-d "{\\"model\\":\\"$m\\",\\"keep_alive\\":0}" -o /dev/null; done; true',
    )
    # **E9, 2026-08-19.** ollama runs as `User=ollama` on both rigs, so this
    # `pkill` as the ssh user got EPERM on every match — silently, because
    # stderr was discarded and the step ended `; true`. The card still cleared,
    # via the service restart below, so the effect was right and the RECORD was
    # a lie: a cleanup step that cannot work, wrapped in a suppressor that hides
    # that it did not. Now it runs under `sudo -n` and its effect is read back.
    run(
        "kill_servers",
        "sudo -n pkill -f '[l]lama-server' 2>/dev/null; sleep 4; "
        "echo \"remaining=$(pgrep -c '[l]lama-server' 2>/dev/null || echo 0)\"",
    )
    run(
        "restart_service",
        "sudo -n systemctl restart ollama 2>/dev/null && echo restarted "
        "|| echo '(no passwordless sudo — the card may not fully clear)'",
    )
    run("settle", "sleep 8; echo settled")
    gpu = run("gpu_memory", "nvidia-smi --query-gpu=memory.used --format=csv,noheader")
    # `released` is a statement about THIS backend, not about the card. Reading
    # total VRAM made a backend that holds nothing report failure whenever
    # ANOTHER engine held the card — so the orchestrator's exclusion gate
    # refused the very engine it was about to measure. With the shipped config
    # that meant the third entry was refused on every host while the family
    # verdict quietly reported "2 of 3".
    mine = run("own_processes", "pgrep -c '[l]lama-server' 2>/dev/null || echo 0")
    remaining = contract.first_int(mine)
    used = contract.first_int(gpu)
    return {
        "backend": NAME,
        "steps": steps,
        "gpu_used_mib": used,
        "own_processes_remaining": remaining,
        "released": remaining == 0,
        # A reading of the CARD, separate from the statement about this backend.
        # `released` deliberately does not consult it: a backend that holds
        # nothing must not report failure because ANOTHER engine holds the card.
        # But `claim` needs to know whether the card was clear before a load, and
        # it was previously handed this backend's process count under that name.
        "card_used_mib": used,
        "card_idle": None if used is None else used < IDLE_BEFORE_LOAD_MIB,
    }


def claim(
    host: str,
    base: str,
    model: str,
    serve: dict[str, Any] | None = None,
    expect: dict[str, Any] | None = None,
    placement: dict[str, Any] | None = None,
    coresident: bool = False,
    coresident_with: list[str] | None = None,
) -> dict[str, Any]:
    """Load ``model`` and prove the card is in the state the entry declared.

    Loading is not the hard part; verifying is. Each check maps to a way a
    measurement here was silently ruined before it existed:

    1. **The card was idle before the load** — placement is decided then. This
       now reads the CARD (``release()["card_idle"]``). It previously read this
       backend's own process count under that name, so it was true whenever
       ollama held nothing, including when another engine held the whole card.
       D4 withdrew ``MIN_VRAM_FRACTION`` on the stated grounds that this check
       caught contamination separately; that was not true of the code, and this
       is what makes it true.
    2. **The model under test is resident**, and the full resident set is
       recorded. Requiring it to be the ONLY resident is now an entry's choice,
       not a law: D7 item 4 measures two models co-resident deliberately, and a
       gate that refuses by construction cannot express it. Entries default to
       sole residency, so nothing becomes laxer by accident.
    3. **Placement is recorded and compared to what the entry declared**
       (``placement.expect``), not to a global constant — see D4 above.
    4. **The weights are the ones expected**, when the caller pinned a digest. A
       tag is mutable: the same name re-pulled tomorrow serves different bytes,
       and every other check here still passes.

    Retries the whole cycle rather than the load, and raises
    :exc:`contract.NotCleanError` rather than returning something measurable.
    """
    serve = serve or {}
    expect = expect or {}
    placement = placement or {}
    # **D7 item 4 measures INTENDED co-residency**, which needs a neighbour
    # actually on the card — accepting one is not the same as arranging one.
    # Named models are loaded first, then the model under test, so what is
    # measured is this model sharing a card rather than this model alone.
    neighbours = list(coresident_with or [])
    if neighbours:
        coresident = True
    # A pin naming a field this backend does not compute is a config that
    # believes it is pinned and is not — checked before anything else, because
    # a verification that only runs on the failure path never runs at all.
    unknown = set(expect) - {"model_sha256"}
    if unknown:
        raise contract.NotCleanError(
            f"{model} on {host}: {sorted(unknown)} is not this backend's pin. "
            "The weights pin here is `model_sha256`, the manifest digest this "
            "engine lists for a tag. Nothing was measured."
        )
    trail: list[dict[str, Any]] = []
    for attempt in range(1, LOAD_ATTEMPTS + 1):
        released = release(host)
        # Loaded AFTER the release, so the neighbours are this attempt's doing
        # and not a leftover — and before the model under test, so the card is
        # already shared when it lands. A neighbour that will not load is a
        # refusal of the whole entry: an entry that asked to measure sharing and
        # got sole residency would silently measure the wrong thing.
        neighbourhood = []
        for other in neighbours:
            body = json.dumps({"model": other, "keep_alive": "10m", "num_predict": 1})
            status = contract.ssh(
                host,
                f"curl -s -m 3600 -X POST "
                f"{shlex.quote(contract.url(base, '/api/generate'))} "
                f"-d {shlex.quote(body)} -o /dev/null -w '%{{http_code}}'",
                timeout=LOAD_TIMEOUT_S,
            )
            neighbourhood.append({"model": other, "load_http_status": status})
        contract.drop_page_cache(host)
        options = {"num_predict": 1}
        if "num_ctx" in serve:
            options["num_ctx"] = serve["num_ctx"]
        body = json.dumps(
            {"model": model, "prompt": "hi", "stream": False, "options": options}
        )
        # `shlex.quote`, not a bare '...': a model id is config-supplied, and one
        # containing an apostrophe closes the quote — breaking the command at
        # best, and running the rest of the id as shell at worst. This runs over
        # ssh against a real host, so a typo in a config must not become a
        # command.
        loaded = contract.ssh(
            host,
            f"curl -s -m 3600 -X POST "
            f"{shlex.quote(contract.url(base, '/api/generate'))} "
            f"-d {shlex.quote(body)} -o /dev/null -w '%{{http_code}}'",
            timeout=LOAD_TIMEOUT_S,
        )
        resident = _resident(host)
        placed = _placement(resident, model)
        digest = _digest(base, model)
        wanted = expect.get("model_sha256")
        names = [row.get("name") for row in resident]
        fraction = placed.get("fraction")
        floor = placement.get("min_vram_fraction")
        check = {
            "attempt": attempt,
            # Reads the card, not this backend's process count. See the
            # docstring — the old field was the same name and a different fact.
            "card_idle_before_load": released.get("card_idle"),
            "card_used_mib_before_load": released.get("card_used_mib"),
            "load_http_status": loaded,
            "resident_names": names,
            "sole_resident": names == [model],
            "coresidency_allowed": coresident,
            "coresident_with": neighbours or None,
            "coresident_loads": neighbourhood or None,
            "coresidency_arranged": (
                None
                if not neighbours
                else all(row["load_http_status"] == "200" for row in neighbourhood)
                and all(other in names for other in neighbours)
            ),
            "size": placed.get("size"),
            "size_vram": placed.get("size_vram"),
            "vram_fraction": fraction,
            # D4: a declaration per entry, not a constant. `None` means the
            # entry declared nothing, and then placement is RECORDED, not gated.
            "placement_expected": placement or None,
            "placement_meets_expectation": (
                None if floor is None else (fraction or 0) >= floor
            ),
            "model_sha256": digest,
            "model_sha256_expected": wanted,
            "server": _server(host),
        }
        # **E11, 2026-08-19: residency is cross-checked against the card.**
        # Measured on srv1: after a child is killed, `/api/ps` keeps listing the
        # model — with its full `size_vram` and its original `expires_at` — for
        # the whole keep-alive window. So the residency list can assert that a
        # model is on the card, at fraction 1.0, when the card holds nothing.
        # E9 made the kill actually work, which is what opens this window; the
        # service restart that follows closes it, and this makes the guarantee
        # independent of that ordering rather than dependent on it.
        card_now = contract.first_int(
            contract.ssh(
                host,
                "nvidia-smi --query-gpu=memory.used --format=csv,noheader",
            )
        )
        check["card_used_mib_after_load"] = card_now
        check["residency_contradicts_card"] = bool(
            (placed.get("size_vram") or 0) > 0
            and card_now is not None
            and card_now < IDLE_BEFORE_LOAD_MIB
        )
        check["ok"] = bool(
            loaded == "200"
            and model in names
            and (coresident or check["sole_resident"])
            and check["coresidency_arranged"] is not False
            and check["placement_meets_expectation"] is not False
            and check["server"].get("instances")
            and not check["residency_contradicts_card"]
            and (wanted is None or digest == wanted)
        )
        trail.append(check)
        if check["ok"]:
            return {
                "backend": NAME,
                "model": model,
                "verified": True,
                "attempts": trail,
            }

    last = trail[-1]
    if (
        last["model_sha256_expected"]
        and last["model_sha256"] != last["model_sha256_expected"]
    ):
        raise contract.NotCleanError(
            f"{model} on {host} is not the pinned weights: expected "
            f"{last['model_sha256_expected']}, served {last['model_sha256']}. A tag "
            "is mutable and this one has moved — every other check passed, which "
            "is why the digest is pinned. Nothing was measured."
        )
    # **D8: the reason is structured, not only prose.** A refusal that a reader
    # has to parse out of a sentence cannot be counted across a campaign.
    reasons = []
    if last["load_http_status"] != "200":
        reasons.append("load_http_status")
    if model not in (last["resident_names"] or []):
        reasons.append("model_not_resident")
    elif not last["sole_resident"] and not last["coresidency_allowed"]:
        reasons.append("unexpected_coresidency")
    if last["placement_meets_expectation"] is False:
        reasons.append("placement_below_declared_floor")
    if not last["server"].get("instances"):
        reasons.append("no_server_child")
    if not last["card_idle_before_load"]:
        reasons.append("card_not_idle_before_load")
    if last.get("residency_contradicts_card"):
        reasons.append("residency_contradicts_card")
    if last.get("coresidency_arranged") is False:
        reasons.append("coresidency_not_arranged")
    raise contract.NotCleanError(
        f"{model} on {host} would not come up clean in {LOAD_ATTEMPTS} attempts "
        f"[{','.join(reasons) or 'unknown'}]: resident={last['resident_names']}, "
        f"vram_fraction={last['vram_fraction']}, "
        f"declared={last['placement_expected']}, "
        f"card_before={last['card_used_mib_before_load']} MiB, "
        f"http={last['load_http_status']}. Nothing was measured. Note that a low "
        "vram_fraction is NOT by itself a refusal any more (D4): a MoE serving "
        "part of its bytes off-card is working as designed, and only an entry "
        "that DECLARED a placement floor can fail one."
    )


def describe(
    host: str,
    base: str,
    model: str,
    serve: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Everything this engine will say about ``model``.

    The public capture, plus what only the child process answers — which is
    where the slot count and the seed live, on ``127.0.0.1`` and therefore out
    of reach of anything that is not on the serving host.
    """
    server = _server(host)
    return {
        "backend": NAME,
        "capture": contract.observed().capture(base, model),
        "resident": _resident(host),
        "server": server,
        "serving_config": serving_config(server, model),
        "declared_slots": declared_slots(server, model),
    }


def declared_slots(
    server: dict[str, Any], model: str | None = None
) -> dict[str, Any]:
    """What this engine SAYS its slot count is — never what the curve did.

    **D1, 2026-08-19.** A scheduler limit and a throughput saturation point are
    different quantities that coincide only when the limit binds before the
    hardware does, so they are different fields. This is the limit; the curve is
    :func:`contract.saturation`.

    For this engine the value is genuinely **observed**: the child process
    answers ``total_slots`` on its own ``/props``, which is the engine's own
    statement of how many requests it will run at once. It is set from
    ``OLLAMA_NUM_PARALLEL`` where that is configured and from the engine's
    default where it is not — measured 2 on srv1 (which sets it) and 1 on srv2
    (which does not).

    The provenance travels with the value because it is not observable on every
    engine. Where an engine states its width on no endpoint, the only available
    value is the one that was dispatched to it, and a consumer that could not
    tell the two apart would be comparing a reading with an intention.
    """
    instance = _instance_for(server, model)
    if instance is None:
        return {
            "value": None,
            "provenance": "observed",
            "refused": (
                "no resident child process, so the engine has not stated a slot "
                "count"
            ),
        }
    try:
        props = json.loads(instance.get("props") or "{}")
    except json.JSONDecodeError:
        return {
            "value": None,
            "provenance": "observed",
            "refused": "the child's /props did not parse as JSON",
        }
    if "total_slots" not in props:
        return {
            "value": None,
            "provenance": "observed",
            "refused": "the child's /props carries no total_slots key",
        }
    return {
        "value": props["total_slots"],
        "provenance": "observed",
        "source": "llama-server /props total_slots",
        "refused": None,
    }


def _instance_for(
    server: dict[str, Any], model: str | None
) -> dict[str, Any] | None:
    """The child serving ``model``, or ``None`` — never a blind ``instances[0]``.

    This engine runs one child per resident model, and up to three can be
    resident at once (``OLLAMA_MAX_LOADED_MODELS=3`` on srv1). Taking the first
    instance therefore described *an* unidentified model whenever more than one
    was up, which D7 item 4 does deliberately. A config that cannot say which
    model it describes is not a config.
    """
    instances = server.get("instances") or []
    if not instances:
        return None
    if model is None:
        return instances[0] if len(instances) == 1 else None
    # The child's command line carries the blob path, not the tag, so match on
    # the tag's own components rather than expecting the name verbatim.
    stem = model.replace(":", "-")
    for instance in instances:
        line = instance.get("command_line") or ""
        if model in line or stem in line:
            return instance
    return instances[0] if len(instances) == 1 else None


def serving_config(
    server: dict[str, Any], model: str | None = None
) -> dict[str, Any]:
    """The whole serving configuration, parsed and pinned as two digests.

    This engine's config is split in two places and neither is on the network:
    the child process's command line carries the window, the slot count and the
    attention and batch settings, and the child's own ``/props`` carries 39
    sampler defaults — every one of which decides an emitted token. All of it
    was being captured verbatim and read by nothing, which made this engine the
    less-instrumented of the two despite exposing MORE.
    """
    instances = server.get("instances") or []
    if not instances:
        return {
            "refused": (
                "no model is resident, so the child process that holds this "
                "configuration does not exist yet"
            )
        }
    instance = _instance_for(server, model)
    if instance is None:
        return {
            "refused": (
                f"{len(instances)} children are resident and none could be "
                f"matched to {model!r}; this config would have described an "
                "unidentified one of them"
            ),
            "resident_command_lines": [
                row.get("command_line") for row in instances
            ],
        }
    config: dict[str, Any] = dict(_command_flags(instance.get("command_line") or ""))
    try:
        props = json.loads(instance.get("props") or "{}")
    except json.JSONDecodeError:
        props = {}
    defaults = (props.get("default_generation_settings") or {}).get("params") or {}
    config.update(defaults)
    for key in ("total_slots", "model_ftype", "chat_template", "build_info"):
        if key in props:
            config[key] = props[key]
    if "n_ctx" in (props.get("default_generation_settings") or {}):
        config["n_ctx"] = props["default_generation_settings"]["n_ctx"]
    try:
        return fingerprint.fingerprint(config)
    except fingerprint.UnclassifiedError as error:
        return {"refused": str(error), "parsed": config}


#: The child's command-line flags that are configuration rather than plumbing,
#: mapped onto the names the fingerprint classifies. Measured on srv1:
#: `-c 8192 -np 2 --flash-attn auto -b 1024 -ub 1024 --context-shift --keep 4`.
_FLAGS: tuple[tuple[str, str, bool], ...] = (
    ("-c", "n_ctx", True),
    ("-np", "n_parallel", True),
    ("-b", "batch_size", True),
    ("-ub", "ubatch_size", True),
    ("--flash-attn", "flash_attn", True),
    ("--keep", "keep", True),
    ("--chat-template", "chat_template", True),
    ("--context-shift", "context_shift", False),
)


def _command_flags(line: str) -> dict[str, Any]:
    """The configuration flags off the child's command line."""
    tokens = line.split()
    out: dict[str, Any] = {}
    for flag, name, takes_value in _FLAGS:
        if flag not in tokens:
            continue
        if not takes_value:
            out[name] = True
            continue
        index = tokens.index(flag)
        if index + 1 < len(tokens):
            value = tokens[index + 1]
            out[name] = int(value) if value.isdigit() else value
    return out


def _server(host: str) -> dict[str, Any]:
    """The child process, its command line, and its own HTTP answers.

    Exists only while a model is resident, and its port is chosen at load time,
    so it is found by process rather than assumed. ``build_info`` is worth as
    much as the rest: it names the build that does the arithmetic, which is a
    different identifier from this engine's own version.
    """
    listing = contract.ssh(host, "pgrep -af '[l]lama-server' || true") or ""
    # The raw listing is scrubbed too, not only the per-instance readings built
    # from it — a planted-secret test caught this exact gap, where the parsed
    # detail was redacted and the text it was parsed from was not.
    out: dict[str, Any] = {
        "processes": contract.scrub(listing) or None,
        "instances": [],
    }
    for line in listing.splitlines():
        match = re.search(r"--port\s+(\d+)", line)
        if match is None:
            continue
        port = match.group(1)
        # A command line carries file paths and can carry a token; `/props`
        # carries a model path. Scrubbed at capture, like every other reading.
        out["instances"].append(
            contract.scrub(
                {
                    "port": port,
                    "command_line": line.strip(),
                    "props": contract.ssh(
                        host, f"curl -s -m 8 http://127.0.0.1:{port}/props || true"
                    ),
                    "slots": contract.ssh(
                        host, f"curl -s -m 8 http://127.0.0.1:{port}/slots || true"
                    ),
                }
            )
        )
    return out


def _resident(host: str) -> list[dict[str, Any]]:
    """The models in memory right now, from the host's own view."""
    raw = contract.ssh(host, "curl -s -m 15 http://127.0.0.1:11434/api/ps || true")
    try:
        rows = json.loads(raw or "{}").get("models")
    except json.JSONDecodeError:
        return []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _placement(resident: list[dict[str, Any]], model: str) -> dict[str, Any]:
    """How much of ``model`` is on the card, as a fraction of its size."""
    # `name` OR `model`, like every other matcher against this engine's rows:
    # both are carried, and a build that drops one would otherwise send `claim`
    # through two full clear-load cycles before refusing with a message blaming
    # VRAM placement for a field-name mismatch.
    row = next((r for r in resident if model in (r.get("name"), r.get("model"))), None)
    if row is None:
        return {}
    size, vram = row.get("size"), row.get("size_vram")
    if not isinstance(size, int) or not isinstance(vram, int) or size <= 0:
        return {"size": size, "size_vram": vram}
    return {"size": size, "size_vram": vram, "fraction": vram / size}


def _digest(base: str, model: str) -> str | None:
    """The manifest digest this engine lists for ``model``.

    Over-sensitive by nature — it moves when a non-weights layer changes — and
    that is the safe direction for a pin: it refuses a run that would have been
    sound, and never permits one that is not.
    """
    tags = contract.get_json(contract.url(base, "/api/tags"), timeout=20.0)
    rows = (tags or {}).get("models") if isinstance(tags, dict) else None
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and model in (row.get("name"), row.get("model")):
            found = row.get("digest")
            return str(found) if found else None
    return None
