"""Emitting is writing a file. It is never starting a process.

A rig is a machine with an operator, and mcgyvr is not that operator: it hands
over a launch spec and stops. Nothing in this module shells out, and nothing in
it may learn to — a tool that both sizes a unit and starts it turns "here is
what would run" into "something is now running on your desktop", which is not a
question the caller was asked. :mod:`mcgyvr.serving` builds the spec, this
renders it, and the person at the keyboard decides.

Docker is one rendering of a spec and a bare command line is another, so the
argv is built **once** (:func:`argv`) and both renderings quote from it. A
compose file carrying different arguments from the command it replaces is a
second configuration nobody is reading, and it would be discovered as a
performance mystery months later — the container serving four slots while the
documented command says sixteen.

Two consequences worth naming, because both look like quirks until you need
them:

* **Weights are mounted, never baked.** An 18 GB image rebuilt per quant is a
  copy of the weights per rig; the directory the scan measured free space on is
  bind-mounted read-only instead, so the same file the disk check was about is
  the file the server loads.
* **The weights directory is mounted twice** — at the conventional ``/models``
  and at its own path — and the argv names the host path. That is what lets one
  argv be true in both renderings: the bare command has to work on the machine
  the weights are actually on, and the container has to resolve the identical
  string. When the operator already keeps weights at ``/models`` the two mounts
  are one and the duplicate disappears.
"""

from __future__ import annotations

import ipaddress
import re
import shlex
from collections.abc import Iterable
from pathlib import Path

import yaml

from mcgyvr.serving import Unit

# The engines this module can render, and what each one is. An engine it has no
# argv shape for is refused rather than guessed at: llama.cpp's flags on a vLLM
# image is a server that fails at load with a message about neither.
ENGINE_BINARIES = {"llama.cpp": "llama-server"}
ENGINE_IMAGES = {"llama.cpp": "ghcr.io/ggml-org/llama.cpp:server-cuda"}

# Where the weights directory appears inside the container. A convention, not a
# choice the spec makes — see the module docstring on why the argv does not use
# it.
MOUNT = "/models"

COMPOSE_PREFIX = "compose."
COMPOSE_SUFFIX = ".yml"

# Compose service and container names, and the file name a host is filed under.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class EmitError(Exception):
    """A launch spec could not be rendered — for a host, an engine or a path."""


def argv(unit: Unit) -> tuple[str, ...]:
    """The launch arguments, once, so the two renderings cannot drift.

    Flag then value, ordered by flag: :class:`~mcgyvr.serving.Unit` carries its
    arguments as a mapping and a mapping has no order worth trusting, so one is
    imposed here. The same unit therefore renders to the same bytes on any
    machine, which is what makes an emitted file diffable against the last one.

    An argument containing whitespace is refused, even though
    :func:`render_command` quotes and could carry it. Quoting makes such an
    argument safe, not intended: a space in a weights path is far more often a
    truncated config or a half-finished edit than a directory somebody meant to
    name, and it is worth reporting here, where it is still a fixable line in a
    file, rather than at load on the rig. A metacharacter is not refused — a
    path is allowed to contain a semicolon, and that is precisely why the bare
    rendering quotes instead of trusting.

    ``--port`` is stated rather than left to the engine, because the source URL
    the unit was built from is a promise about where that rung answers, and a
    server listening somewhere else makes the config a lie — one that reads as
    a dead tier, or as two models on one host where the second never came up
    because the first already had 8080. Written here, in the one argv, so the
    compose file and the pasted command cannot disagree about it.
    """
    flags = {**unit.args, "--port": str(unit.port)}
    parts = tuple(part for flag in sorted(flags) for part in (flag, str(flags[flag])))
    for part in parts:
        if part.split() != [part]:
            raise EmitError(
                f"{unit.key.slug}: argument {part!r} contains whitespace, which the "
                "compose file and the bare command cannot spell the same way"
            )
    return parts


def render_command(unit: Unit) -> str:
    """The unit as one command line an operator can paste into a shell.

    The binary and then :func:`argv`, shell-quoted. Quoting is what keeps the
    two renderings saying one thing rather than what makes them differ: the
    compose ``command`` is a list, so ``/srv/w;id/qwen-3b.gguf`` is one
    argument there whatever it contains, while this rendering is a single
    string a shell reads again. Unquoted, that same path is a command separator
    and a second command; a ``*`` or a ``$(…)`` in it would be quieter and
    worse, loading different weights here than the container loads. What comes
    back is exactly :func:`argv` under ``shlex.split``, which is the property
    the two renderings are held to.

    This is the whole of the non-Docker rendering on purpose: everything else a
    compose file says — image, mounts, device reservation — is Docker's way of
    arranging what a person on the machine has already arranged.
    """
    return shlex.join((_binary(unit), *argv(unit)))


def render_compose(unit: Unit | None) -> str:
    """The unit as a one-service compose file.

    ``None`` is the shape a caller gets back for a host nobody has measured,
    and it is refused rather than filled in with defaults. Every number in a
    unit — the card index, the slot count, how many expert blocks go to the
    CPU — was read off a scan, so there is no honest compose file for an
    unscanned machine, only a plausible one.
    """
    if unit is None:
        raise EmitError(
            "no serving unit to render: the host is unscanned, and a launch spec "
            "for a machine nobody measured would be a guess wearing a file name"
        )
    return _document((unit,))


def emit_all(units: Iterable[Unit], root: Path) -> tuple[Path, ...]:
    """Write one compose file per host under ``root``. Returns what was written.

    Per host rather than per unit because a host is what an operator brings up:
    ``docker compose -f compose.desktop-1.yml up`` starts everything that
    machine serves, and two files for one rig would be two commands with a rule
    about which comes first.

    Nothing is written outside ``root``, and a host name that would climb out of
    it is refused rather than sanitised — a host is a key that scans, units and
    files are all filed under, and quietly rewriting it here would file this
    file under a name nothing else uses.
    """
    grouped: dict[str, list[Unit]] = {}
    for unit in units:
        grouped.setdefault(unit.host, []).append(unit)

    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    claimed: dict[str, str] = {}
    for host in sorted(grouped):
        name = _safe_host(host)
        # Spelling a host into a file name is many-to-one wherever it rewrites
        # anything — and for an IPv6 literal it does — so two hosts can reach
        # one path. Left alone that is not an error anybody sees: the second
        # file overwrites the first and one rig is simply absent from the
        # output, which is the same silent loss as two models in one service.
        first = claimed.setdefault(name, host)
        if first != host:
            raise EmitError(
                f"{host!r} and {first!r} would both be written to "
                f"{COMPOSE_PREFIX}{name}{COMPOSE_SUFFIX}, and the second file "
                "would be the only one left"
            )
        path = root / f"{COMPOSE_PREFIX}{name}{COMPOSE_SUFFIX}"
        if path.resolve().parent != root.resolve():
            raise EmitError(f"{host}: would write outside {root}")
        path.write_text(_document(tuple(grouped[host])), encoding="utf-8")
        written.append(path)
    return tuple(written)


def _document(units: tuple[Unit, ...]) -> str:
    """The compose document for one host's units, sorted throughout.

    Two units that spell one service name are refused rather than merged.
    :func:`_service_name` is many-to-one — ``qwen2.5-coder:3b`` and
    ``qwen2.5-coder-3b`` are two sets of weights, two processes and one compose
    name — and keeping the last of them writes a file that looks entirely
    correct, brings up one server and leaves the rung bound to the other with
    connection refused, on a rig whose own compose file names the model it is
    asking for. Compose has no spelling that is both, so the fixable thing is
    the model name and the error says so.
    """
    services: dict[str, dict[str, object]] = {}
    spoken_for: dict[str, str] = {}
    for unit in units:
        name = _service_name(unit)
        first = spoken_for.setdefault(name, unit.key.slug)
        if first != unit.key.slug:
            raise EmitError(
                f"{unit.host}: {first} and {unit.key.slug} would both be the "
                f"compose service {name!r}, and a file with one service starts "
                "one of them — rename a model so the two spell differently"
            )
        services[name] = _service(unit)
    return yaml.safe_dump({"services": services}, sort_keys=True, width=200)


def _service(unit: Unit) -> dict[str, object]:
    """One unit as a compose service.

    The device reservation names the card the scan actually found rather than
    handing the container every GPU: on a two-card rig ``all`` is how two units
    sized for two different cards end up fighting over one.
    """
    return {
        "image": _image(unit),
        "container_name": f"mcgyvr-{_safe_host(unit.host)}-{_service_name(unit)}",
        "command": list(argv(unit)),
        # The host's network rather than a published port, for the same reason
        # the argv is built once: the port is already in the argv, so a
        # published mapping would be a second answer to "where do I reach
        # this" — one that can differ from the pasted command's, which is the
        # drift this module exists to prevent. Under host networking there is
        # one number, the one the source URL named, and both renderings say it.
        "network_mode": "host",
        # The rig is reached from another machine, and llama-server's own
        # default bind is loopback — which under host networking would serve
        # only the rig itself. Stated as the server's environment variable
        # rather than as an argument, on purpose: the argv has to stay
        # identical in both renderings, and this is a fact about where the
        # container sits rather than about how the model is loaded.
        "environment": {"LLAMA_ARG_HOST": "0.0.0.0"},
        "restart": "unless-stopped",
        "volumes": sorted(
            {
                f"{unit.weights_dir}:{MOUNT}:ro",
                f"{unit.weights_dir}:{unit.weights_dir}:ro",
            }
        ),
        "deploy": {
            "resources": {
                "reservations": {
                    "devices": [
                        {
                            "driver": "nvidia",
                            "device_ids": [str(unit.gpu)],
                            "capabilities": ["gpu"],
                        }
                    ]
                }
            }
        },
    }


def _binary(unit: Unit) -> str:
    binary = ENGINE_BINARIES.get(unit.engine)
    if binary is None:
        raise EmitError(
            f"{unit.key.slug}: no command line is known for engine {unit.engine!r}"
        )
    return binary


def _image(unit: Unit) -> str:
    image = ENGINE_IMAGES.get(unit.engine)
    if image is None:
        raise EmitError(
            f"{unit.key.slug}: no container image is known for engine {unit.engine!r}"
        )
    return image


def _service_name(unit: Unit) -> str:
    """The process, spelled the way compose accepts.

    A service is one server process, and what tells two processes on one host
    apart is the port they answer on — the same weights are legitimately served
    twice, once sized for volume and once to drain that lane's failure tail.
    Naming the service after the model alone throws that distinction away, so
    the port is part of the name rather than a detail inside it.

    ``qwen2.5-coder:3b`` has a colon, which compose does not take in a name.
    """
    return f"{_UNSAFE.sub('-', unit.model)}-{unit.port}"


def _safe_host(host: str) -> str:
    """The host as a file name component, refusing whatever it would have to tidy.

    A host is the key scans, units and files are all filed under, so a name
    that merely needs sanitising is refused rather than sanitised: rewriting it
    here would file this file under a name nothing else in the tool uses.

    An IPv6 literal is the one exception, because refusing it is refusing the
    rig. ``host_of("http://[fd00::1]:8080")`` is ``fd00::1`` — a real address
    of a real machine that a ladder can already reach — and a colon is not a
    compose name anywhere, nor a path component on every system a compose file
    gets copied to. So it is spelled out instead, and normalised first, so that
    the two ways of writing one address (``fd00::1`` and ``fd00:0:0:0:0:0:0:1``)
    cannot become two files for one rig. What comes back is a name, not an
    address; :func:`emit_all` is where two hosts are stopped from claiming one.
    """
    address = _ipv6(host)
    if address is not None:
        return _UNSAFE.sub("-", address)
    if not host or host != _UNSAFE.sub("-", host) or host in {".", ".."}:
        raise EmitError(f"{host!r} is not a host name a file can be named after")
    return host


def _ipv6(host: str) -> str | None:
    """``host`` as one normalised IPv6 literal, or ``None`` if it is not one."""
    try:
        return ipaddress.IPv6Address(host).compressed
    except ValueError:
        return None
