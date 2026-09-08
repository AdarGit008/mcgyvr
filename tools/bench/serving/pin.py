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
    hypothetical. A daemon that serves many checkpoints from one process
    re-derives its serving parameters **per model**: measured 2026-08-22 on one
    host at one configured width, ``qwen2.5-coder:*``
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
import json
import os
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
    ("llamacpp", "'[l]lama-server'"),
    ("vllm", "'[v]llm serve'"),
)


#: Where this engine states the batch width it was started with, in the parsed
#: serving config. `n_parallel` is the `-np` the server was launched with;
#: `total_slots` is what it then reports on its own `/props`. Both are
#: classified **semantic** by `fingerprint.py`, under its own comment "batching
#: and caching — decide whether a re-run reproduces at all".
LLAMACPP_WIDTH_FIELDS: tuple[str, ...] = ("n_parallel", "total_slots")


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
        for name in LLAMACPP_WIDTH_FIELDS
        if isinstance(semantic.get(name), int) and not isinstance(semantic[name], bool)
    }
    if not found:
        refusal = (config or {}).get("refused")
        return {
            "value": None,
            "source": None,
            "refused": (
                "the serving config carried neither "
                + " nor ".join(LLAMACPP_WIDTH_FIELDS)
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
#: What a sweep reads off the card, composed from the constants that already
#: declare each part rather than from a fourth copy of ``nvidia-smi`` (#348).
#: One ssh, three readings: the card's own state, which processes hold it and
#: how much each holds, and the machine's load.
#:
#: **Semicolons BETWEEN the sections and ``&&`` inside them.** The separator
#: between sections is `;` for the reason ``LEVEL_STATE_COMMAND`` gives — one
#: failing reading must not take the others down with it — and the separator
#: before each sentinel is `&&` for the reason ``COMPUTE_APPS_PROBE`` gives: a
#: query that printed nothing on stdout would otherwise have its sentinel
#: printed anyway, and an UNREAD card would parse as an empty one.
SWEEP_CARD_END = "__sweep_card_end__"
SWEEP_PROBE = (
    f"{contract.CARD_STATE_COMMAND} && echo {SWEEP_CARD_END}; "
    f"{contract.COMPUTE_APPS_PROBE}; "
    "cat /proc/loadavg"
)

#: How many consecutive failed readings before the sampler stops taking them.
#:
#: **The recorder must not be able to damage the run it is recording.** A
#: reading costs one ssh — measured p50 0.956 s and p95 1.40 s
#: (records/evidence/calibration-2026-08-19/README.md:20) — and an ssh to a host
#: that has GONE AWAY costs its ``ConnectTimeout`` instead, 15 s, every single
#: time. Over a several-hundred-task sweep that is hours of a measurement run
#: spent learning one fact repeatedly. Three is small enough that a sweep never
#: pays much for a dead host and large enough that one dropped packet does not
#: end the sampling.
SWEEP_GIVE_UP_AFTER = 3


def sweep_reading(raw: str | None) -> dict[str, Any]:
    """:data:`SWEEP_PROBE`'s output, sliced by sentinel and parsed by section.

    **Sliced explicitly rather than by the shape of a line.** Handing the whole
    reading to each parser happens to work today — a card line has four
    comma-separated fields and ``compute_apps`` drops anything that is not two
    — but that is a guard doing a second job by luck, and the day a driver adds
    a column it stops being luck. Every section is delimited, and a section
    whose delimiter is missing is a section that did not complete.

    Three states per reading, as everywhere else (ADR-0027 D2): a value, or
    ``null`` **with a reason**, never a zero standing in for an unknown. In
    particular ``placements: null`` is "the card was not read" and ``[]`` is
    "the card answered and holds nothing" — the distinction the sentinel in
    ``COMPUTE_APPS_PROBE`` exists to preserve, carried through to here.
    """
    if raw is None:
        return {
            "card": contract.card_state(None, SWEEP_PROBE),
            "placements": None,
            "host_loadavg": None,
            "refused": "the reading did not come back: the host did not answer",
        }
    head, seen_card, rest = raw.partition(SWEEP_CARD_END)
    lines = [line for line in raw.splitlines() if line.strip()]
    return {
        # Without its sentinel the card section did not complete, and `head`
        # would then be the whole reading — so it is not offered to the parser.
        "card": contract.card_state(head if seen_card else None, SWEEP_PROBE),
        "placements": contract.compute_apps(rest if seen_card else raw),
        "host_loadavg": contract.loadavg(lines[-1] if lines else None),
    }


class CardSampler:
    """One reading of the card per unit of work, and a rule for when to stop.

    **Nothing reads what this writes** — the same discipline as the `observed`
    block, and stated here for the same reason: it is comprehensive precisely
    because nothing is admitted from it, and a later lane wiring a guard to a
    throttle mask would silently turn a fact about a cell into a refusal of it.
    Whether a throttled card should refuse a measurement is a real question and
    it is a different one, with a different owner.

    The sampler holds state because giving up is stateful. It is deliberately
    not a thread: at one reading per task the extra resolution a timer would buy
    is nil, and a background thread inside a process that drives a rig over ssh
    is a concurrency question nobody needs to answer for it.
    """

    def __init__(
        self, host: str, path: Path, give_up_after: int = SWEEP_GIVE_UP_AFTER
    ) -> None:
        self.host = host
        self.path = path
        self.give_up_after = give_up_after
        self.consecutive_failures = 0
        self.stopped: str | None = None
        self.taken = 0

    def sample(self, label: str, at: str) -> dict[str, Any] | None:
        """Append one reading, or ``None`` once this sampler has given up.

        ``at`` is passed in rather than read here so the row's clock is the
        run's clock, and so a test can state the instant instead of racing it.

        Never raises. A sampler that could end a sweep would be worse than no
        sampler: the run is the thing being protected, and this is a recording.
        """
        if self.stopped is not None or not self.host:
            return None
        try:
            reading = sweep_reading(contract.ssh(self.host, SWEEP_PROBE))
        except Exception as error:  # pragma: no cover - defence, not a path
            reading = {
                "card": contract.card_state(None, SWEEP_PROBE),
                "placements": None,
                "host_loadavg": None,
                "refused": f"the reading raised: {type(error).__name__}: {error}",
            }
        row = {"at": at, "label": label, "host": self.host, **reading}

        answered = reading["card"].get("why") is None
        self.consecutive_failures = 0 if answered else self.consecutive_failures + 1
        if self.consecutive_failures >= self.give_up_after:
            self.stopped = (
                f"{self.consecutive_failures} consecutive readings did not "
                f"answer, so sampling stopped after {self.taken + 1} of them "
                "rather than spending an ssh timeout per task on a host that "
                "has gone away. The samples before this one stand"
            )
            row["sampling_stopped"] = self.stopped

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.taken += 1
        return row


#: The ways a host block can hold no readings. **They were one value — `{}` —
#: and that is #349**: "there is no machine to log into", "the dispatch address
#: is loopback so it names whatever box resolved it", "the name did not resolve"
#: and "the probe raised" arrived identical, so a reading that BROKE could not
#: be told from one that was never available. This module refuses that same
#: collapse twice elsewhere on purpose — `gpu_idle`'s "`None` is NOT idle" and
#: the compute-apps probe's `&&`-not-`;` sentinel, both so that an unread card
#: cannot parse as an empty one — and did it here anyway.
#:
#: `PROBE_FAILED` is raised on the RUNNER's side of the import, which is the one
#: place this module cannot reach: if `pin.py` itself will not load, nothing
#: here runs to say so. It is named here so the vocabulary is closed and one
#: `git grep` finds every arm of it.
NO_HOSTNAME = "no_hostname"
LOOPBACK = "loopback"
UNRESOLVABLE = "unresolvable"
PROBE_FAILED = "probe_failed"


def unread(reason: str, why: str, **extra: Any) -> dict[str, Any]:
    """A host block with no readings in it, saying WHICH of the ways it is one.

    ``refused`` carries the sentence and ``reason`` the code, the pair ADR-0027
    D2 asks for: a value, or ``null`` **with a reason**, never a silent empty.
    An absent block still means the record predates the contract, and that is
    now the only thing it means.

    ``width`` is present on every arm so the shape does not fork. A consumer
    reaching for it must not have to know which failure produced the block it
    is reaching into — that is how a reader comes to write ``or 0``.
    """
    return {
        "reason": reason,
        "refused": why,
        "width": {"value": None, "source": None, "refused": why},
        **extra,
    }


NO_PROCESS_WIDTH: dict[str, Any] = {
    "value": None,
    "source": None,
    "refused": "no serving process of a known engine is running on this host",
}


def host_block(endpoint: str, host: str = "") -> dict[str, Any]:
    """Everything the serving MACHINE will say, plus what binds it to this run.

    **Never returns a bare ``{}``** (#349). Holding no readings is an ordinary
    state — a run from a machine without keys records what the endpoint said and
    nothing more — but it is FOUR ordinary states, and they were one value. See
    :func:`unread`: each arm carries its own ``reason`` and its own sentence, so
    a reading that broke can be told from one that was never available.

    A hosted endpoint that RESOLVES is not one of them, and was mistaken for one
    when this was written up: it produces a full block whose ``machine.held`` is
    ``False`` and whose ``why`` says the dispatch address is not this host's.
    That is a stronger record than an empty one and it was already correct.

    ``host`` defaults to the endpoint's own hostname, which is right whenever
    the dispatch URL names the serving machine — and :func:`same_machine` is the
    claim that checks it rather than assuming it.
    """

    host = host or (urlsplit(endpoint).hostname or "")
    if not host:
        return unread(
            NO_HOSTNAME,
            f"no hostname in {endpoint!r}, so there is no machine to read. "
            "This is a statement about the dispatch URL, not about a rig",
        )
    if host in ("localhost", "127.0.0.1"):
        return unread(
            LOOPBACK,
            f"the dispatch address {host!r} is loopback, so it names whatever "
            "box resolved it rather than a machine these readings could be "
            "bound to. `same_machine` cannot refute a claim it cannot address",
        )
    machine = same_machine(host, endpoint)
    if machine.get("held") is None and not machine.get("endpoint_resolves_to"):
        return unread(
            UNRESOLVABLE,
            "the endpoint could not be resolved to an address, so nothing "
            f"read off {host!r} could be tied to the server that answered: "
            + str(machine.get("why") or "no reason given"),
            machine=machine,
        )

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
    # One spelling now. A branch stood here for the engine that ran
    # llama-server as a child of a daemon, whose address had to be discovered
    # rather than computed from a known port; both engines this build serves
    # answer at a port the backend states (archive/forensic-ollama/).
    config = backend.serving_config(f"http://{host}:{backend.PORT}")
    return {
        **found,
        "machine": machine,
        "fingerprint": config,
        "width": width(found["engine"], host, config, backend),
    }
