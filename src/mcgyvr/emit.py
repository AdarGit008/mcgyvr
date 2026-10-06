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

A model split across machines is several processes, one :class:`Unit` each, and
this module renders each the way it renders any other: a process reserves every
card it holds, a ``rpc-server`` worker runs its own binary with no weights
mount (the head sends it what it holds), and a ``--headless`` vLLM node renders
as a vLLM unit that answers nothing. What an engine reads beside its argv is
the unit's ``env``, merged into the service's environment.
"""

from __future__ import annotations

import difflib
import re
import shlex
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from mcgyvr.fleet.spans import SpanError, spans
from mcgyvr.serving import (
    COMPOSE_PREFIX,
    COMPOSE_SUFFIX,
    HF_CACHE_MOUNT,
    MEDIA_ENGINES,
    MEDIA_ENGINES_NOT_WIRED,
    ROLE_HEADLESS,
    ROLE_RPC,
    ROLE_SERVE,
    Unit,
    launch_specs,
    port_of,
    safe_host,
    safe_model,
    spec_files,
    spec_name,
)

# The engines this module can render, and what each one is. An engine it has no
# argv shape for is refused rather than guessed at: llama.cpp's flags on a vLLM
# image is a server that fails at load with a message about neither.
ENGINE_COMMANDS = {"llama.cpp": ("llama-server",), "vllm": ("vllm", "serve")}
# How llama-server is told the name its answers carry, in both spellings: a
# unit whose ``serve_args`` state one keeps it, and :func:`argv` adds none.
ALIAS_FLAGS = ("--alias", "-a")
# What a llama.cpp process that only lends its card to a server on another
# machine runs (:data:`mcgyvr.serving.ROLE_RPC`): the worker binary, not the
# server. It takes no model, because the head sends it the tensors it holds.
RPC_COMMAND = ("rpc-server",)
ENGINE_IMAGES = {
    "llama.cpp": "ghcr.io/ggml-org/llama.cpp:server-cuda",
    # Default only; a unit's own `image` wins (see `_image`).
    "vllm": "vllm/vllm-openai:v0.26.0",
}

# Where the weights directory appears inside the container. A convention, not a
# choice the spec makes — see the module docstring on why the argv does not use
# it.
MOUNT = "/models"

#: What a vLLM unit is started with where ``serving.enable_sleep_wake`` is on
#: (:func:`sleep_mode`): the flag that lets it sleep at level 2, and the
#: variable that registers the routes the door sleeps and wakes it through.
VLLM_SLEEP_FLAG = "--enable-sleep-mode"
VLLM_DEV_ROUTES = "VLLM_SERVER_DEV_MODE"

#: What a launch spec written with sleep mode says first, because the variable
#: it sets is a fact about who can reach the unit and not only about how it runs.
SLEEP_MODE_NOTICE = """\
# serving.enable_sleep_wake is on, so every vLLM unit below runs with
# --enable-sleep-mode and VLLM_SERVER_DEV_MODE=1. That registers vLLM's
# development routes on each unit's serving port -- /sleep, /wake_up,
# /is_sleeping, /reset_prefix_cache, /collective_rpc and others -- and they are
# unauthenticated: anyone who can reach the port can put the unit to sleep,
# wake it or reset it. Keep the port reachable only by who should do that.
"""


def sleep_mode(config: Config) -> bool:
    """Whether vLLM units are emitted with sleep mode: ``serving.enable_sleep_wake``.

    One switch for two things on purpose. The level-2 sleep the ladder manager
    uses needs the flag and the routes, and the routes are unauthenticated, so
    a config that did not ask mcgyvr to sleep and wake cards does not get them.
    """
    return bool(config.get("serving.enable_sleep_wake"))


if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.config import Config

# Re-exported from :mod:`mcgyvr.serving`, where they are defined.
__all__ = ["COMPOSE_PREFIX", "COMPOSE_SUFFIX", "safe_host", "safe_model"]

# Compose service names: the process, not the file.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class EmitError(Exception):
    """A launch spec could not be rendered — for a host, an engine or a path."""


def _media_engine_not_wired(unit: Unit) -> str:
    """Why a media engine's unit is refused before it is rendered.

    ComfyUI and the TTS engines land later. Until one does there is no command
    line and no image for it, and mcgyvr will not render a media unit with
    another engine's flags.
    """
    return (
        f"{unit.key.slug}: engine {unit.engine!r} is not wired in this build; "
        "mcgyvr will not render a unit for an engine it has no launch spec "
        "for rather than emit another engine's flags."
    )


def argv(unit: Unit, *, sleep_mode: bool = False) -> tuple[str, ...]:
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

    ``--port`` is stated rather than left to the engine, because the address
    the unit was built from is a promise about where that unit answers, and a
    server listening somewhere else makes the config a lie — one that reads as
    a dead unit, or as two models on one host where the second never came up
    because the first already had 8080. Written here, in the one argv, so the
    compose file and the pasted command cannot disagree about it.

    ``sleep_mode`` adds vLLM's ``--enable-sleep-mode`` (:func:`sleep_mode`), and
    only for a vLLM unit: llama.cpp has no such mode.

    ``--alias`` is the unit's model, on a llama.cpp server: without it
    llama-server names every answer after the path it was handed, so a request
    for the model the setup declares is answered under a file path, and a
    rider this unit is shared with (:mod:`mcgyvr.rig.hitchhike`) receives that
    path as the answer's model. An alias the spec's ``serve_args`` state is the
    owner's and is the only one written; a worker (``rpc``) answers no request
    and gets none, and vLLM already serves the id it was started with.
    """
    if unit.engine in MEDIA_ENGINES_NOT_WIRED:
        raise EmitError(_media_engine_not_wired(unit))
    flags = {**unit.args, "--port": str(unit.port)}
    if (
        unit.engine == "llama.cpp"
        and unit.role == ROLE_SERVE
        and not any(flag in ALIAS_FLAGS for flag in (*flags, *unit.extra))
    ):
        flags["--alias"] = unit.model
    # vLLM takes the model as its first positional argument, and it is the
    # model id — a repository path the cache resolves — never a file. Then
    # the derived flags, then whatever the spec's ``serve_args`` said, in the
    # order it said it: a flag repeated there overrides, which is what
    # "verbatim" has to mean for an argv the engine reads left to right.
    lead = (unit.model,) if unit.engine == "vllm" else ()
    sleeps = (VLLM_SLEEP_FLAG,) if sleep_mode and unit.engine == "vllm" else ()
    parts = (
        *lead,
        *(part for flag in sorted(flags) for part in (flag, str(flags[flag]))),
        *sleeps,
        *unit.extra,
    )
    for part in parts:
        if part.split() != [part]:
            raise EmitError(
                f"{unit.key.slug}: argument {part!r} contains whitespace, which the "
                "compose file and the bare command cannot spell the same way"
            )
    return parts


def render_command(unit: Unit, *, sleep_mode: bool = False) -> str:
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
    routes = (f"{VLLM_DEV_ROUTES}=1",) if sleep_mode and unit.engine == "vllm" else ()
    return shlex.join((*routes, *_command(unit), *argv(unit, sleep_mode=sleep_mode)))


def render_compose(unit: Unit | None, *, sleep_mode: bool = False) -> str:
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
    return _document((unit,), sleep_mode=sleep_mode)


def emit_all(
    units: Iterable[Unit], root: Path, *, sleep_mode: bool = False
) -> tuple[Path, ...]:
    """Write one compose file per launch spec under ``root``. Returns what was written.

    A launch spec is a set of units that come up **together**, which is usually
    a host and is not always one. Per host is the right grouping for
    co-residents: ``docker compose -f compose.desktop-1.yml up`` starts
    everything that machine serves, and two files for one rig would be two
    commands with a rule about which comes first. It is the wrong grouping for
    alternatives, where the rule about which comes first is that only one ever
    does — see :func:`_planned`.

    Nothing is written outside ``root``, and a host name that would climb out of
    it is refused rather than sanitised — a host is a key that scans, units and
    files are all filed under, and quietly rewriting it here would file this
    file under a name nothing else uses.
    """
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for path, document in _planned(units, root, sleep_mode=sleep_mode):
        path.write_text(document, encoding="utf-8")
        written.append(path)
    return tuple(written)


@dataclass(frozen=True)
class Drift:
    """One compose file that is not what the config would emit today.

    ``found`` is ``None`` when nothing is there at all, and that is deliberately
    not spelled as an empty string: "never emitted" and "emitted from a config
    that has since moved" send an operator to different commands — one writes a
    file for the first time, the other re-emits and restarts a container that is
    already up and serving the wrong argv. A reader that could not tell them
    apart would send half of them to the wrong one.
    """

    path: Path
    #: The document this config implies, as :func:`emit_all` would write it.
    emitted: str
    #: The document on disk, or ``None`` where there is none.
    found: str | None

    @property
    def missing(self) -> bool:
        return self.found is None

    def diff(self) -> tuple[str, ...]:
        """The on-disk file against the one the config implies, unified.

        Empty for a missing file: there is no line that changed, only a file
        that is not there, and rendering the whole document as additions would
        bury that fact in its own output.
        """
        if self.found is None:
            return ()
        return tuple(
            line.rstrip("\n")
            for line in difflib.unified_diff(
                self.found.splitlines(keepends=True),
                self.emitted.splitlines(keepends=True),
                fromfile=f"{self.path.name} (on disk)",
                tofile=f"{self.path.name} (this config)",
                n=1,
            )
        )


def check_all(
    units: Iterable[Unit], root: Path, *, sleep_mode: bool = False
) -> tuple[Drift, ...]:
    """Which of ``root``'s compose files are not what ``units`` would write.

    The other half of :func:`emit_all`, sharing its plan so that the comparison
    is against the same bytes the same call would produce — a check rendering
    its own document would be the second configuration this module's own
    docstring warns about, and it would agree with the file it was checking
    exactly until the day it mattered.

    Files this config says nothing about are not read and not reported. A
    directory may hold compose files for rigs a ladder no longer binds, and
    calling those a drift would ask an operator to delete evidence of a machine
    that is still serving perfectly well; what this answers is whether the
    ladder in hand and the files on disk agree about the rigs it names.

    Nothing is written and nothing is created — not even ``root``, which
    :func:`emit_all` makes and this deliberately does not: a check that
    conjured an empty directory would report every file missing from a place
    it had just invented.
    """
    return _drifts(_planned(units, root, sleep_mode=sleep_mode))


def planned_paths(
    units: Iterable[Unit], root: Path, *, sleep_mode: bool = False
) -> tuple[Path, ...]:
    """The files :func:`emit_all` would write, without rendering an opinion.

    For a reporter that wants to name them — a clean ``--check`` says which
    files it just agreed with — and it asks the planner rather than spelling
    ``compose.<host>.yml`` itself, which is not the name of every spec: a host
    may hold alternatives.
    """
    return tuple(path for path, _ in _planned(units, root, sleep_mode=sleep_mode))


def unplanned(
    units: Iterable[Unit], root: Path, *, sleep_mode: bool = False
) -> tuple[Path, ...]:
    """Launch specs on disk for a rig this ladder binds that this config does not write.

    **The third answer, and it is neither of the two :func:`check_all` gives.**
    A planned file that differs is a drift; a file this config says nothing
    about is not read at all, deliberately, because a directory may hold compose
    files for rigs a ladder no longer binds and calling those a drift asks an
    operator to delete evidence of a machine that is serving. What sits between
    them is a file that matches **mcgyvr's own naming convention, for a host
    this ladder still names, that this config would not write** — and that is
    not somebody else's file. It is one of ours, left behind.

    It is left behind constantly and by design: ``emit`` writes what a config
    plans and deletes nothing, so the day a host's units stop summing onto its
    card, ``emit`` writes ``compose.<host>.<model>.yml`` per alternative and the
    old ``compose.<host>.yml`` — holding every unit on one card, the overcommit
    :func:`~mcgyvr.serving.hold_together` was written to refuse — simply stays.
    :func:`~mcgyvr.serving.spec_files` finds it, so a wake declines to guess
    rather than starting it, and this is what tells the operator it is there.

    Reported at drift severity by :func:`mcgyvr.cli._report_drift` rather than as
    a warning, for the reason drift is: the consequence is a rig serving argv
    nobody is reading. The repair is different and the sentence says so — a
    drifted file is re-emitted, this one is deleted.
    """
    units = tuple(units)
    hosts = {unit.host for unit in units}
    planned = {path.name for path in planned_paths(units, root, sleep_mode=sleep_mode)}
    found: list[Path] = []
    for host in sorted(hosts):
        found.extend(
            path for path in spec_files(root, host) if path.name not in planned
        )
    return tuple(sorted(set(found)))


def _planned(
    units: Iterable[Unit], root: Path, *, sleep_mode: bool = False
) -> tuple[tuple[Path, str], ...]:
    """Every (path, document) pair a ladder's units resolve to, path-sorted.

    Shared so that writing and checking cannot disagree about grouping, naming
    or refusal: the answer is a value, so a caller may compare it with the disk
    instead of committing it to the disk.

    The cut into files is :func:`~mcgyvr.serving.launch_specs`' and not this
    module's — what comes up together is a fact about the *card* units share.
    What is decided here is only how a spec is spelled:
    ``compose.<host>.yml`` for a host that comes up as one,
    and ``compose.<host>.<what tells it apart>.yml`` otherwise, because
    ``serve up --compose`` takes one file and starts what is in it. The
    discriminator is :func:`~mcgyvr.serving.launch_specs`' too — usually the
    model of the spec's largest unit, and more where a host needs more to tell
    two specs apart.
    """
    planned: list[tuple[Path, str]] = []
    # What each file name is a name *for*, so that two things reaching one path
    # is an error somebody sees. Spelling a host or a model into a file name is
    # many-to-one wherever it rewrites anything — and for an IPv6 literal, and
    # for a HuggingFace repository id, it does. Left alone that is not an error
    # anybody sees: the second file overwrites the first and one unit is simply
    # absent from the output, which is the same silent loss as two models in
    # one compose service.
    claimed: dict[str, str] = {}
    for spec in launch_specs(units):
        name = spec_name(spec.host, spec.model)
        called = spec.units[0].key.slug if spec.model is not None else spec.host
        first = claimed.setdefault(name, called)
        if first != called:
            raise EmitError(
                f"{called!r} and {first!r} would both be written to {name}, and "
                "the second file would be the only one left"
            )
        path = root / name
        # `path.resolve().parent` and not `path.parent.resolve()`: the name is
        # sanitised and cannot climb, but a symlink planted at it can, and only
        # resolving the file itself sees that. It holds for a path that does
        # not exist yet, which is every path on a first emit and some on a
        # check.
        if path.resolve().parent != root.resolve():
            raise EmitError(f"{spec.host}: would write outside {root}")
        planned.append((path, _document(spec.units, sleep_mode=sleep_mode)))
    return tuple(sorted(planned, key=lambda pair: pair[0].name))


def _document(units: tuple[Unit, ...], *, sleep_mode: bool = False) -> str:
    """The compose document for one host's units, sorted throughout.

    Two units that spell one service name are refused rather than merged.
    :func:`_service_name` is many-to-one — ``qwen2.5-coder:3b`` and
    ``qwen2.5-coder-3b`` are two sets of weights, two processes and one compose
    name — and keeping the last of them writes a file that looks entirely
    correct, brings up one server and leaves the unit bound to the other with
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
        services[name] = _service(unit, sleep_mode=sleep_mode)
    _sequence_on_one_card(units, services)
    document = yaml.safe_dump({"services": services}, sort_keys=True, width=200)
    if sleep_mode and any(unit.engine == "vllm" for unit in units):
        return SLEEP_MODE_NOTICE + document
    return document


def _sequence_on_one_card(
    units: tuple[Unit, ...], services: dict[str, dict[str, object]]
) -> None:
    """Chain the units that share a card so they load one at a time, in place.

    A compose file with no dependency between its services tells the daemon to
    start every one of them at once, which on a card that fits both only if
    they load one after the other is a race: an engine sizes its share from the
    card's free memory while it starts, and two starting together can each
    count memory the other is about to take.

    The order this code writes is largest card figure first, then service
    name. Which order is right is not settled; the sort is total so that two
    runs of ``emit`` over one config write the same file.

    A chain rather than a fan-in, so that three units on one card load one at a
    time as well as two.

    Units on different cards are not sequenced: they do not contend, and a
    dependency there is noise that delays every restart. Neither is a host with
    one unit, for the same reason.

    **The condition is ``service_healthy``.** ``service_started`` releases the
    waiter as soon as the process ahead of it exists, long before that process
    has read its weights and taken its card, so it does not sequence.

    A healthcheck is written **only on a service something waits for**, which is
    only ever a co-resident. ``service_healthy`` against a service that declares
    none never releases at all, so the two go together; a single-unit rig's
    compose file carries neither.

    The check asks the unit's own port, which under host networking is the only
    thing telling two units on one host apart. It is deliberately the same
    ``/v1/models`` that ``servelib.wait_for`` gates on: a unit that can list its
    models has read its weights and taken its card, which is the fact the waiter
    needs and the only one both engines report the same way.
    """
    on_card: dict[int, list[tuple[float, str, int]]] = {}
    for unit in units:
        if unit.cpu_only:
            continue
        # A worker or a headless node answers no ``/v1/models``, so a check on
        # it never passes and whatever waits on it never starts; they are not
        # chained.
        if unit.role != ROLE_SERVE:
            continue
        for card in unit.cards:
            on_card.setdefault(card, []).append(
                (unit.fit.vram_gb, _service_name(unit), unit.port)
            )
    for sharing in on_card.values():
        if len(sharing) < 2:
            continue
        ordered = sorted(sharing, key=lambda triple: (-triple[0], triple[1]))
        for (_, waiter, _), (_, ahead, port) in zip(
            ordered[1:], ordered[:-1], strict=True
        ):
            # Merged, because a unit that spans cards can wait on a neighbour
            # of each of them.
            waits = services[waiter].setdefault("depends_on", {})
            assert isinstance(waits, dict)
            waits[ahead] = {"condition": "service_healthy"}
            services[ahead]["healthcheck"] = _healthcheck(port)


#: How long a unit ahead of another may take to read its weights and take its
#: card before compose calls it unhealthy. Generous on purpose: a healthcheck
#: that gives up is a pair that never starts, and the door's own health poll
#: (`mcgyvr.config.HEALTH_POLLS` x `HEALTH_INTERVAL_S`) is what gives up.
_HEALTH_START_PERIOD_S = 600


def _healthcheck(port: int) -> dict[str, object]:
    """The check a co-resident's neighbour waits on.

    ``start_period`` rather than a long ``retries``: during it a failing probe
    does not count against the container, which is exactly the state a unit
    is in while it loads. ``CMD-SHELL`` with a ``wget`` fallback
    because the two engines ship different base images and neither promises
    ``curl`` — a check whose binary is absent is a container that is unhealthy
    forever, and a waiter that never starts.
    """
    url = f"http://localhost:{port}/v1/models"
    return {
        "test": [
            "CMD-SHELL",
            f"curl -sf {url} >/dev/null 2>&1 || wget -q -O- {url} >/dev/null 2>&1",
        ],
        "interval": "5s",
        "timeout": "3s",
        "retries": 3,
        "start_period": f"{_HEALTH_START_PERIOD_S}s",
    }


def _service(unit: Unit, *, sleep_mode: bool = False) -> dict[str, object]:
    """One unit as a compose service.

    The device reservation names the cards the scan actually found rather than
    handing the container every GPU: on a two-card rig ``all`` is how two units
    sized for two different cards end up fighting over one. A unit that spans
    cards names each of them.
    """
    _check_role(unit)
    if unit.engine == "vllm":
        return _vllm_service(unit, sleep_mode=sleep_mode)
    if unit.engine in MEDIA_ENGINES:
        return _media_service(unit)
    if unit.role == ROLE_RPC:
        return _rpc_service(unit)
    return {
        "image": _image(unit),
        "container_name": f"mcgyvr-{safe_host(unit.host)}-{_service_name(unit)}",
        "command": list(argv(unit)),
        # The host's network rather than a published port, for the same reason
        # the argv is built once: the port is already in the argv, so a
        # published mapping would be a second answer to "where do I reach
        # this" — one that can differ from the pasted command's, which is the
        # drift this module exists to prevent. Under host networking there is
        # one number, the one the unit's address named, and both renderings say it.
        "network_mode": "host",
        # The rig is reached from another machine, and llama-server's own
        # default bind is loopback — which under host networking would serve
        # only the rig itself. Stated as the server's environment variable
        # rather than as an argument, on purpose: the argv has to stay
        # identical in both renderings, and this is a fact about where the
        # container sits rather than about how the model is loaded.
        "environment": _environment({"LLAMA_ARG_HOST": "0.0.0.0"}, unit),
        "restart": "unless-stopped",
        "volumes": sorted(
            {
                f"{unit.weights_dir}:{MOUNT}:ro",
                f"{unit.weights_dir}:{unit.weights_dir}:ro",
            }
        ),
        "deploy": _reservation(*unit.cards),
    }


def _rpc_service(unit: Unit) -> dict[str, object]:
    """A llama.cpp ``rpc-server`` worker as a compose service.

    It lends one card and holds no model file, so nothing is mounted: the head
    sends it the tensors it is to hold. The image's entrypoint is the server,
    so the worker binary is the entrypoint here and the argv is its command.
    Deliberately without ``LLAMA_ARG_HOST``: this process is unauthenticated,
    and the address it listens on is the ``-H`` the launch states and nothing
    wider.
    """
    service: dict[str, object] = {
        "image": _image(unit),
        "container_name": f"mcgyvr-{safe_host(unit.host)}-{_service_name(unit)}",
        "entrypoint": list(RPC_COMMAND),
        "command": list(argv(unit)),
        "network_mode": "host",
        "restart": "unless-stopped",
        "deploy": _reservation(*unit.cards),
    }
    environment = _environment({}, unit)
    if environment:
        service["environment"] = environment
    return service


def _environment(base: dict[str, str], unit: Unit) -> dict[str, str]:
    """The service's environment: what this module sets, then the unit's own.

    Both are facts about how the process runs, so neither may silently win: a
    unit that sets a variable this module already sets differently is refused,
    naming the variable and the unit.
    """
    merged = dict(base)
    for key, value in unit.env.items():
        if key in merged and merged[key] != value:
            raise EmitError(
                f"{unit.key.slug}: its env sets {key}={value!r} and the emitted "
                f"service already sets {key}={merged[key]!r}; drop one of them"
            )
        merged[key] = value
    return merged


def _vllm_service(unit: Unit, *, sleep_mode: bool = False) -> dict[str, object]:
    """A vLLM unit as a compose service.

    The weights are a repository id resolved in the rig's HuggingFace cache,
    so that cache is what gets mounted — read-only, at the image's own cache
    path so the id resolves with no further flag — and the server is started
    offline, so a rig never downloads at load. ``ipc: host`` is what vLLM's
    own image documents for its shared-memory tensors.

    With ``sleep_mode`` the unit also runs with vLLM's sleep flag and its
    development routes (:data:`SLEEP_MODE_NOTICE` says what that exposes).
    """
    environment = {"HF_HUB_OFFLINE": "1"}
    if sleep_mode:
        environment[VLLM_DEV_ROUTES] = "1"
    return {
        "image": _image(unit),
        "container_name": f"mcgyvr-{safe_host(unit.host)}-{_service_name(unit)}",
        "command": list(argv(unit, sleep_mode=sleep_mode)),
        "network_mode": "host",
        "ipc": "host",
        "environment": _environment(environment, unit),
        "restart": "unless-stopped",
        "volumes": [f"{unit.weights_dir}:{HF_CACHE_MOUNT}:ro"],
        "deploy": _reservation(*unit.cards),
    }


def _media_service(unit: Unit) -> dict[str, object]:
    """A media unit as a compose service.

    mcgyvr ships no media server image or shell binary: the container image is
    the operator's and its entrypoint is the server, so the compose file names
    that image and mounts the weights directory at its own absolute path with
    no environment of mcgyvr's. The image contract is ENTRYPOINT-as-server:
    compose ``command`` supplies only the argv. A cpu_only unit (a Piper-class
    TTS rung) claims no card, so its service carries no GPU reservation.
    """
    service: dict[str, object] = {
        "image": _image(unit),
        "container_name": f"mcgyvr-{safe_host(unit.host)}-{_service_name(unit)}",
        "command": list(argv(unit)),
        "network_mode": "host",
        "restart": "unless-stopped",
        "volumes": [f"{unit.weights_dir}:{unit.weights_dir}:ro"],
    }
    if not unit.cpu_only:
        service["deploy"] = _reservation(unit.gpu)
    return service


def _command(unit: Unit) -> tuple[str, ...]:
    _check_role(unit)
    if unit.role == ROLE_RPC:
        return RPC_COMMAND
    command = ENGINE_COMMANDS.get(unit.engine)
    if command is None:
        if unit.engine in MEDIA_ENGINES_NOT_WIRED:
            raise EmitError(_media_engine_not_wired(unit))
        if unit.engine in MEDIA_ENGINES:
            raise EmitError(
                f"{unit.key.slug}: engine {unit.engine!r} has no shell command — its "
                "server is the container image's entrypoint, so render the "
                "compose file rather than a pasted command"
            )
        raise EmitError(
            f"{unit.key.slug}: no command line is known for engine {unit.engine!r}"
        )
    return command


def _check_role(unit: Unit) -> None:
    """Refuse a role its engine has no process for, by the unit's name.

    ``rpc-server`` is llama.cpp's worker and ``--headless`` is vLLM's node that
    answers nothing; either on the other engine would render a command the
    engine does not have, and fail at load on the rig with a message about
    neither.
    """
    if unit.role == ROLE_SERVE:
        return
    if unit.role == ROLE_RPC and unit.engine == "llama.cpp":
        return
    if unit.role == ROLE_HEADLESS and unit.engine == "vllm":
        return
    raise EmitError(
        f"{unit.key.slug}: role {unit.role!r} is not a process engine "
        f"{unit.engine!r} has (llama.cpp's workers are 'rpc', vLLM's are 'headless')"
    )


def _needs_built_image(unit: Unit) -> bool:
    """Whether this llama.cpp process needs an image built with RPC support.

    The ``rpc-server`` worker, and a server that reaches workers with
    ``--rpc``. The upstream CUDA images are built without it, so the engine's
    default image cannot be what either runs in.
    """
    return unit.engine == "llama.cpp" and (
        unit.role == ROLE_RPC or "--rpc" in unit.args
    )


def _image(unit: Unit) -> str:
    if unit.image:
        return unit.image
    if unit.engine in MEDIA_ENGINES:
        raise EmitError(
            f"{unit.key.slug}: engine {unit.engine!r} has no default container image — "
            f"set units.<unit>.image to the operator's {unit.engine} server image"
        )
    if _needs_built_image(unit):
        what = (
            "an rpc-server worker" if unit.role == ROLE_RPC else "a server with --rpc"
        )
        raise EmitError(
            f"{unit.key.slug}: {what} needs a llama.cpp image built with RPC "
            f"support, and the upstream CUDA images are built without it. State "
            f"the image you built as the unit's `image`; mcgyvr will not "
            f"default to one that cannot run it"
        )
    image = ENGINE_IMAGES.get(unit.engine)
    if image is None:
        if unit.engine in MEDIA_ENGINES_NOT_WIRED:
            raise EmitError(_media_engine_not_wired(unit))
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
    name = f"{_UNSAFE.sub('-', unit.model)}-{unit.port}"
    # A worker is a process of the same model on a port of its own, and on a
    # machine that also serves the model the role is what tells them apart.
    return name if unit.role == ROLE_SERVE else f"{name}-{unit.role}"


class LockedLaunchError(EmitError):
    """A locked unit does not state what its launch needs to be rendered."""


def is_locked(fleet: Mapping[str, Any]) -> bool:
    """Whether a parsed ``fleet.yaml`` is a locked setup: a unit carries its unit_id."""
    units = fleet.get("units") or {}
    return any(
        isinstance(block, Mapping) and bool(block.get("unit_id"))
        for block in units.values()
    )


def emit_locked(
    fleet: Mapping[str, Any], root: Path, setup: Path | None = None
) -> tuple[Path, ...]:
    """Write one compose file per fleet per rig of a locked ``fleet.yaml``.

    A locked unit was measured, approved and hashed, so what is rendered is the
    launch it states and not one sized here: no scan, no fit, no cache dtype.
    Every file is planned, and every refusal raised, before the first one is
    written.

    ``setup`` is the directory the fleet files are in, which is what a unit's
    ``launch.seccomp`` is named relative to. A unit that states one has its
    profile written beside the compose file that names it, because that is
    where compose looks for it; a fleet where nobody states one needs no
    ``setup``.
    """
    planned = _planned_locked(fleet, root, setup)
    root.mkdir(parents=True, exist_ok=True)
    for path, document in planned:
        path.write_text(document, encoding="utf-8")
    return tuple(path for path, _ in planned)


def check_locked(
    fleet: Mapping[str, Any], root: Path, setup: Path | None = None
) -> tuple[Drift, ...]:
    """Which of ``root``'s files are not what :func:`emit_locked` would write."""
    return _drifts(_planned_locked(fleet, root, setup))


def planned_locked_paths(
    fleet: Mapping[str, Any], root: Path, setup: Path | None = None
) -> tuple[Path, ...]:
    """The files :func:`emit_locked` would write."""
    return tuple(path for path, _ in _planned_locked(fleet, root, setup))


def unplanned_locked(
    fleet: Mapping[str, Any], root: Path, setup: Path | None = None
) -> tuple[Path, ...]:
    """Launch specs on disk for a rig a locked layout names that it does not write.

    The locked counterpart of :func:`unplanned`: a leftover
    ``compose.<host>.yml`` is still where a wake would look for that rig.
    """
    hosts = {
        host
        for block in (fleet.get("fleets") or {}).values()
        for host in (block.get("layout") or {})
    }
    planned = {path.name for path in planned_locked_paths(fleet, root, setup)}
    found: set[Path] = set()
    for host in hosts:
        found.update(
            path for path in spec_files(root, host) if path.name not in planned
        )
    return tuple(sorted(found))


def _drifts(planned: tuple[tuple[Path, str], ...]) -> tuple[Drift, ...]:
    drifted: list[Drift] = []
    for path, document in planned:
        try:
            found: str | None = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            found = None
        except OSError as exc:
            raise EmitError(f"{path}: cannot be read to compare — {exc}") from exc
        if found != document:
            drifted.append(Drift(path=path, emitted=document, found=found))
    return tuple(drifted)


def _planned_locked(
    fleet: Mapping[str, Any], root: Path, setup: Path | None = None
) -> tuple[tuple[Path, str], ...]:
    """``compose.<host>.<fleet>.yml`` per fleet per rig, services in layout order.

    The layout is the start order: each service waits for the one before it to
    be healthy.

    A unit that states ``launch.seccomp`` adds one more planned file: the
    profile itself, beside the compose file that names it, because compose
    resolves the path against the compose file's own directory and reads it
    there. It is planned like any other file, so ``--check`` compares it and a
    re-emit rewrites it.

    A unit reserves the cards its ``launch.shards`` name on the rig being
    rendered (:mod:`mcgyvr.fleet.spans`), and card 0 when it names none. A
    locked launch is one argv, its head's, so a unit that spans rigs is
    refused by name: on a worker's rig it would start a second head.
    """
    units = fleet.get("units") or {}
    try:
        found = spans(fleet)
    except SpanError as exc:
        raise LockedLaunchError(str(exc)) from exc
    planned: list[tuple[Path, str]] = []
    profiles: dict[str, Path] = {}
    for fleet_name, block in sorted((fleet.get("fleets") or {}).items()):
        for host, slots in sorted((block.get("layout") or {}).items()):
            services: dict[str, dict[str, object]] = {}
            ahead: tuple[str, int] | None = None
            for slot in slots:
                name = slot[0]
                unit = units.get(name)
                if not isinstance(unit, Mapping):
                    raise LockedLaunchError(
                        f"{fleet_name}: {name} is in the {host} layout and "
                        "fleet.yaml declares no such unit"
                    )
                span = found.get(name)
                if span is not None and len(span.rigs) > 1:
                    raise LockedLaunchError(
                        f"{name}: spans {', '.join(span.rigs)}, and a locked "
                        f"launch states one argv, its head's on {span.head}; "
                        f"rendered on {host} it would be a second head, not a "
                        "worker. A locked unit split across rigs is not "
                        "rendered until each worker's launch is stated"
                    )
                cards = span.cards.get(host, ()) if span is not None else (0,)
                if not cards:
                    raise LockedLaunchError(
                        f"{fleet_name}: {name} is in the {host} layout and its "
                        f"launch.shards name no card there"
                    )
                service = _locked_service(name, unit, cards)
                stated = (unit.get("launch") or {}).get("seccomp")
                if isinstance(stated, str) and stated.strip():
                    source = _profile_source(name, stated, setup)
                    first = profiles.setdefault(Path(stated).name, source)
                    if first != source:
                        raise EmitError(
                            f"{name}: launch.seccomp {stated} and {first} are two "
                            f"profiles with one file name, and the compose file "
                            "names each by its file name alone — rename one"
                        )
                if ahead is not None:
                    waited_on, port = ahead
                    service["depends_on"] = {
                        waited_on: {"condition": "service_healthy"}
                    }
                    services[waited_on]["healthcheck"] = _healthcheck(port)
                services[name] = service
                ahead = (name, port_of(str(unit.get("address") or "")))
            path = root / spec_name(host, fleet_name)
            if path.resolve().parent != root.resolve():
                raise EmitError(f"{host}: would write outside {root}")
            document = yaml.safe_dump({"services": services}, sort_keys=True, width=200)
            planned.append((path, document))
    for file_name, source in sorted(profiles.items()):
        path = root / file_name
        if path.resolve().parent != root.resolve():
            raise EmitError(f"{file_name}: would write outside {root}")
        planned.append((path, source.read_text(encoding="utf-8")))
    return tuple(sorted(planned, key=lambda pair: pair[0].name))


def _locked_service(
    name: str, unit: Mapping[str, Any], cards: tuple[int, ...] = (0,)
) -> dict[str, object]:
    """One locked unit as a compose service: its stated launch, verbatim.

    ``cards`` are the card indices it reserves on this rig; card 0 for a unit
    that names none.
    """
    launch = unit.get("launch") or {}
    argv = launch.get("argv")
    env = launch.get("env", {})
    volumes = launch.get("volumes")
    seccomp = launch.get("seccomp")
    engine = unit.get("engine")
    missing: list[str] = []
    for key in ("unit_id", "image", "container"):
        if not isinstance(unit.get(key), str) or not unit.get(key):
            missing.append(key)
    if not _strings(argv) or not argv:
        missing.append("launch.argv (a list of strings)")
    if not isinstance(env, Mapping) or not _strings(list(env.values())):
        missing.append("launch.env (a mapping of strings)")
    if engine == "vllm":
        if not isinstance(unit.get("hf_cache"), str) or not unit.get("hf_cache"):
            missing.append("hf_cache")
    elif engine == "llama.cpp":
        if not _strings(volumes) or not volumes:
            missing.append("launch.volumes (a list of strings)")
    else:
        missing.append("engine (llama.cpp or vllm)")
    if seccomp is not None and (not isinstance(seccomp, str) or not seccomp.strip()):
        missing.append("launch.seccomp (a file name)")
    if missing:
        raise LockedLaunchError(
            f"{name}: a locked unit is rendered from what it states, and it does "
            f"not state {', '.join(missing)}"
        )
    service: dict[str, object] = {
        "image": unit["image"],
        "container_name": unit["container"],
        "command": list(argv or ()),
        "environment": dict(env),
        "network_mode": "host",
        "restart": "unless-stopped",
        "deploy": _reservation(*cards),
    }
    if isinstance(seccomp, str) and seccomp.strip():
        # Compose resolves a profile path against the PROJECT directory — the
        # compose file's own — and reads the file itself, sending the JSON to
        # the daemon (`docker/compose`, pkg/compose/create.go:
        # `os.ReadFile(p.RelativePath(...))`). So the profile is written beside
        # this file and named here by its file name alone, which keeps the
        # rendered bytes the same wherever the tree is checked out.
        service["security_opt"] = [f"seccomp={Path(seccomp).name}"]
    if engine == "vllm":
        service["ipc"] = "host"
        service["volumes"] = [f"{unit['hf_cache']}:{HF_CACHE_MOUNT}:ro"]
    else:
        service["volumes"] = list(volumes or ())
    return service


def _profile_source(name: str, stated: str, setup: Path | None) -> Path:
    """The seccomp profile a unit's launch names, as the file beside fleet.yaml."""
    if setup is None:
        raise LockedLaunchError(
            f"{name}: launch.seccomp names {stated}, and this emit was not told "
            "where the fleet files are, so the profile cannot be read"
        )
    path = setup / stated
    if not path.is_file():
        raise LockedLaunchError(
            f"{name}: launch.seccomp names {stated}, and {path} is not a file"
        )
    return path


def _strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(part, str) for part in value)


def _reservation(*gpus: int) -> dict[str, object]:
    return {
        "resources": {
            "reservations": {
                "devices": [
                    {
                        "driver": "nvidia",
                        "device_ids": [str(gpu) for gpu in gpus],
                        "capabilities": ["gpu"],
                    }
                ]
            }
        }
    }
