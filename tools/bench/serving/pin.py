#!/usr/bin/env python3
"""Binding a run to what the serving HOST said, with three falsifiable claims.

Host-side readings are worth more than anything the endpoint will state about
itself — the slot count, the sampler defaults, the serving config digests — and
they are worth **nothing** unless they provably describe the server that served
*this* run. This module is that proof, and it is three claims rather than one
assertion, because there are three separate ways for the connection to be false
and each needs its own evidence:

``same_machine``
    The address the dispatch URL resolves to is one the SSH host reports owning.
    Refutes *"the host readings describe a different box"* — a proxy, a tunnel, a
    load balancer in front of several servers, a hosted endpoint with no host at
    all. Measured here: ``srv1`` resolves to ``100.67.218.22``, which srv1 lists
    among its own addresses.

``same_process``
    ``(boot_time, process start ticks, pid)`` read at open and again at close.
    Refutes *"the server was restarted mid-run"*. Boot time is combined with
    jiffies-since-boot rather than trusting the pid alone, because a pid is
    reused and a restarted server can land on the same number.

``same_config``
    The semantic serving digest at open equals the one at close. Refutes
    *"the configuration changed without a restart"* — and that is not
    hypothetical. Ollama re-derives its serving parameters **per model**:
    measured on one host with one ``OLLAMA_NUM_PARALLEL``, ``qwen2.5-coder:*``
    was served ``-c 8192 -np 2`` and ``nemotron-3-nano:4b`` ``-c 4096 -np 1``.
    Same machine, same pid, different served window and slot count — so the
    first two claims both hold while the thing being described has changed.

**A failed claim is recorded, never raised.** ``pinned: false`` says the serving
configuration was not constant across the run, which is a fact *about* the
measurement rather than an error *in* it — the rows are still real. Whether it
should refuse a comparison is a question for ``identity.KEY``, which is the
owner's under ADR-0027 D7 and belongs in its own change.
"""

from __future__ import annotations

import importlib.util
import re
import socket
import sys
import types
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent


def _contract() -> types.ModuleType:
    cached = sys.modules.get("serving_contract")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "serving_contract", HERE / "contract.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["serving_contract"] = module
    spec.loader.exec_module(module)
    return module


contract = _contract()

#: `/proc/<pid>/stat` field 22 is the process start time in clock ticks since
#: boot. Paired with `/proc/stat`'s `btime` it becomes an absolute instant, which
#: is what makes it survive pid reuse — a bare pid does not.
_STARTTIME_FIELD = 22


def instance(host: str, pattern: str) -> dict[str, Any]:
    """Which serving process this is, in a form that survives pid reuse.

    ``pattern`` is a ``pgrep`` pattern for the engine's own process. Bracketed
    by the caller so it cannot match the shell running it.
    """
    raw = contract.ssh(
        host,
        f"P=$(pgrep -f {pattern} | head -1); "
        'if [ -z "$P" ]; then echo "none"; else '
        "echo \"$P $(awk '{print $22}' /proc/$P/stat) "
        "$(awk '/btime/{print $2}' /proc/stat)\"; fi",
    )
    if not raw or raw.strip() == "none":
        return {"present": False, "pattern": pattern}
    parts = raw.split()
    if len(parts) != 3:
        return {"present": False, "pattern": pattern, "unparsed": raw}
    pid, start_ticks, boot = parts
    return {
        "present": True,
        "pattern": pattern,
        "pid": _int(pid),
        "start_ticks": _int(start_ticks),
        "boot_time": _int(boot),
        # The identity that is compared. Two readings equal here are the same
        # process; a restart moves `start_ticks`, and a reboot moves `boot_time`.
        "token": f"{boot}:{start_ticks}:{pid}",
    }


def same_machine(host: str, endpoint: str) -> dict[str, Any]:
    """Whether ``endpoint`` resolves to an address ``host`` says it owns."""
    hostname = urlsplit(endpoint).hostname
    if not hostname:
        return {"held": None, "why": f"no hostname in {endpoint!r}"}
    try:
        resolved = sorted({info[4][0] for info in socket.getaddrinfo(hostname, None)})
    except OSError as error:
        return {"held": None, "why": f"{hostname} did not resolve: {error}"}
    owned_raw = contract.ssh(host, "hostname -I; ip -o addr 2>/dev/null | head -20")
    owned = set(re.findall(r"\d+\.\d+\.\d+\.\d+|[0-9a-f:]{6,}", owned_raw or ""))
    loopback = {"127.0.0.1", "::1", "localhost"}
    shared = sorted(set(resolved) & owned)
    # One decision, used for both the verdict and the sentence. Computing them
    # separately let a loopback endpoint record `held: true` beside a `why`
    # saying the address was NOT this host's — a record that contradicts itself
    # is worse than either answer alone.
    via_loopback = bool(set(resolved) & loopback)
    held = bool(shared) or via_loopback
    return {
        "held": held,
        "endpoint_resolves_to": resolved,
        "host_owns_sample": sorted(owned)[:8],
        "shared": shared,
        "via_loopback": via_loopback,
        "why": (
            "the dispatch address is one this host owns"
            if shared
            else "the dispatch address is loopback, so it names whatever host "
            "resolved it — this binding holds only if the dispatch ran there"
            if via_loopback
            else "the dispatch address is NOT among this host's addresses — the "
            "host readings may describe a different machine than the one served "
            "this run"
        ),
    }


def pin(
    at_open: dict[str, Any], at_close: dict[str, Any], machine: dict[str, Any]
) -> dict[str, Any]:
    """The three claims, and whether all of them hold.

    Each is ``None`` when it could not be evaluated — an unreachable host, a run
    with no close capture — which is a third state and not a pass. A claim that
    could not be checked must never read as a claim that held.
    """
    open_token = (at_open.get("instance") or {}).get("token")
    close_token = (at_close.get("instance") or {}).get("token")
    open_digest = (at_open.get("fingerprint") or {}).get("serving_semantic_sha256")
    close_digest = (at_close.get("fingerprint") or {}).get("serving_semantic_sha256")

    process = None if not (open_token and close_token) else open_token == close_token
    config = None if not (open_digest and close_digest) else open_digest == close_digest
    claims = {
        "same_machine": machine.get("held"),
        "same_process": process,
        "same_config": config,
    }
    return {
        "claims": claims,
        "machine": machine,
        "process": {"at_open": open_token, "at_close": close_token},
        "config": {"at_open": open_digest, "at_close": close_digest},
        # `True` only when every claim was CHECKED and HELD. An unchecked claim
        # leaves this false, because "we did not look" and "we looked and it was
        # fine" are different facts about a run.
        "pinned": all(value is True for value in claims.values()),
        "note": (
            "three claims, each falsifiable: the host readings describe this "
            "run's server only if the endpoint resolves to this machine, the "
            "serving process never restarted, and the semantic serving digest "
            "held from open to close. Recorded, never raised — whether an "
            "unpinned run may join a comparison is identity.KEY's question"
        ),
    }


def _int(text: str) -> int | None:
    try:
        return int(text)
    except ValueError:
        return None


#: How each engine's serving process is found, and where its config comes from.
#: Bracketed so `pgrep -f` cannot match the shell that runs it — an unbracketed
#: pattern kills the ssh session before it finds anything.
_ENGINES: tuple[tuple[str, str], ...] = (
    ("ollama", "'[l]lama-server'"),
    ("vllm", "'[v]llm serve'"),
)


#: Where this engine states the batch width it was started with, in the parsed
#: serving config. `n_parallel` is the `-np` the child was launched with;
#: `total_slots` is what that child then reports on its own `/props`. Both are
#: classified **semantic** by `fingerprint.py`, under its own comment "batching
#: and caching — decide whether a re-run reproduces at all".
OLLAMA_WIDTH_FIELDS: tuple[str, ...] = ("n_parallel", "total_slots")


def width(
    engine: str, host: str, config: dict[str, Any], backend: types.ModuleType
) -> dict[str, Any]:
    """The batch width the running server was started with, as a HOST reading.

    **This is the field the capture module refuses**, and that refusal is right
    about what it refuses: the width is on no network surface either engine
    serves — searched exhaustively on both rigs, across every parameterless GET
    in one engine's own route table and every endpoint the other answers. Its
    own last clause says the answer is "obtainable only with access to the
    serving host", and this module is the half with that access. So the number
    exists, it is a host fact, and it belongs beside the other host facts rather
    than nowhere.

    Normalised across engines deliberately. A reader asking "how wide was the
    server" should not have to know that one engine calls it ``-np`` on a child
    process and the other ``--max-num-seqs`` in its own argv; the ``source``
    field is where that difference is kept.

    ``value`` is ``None`` **with a reason** rather than absent (ADR-0027 D2).
    **Two sources that disagree are refused, not resolved** — the same rule
    ``vllm.declared_slots`` already applies to its own pair, and for the same
    reason: picking one would be picking which of two contradictory facts about
    the running server to believe.
    """
    if engine == "vllm":
        reading = backend.launched_width(host)
        if reading.get("value") is None:
            return {
                "value": None,
                "source": None,
                "refused": (
                    "neither the serving process's argv nor the container's "
                    "Config.Cmd carried --max-num-seqs on this host, and no "
                    "endpoint this engine serves carries it either"
                ),
            }
        return {"value": reading["value"], "source": f"host:{reading['source']}"}

    semantic = (config or {}).get("semantic") or {}
    found = {
        name: semantic[name]
        for name in OLLAMA_WIDTH_FIELDS
        if isinstance(semantic.get(name), int) and not isinstance(semantic[name], bool)
    }
    if not found:
        refusal = (config or {}).get("refused")
        return {
            "value": None,
            "source": None,
            "refused": (
                "the serving config carried neither "
                + " nor ".join(OLLAMA_WIDTH_FIELDS)
                + (f", because {refusal}" if refusal else "")
            ),
        }
    if len(set(found.values())) > 1:
        return {
            "value": None,
            "source": None,
            "refused": (
                f"the host states two different widths, {found} — the flag the "
                "child was launched with and the slot count that child reports "
                "must agree, and resolving them here would pick which of two "
                "contradictory facts to believe"
            ),
        }
    name = next(iter(found))
    return {"value": found[name], "source": f"host:{name}"}


#: The shape :func:`width` returns when no serving process was found at all, so
#: the key is present on every host block rather than only on the ones that
#: could answer. An absent key means the record predates the contract; this is
#: a refusal, and it says so.
NO_PROCESS_WIDTH: dict[str, Any] = {
    "value": None,
    "source": None,
    "refused": "no serving process of a known engine is running on this host",
}


def host_block(endpoint: str, host: str = "") -> dict[str, Any]:
    """Everything the serving MACHINE will say, plus what binds it to this run.

    Returns ``{}`` when the host cannot be reached, which is an ordinary state:
    a hosted endpoint has no host to log into, and a run from a machine without
    keys records what the endpoint said and nothing more. The absence is visible
    in the record rather than mistaken for a clean reading.

    ``host`` defaults to the endpoint's own hostname, which is right whenever
    the dispatch URL names the serving machine — and :func:`same_machine` is the
    claim that checks it rather than assuming it.
    """

    host = host or (urlsplit(endpoint).hostname or "")
    if not host or host in ("localhost", "127.0.0.1"):
        return {}
    machine = same_machine(host, endpoint)
    if machine.get("held") is None and not machine.get("endpoint_resolves_to"):
        return {}

    found: dict[str, Any] = {}
    for name, pattern in _ENGINES:
        reading = instance(host, pattern)
        if reading.get("present"):
            found = {"engine": name, "instance": reading}
            break
    if not found:
        return {
            "machine": machine,
            "instance": {"present": False},
            "width": dict(NO_PROCESS_WIDTH),
        }

    backend = contract.load_backend(found["engine"])
    if found["engine"] == "ollama":
        config = backend.serving_config(backend._server(host))
    else:
        config = backend.serving_config(f"http://{host}:{backend.PORT}")
    return {
        **found,
        "machine": machine,
        "fingerprint": config,
        "width": width(found["engine"], host, config, backend),
    }
