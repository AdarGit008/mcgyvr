"""Render serving units into launch artifacts, and compare them with disk.

A unit is rendered two ways that must agree: a compose document under
``services:`` -- written by `emit_all`, compared by `check_all`, named by
`spec_name` -- and a bare command line (`render_command`) for an operator
who starts the process by hand. Nothing here starts anything: emitting is
writing a file, and the rig's operator runs it.

A second family renders a ``fleet.yaml`` whose units state their own
launch -- image, container, argv, env, a "locked" unit: `emit_locked`
writes those documents, `check_locked` compares them, and both refuse a
unit that states too little to render. A locked llama.cpp unit split
across rigs is its stated head on the head's rig plus the rpc-server
workers the unlocked path would start on the other rigs, at the addresses
their shards or rig files give.

Every refusal is an `EmitError`: an engine this build has no command or
image for, an argument the compose file and the shell command cannot spell
the same way, a file name two units would both
claim, or a path that resolves outside the output directory.
"""

from __future__ import annotations

import difflib
import ipaddress
import re
import shlex
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml

from mcgyvr.config import LAUNCHER_NATIVE
from mcgyvr.fleet.spans import Shard, Span, SpanError, check_spans, spans
from mcgyvr.serving import (
    CARDS_KEY,
    COMPOSE_PREFIX,
    COMPOSE_SUFFIX,
    HF_CACHE_MOUNT,
    LAUNCHER_KEY,
    PROGRAM_KEY,
    ROLE_HEADLESS,
    ROLE_RPC,
    ROLE_SERVE,
    RPC_DEFAULT_PORT,
    SLEEPER_PROFILE,
    Fit,
    Unit,
    UnitKey,
    Width,
    host_of,
    kernelcache,
    launch_specs,
    llamacpp,
    nativerig,
    port_of,
    rigfile,
    safe_host,
    safe_model,
    spec_files,
    spec_name,
)
from mcgyvr.serving.gatelib import LOCAL_RIGS
from mcgyvr.serving.llamacpp import HOST_ENV as HOST_ENV
from mcgyvr.serving.llamacpp import HOST_FLAG, LOOPBACK
from mcgyvr.serving.sharding import Target
from mcgyvr.serving.shardlaunch import (
    LaunchError,
    rpc_endpoints,
    rpc_workers,
)

# The shell command that starts each engine's own server; `_command`
# refuses any other engine rather than inventing a command line.
ENGINE_COMMANDS = {"llama.cpp": ("llama-server",), "vllm": ("vllm", "serve")}
# The flags llama.cpp spells a served model's name with. `argv` adds
# `--alias` only for a serve unit of that engine that carries none already.
ALIAS_FLAGS = ("--alias", "-a")
# The command of a llama.cpp rpc-server worker: one process of a model
# split across rigs, which serves no model of its own. `_rpc_service` also
# makes it the service's entrypoint, so the image's own one does not run.
RPC_COMMAND = ("rpc-server",)
ENGINE_IMAGES = {
    # The one llama.cpp build mcgyvr pins, the native binaries' too.
    "llama.cpp": llamacpp.IMAGE,
    # vLLM is pinned to a release; a unit's own `image` overrides this.
    "vllm": "vllm/vllm-openai:v0.26.0",
}

# llama.cpp weights are mounted here as well as at their own absolute
# path, so a `-m` the unit states resolves whether it was written against
# the host's layout or against the container's.
MOUNT = "/models"

#: vLLM's sleep spelling: the launch flag that turns sleep mode on, and the
#: env var that registers the development routes `/sleep` and `/wake_up`
#: live on. `SLEEP_MODE_NOTICE` states what exposing those routes costs.
VLLM_SLEEP_FLAG = "--enable-sleep-mode"
VLLM_DEV_ROUTES = "VLLM_SERVER_DEV_MODE"

#: llama.cpp's spellings of its fitting switch -- the flags and the variable
#: that turn off adjusting the arguments a unit leaves unset to the memory free
#: when it starts -- and the values llama.cpp reads as off. A unit that states
#: it off takes the memory its own argv states and no more, so
#: `_fixes_its_memory` lets it start beside the other units on its card.
#: `argv` states `--fit FIT_DEFAULT` for every llama.cpp server whose own
#: flags and env state no fitting of their own: the product already states
#: `-c` and `-ngl`, so fitting would only cost a dry run at startup and read
#: free memory a co-resident unit is still taking. A unit opts back in with
#: `--fit on` among its own `serve_args`.
FIT_FLAGS = ("--fit", "-fit")
FIT_ENV = "LLAMA_ARG_FIT"
FIT_OFF = frozenset({"off", "disabled", "false", "0"})
FIT_DEFAULT = "off"


#: Heads every compose document rendered with sleep mode on: the routes
#: sleep needs are unauthenticated, so the file says so in its first lines.
SLEEP_MODE_NOTICE = """\
# serving.enable_sleep_wake is on, so every vLLM unit below runs with
# --enable-sleep-mode and VLLM_SERVER_DEV_MODE=1. That registers vLLM's
# development routes on each unit's serving port -- /sleep, /wake_up,
# /is_sleeping, /reset_prefix_cache, /collective_rpc and others -- and they are
# unauthenticated: anyone who can reach the port can put the unit to sleep,
# wake it or reset it. Keep the port reachable only by who should do that.
"""


def sleep_mode(config: Config) -> bool:
    """Whether `serving.enable_sleep_wake` is on, read from the config."""
    return bool(config.get("serving.enable_sleep_wake"))


if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.config import Config

# What other modules import from here: the compose-file naming parts and
# the two name sanitisers, all re-exported from `mcgyvr.serving`.
__all__ = ["COMPOSE_PREFIX", "COMPOSE_SUFFIX", "safe_host", "safe_model"]

# What a compose service name cannot carry; `_service_name` folds it to '-'.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class EmitError(Exception):
    """A launch that will not be rendered; the message says which unit and why."""


def argv(unit: Unit, *, sleep_mode: bool = False) -> tuple[str, ...]:
    """The argv of the process that serves `unit`, in one canonical order.

    vLLM takes its model as a positional argument, so the model leads. The
    unit's flags follow sorted by name, `--port` among them, and for a
    llama.cpp serve unit `--alias` added when it carries none of
    `ALIAS_FLAGS` and `--fit FIT_DEFAULT` when it states no fitting of its
    own (`_states_fit`); the sleep flag comes next, and the unit's `extra`
    parts are appended as written. An rpc-server worker takes no `--fit`.
    A part containing whitespace is refused: the compose `command` and the
    shell command could not spell it the same way. A native unit's is not:
    its argv is never a shell line.
    """
    flags = {**unit.args, "--port": str(unit.port)}
    if (
        unit.engine == "llama.cpp"
        and unit.role == ROLE_SERVE
        and not any(flag in ALIAS_FLAGS for flag in (*flags, *unit.extra))
    ):
        flags["--alias"] = unit.model
    if (
        unit.engine == "llama.cpp"
        and unit.role == ROLE_SERVE
        and not _states_fit((*flags, *unit.extra), unit.env)
    ):
        flags[FIT_FLAGS[0]] = FIT_DEFAULT
    # The order is fixed so `render_command` and the compose `command` carry
    # one argv: positional model, flags sorted by name, sleep flag, then the
    # unit's own `extra` tokens untouched. Sorting the flags is what lets one
    # unit render the same bytes twice; `extra` keeps its order because it is
    # the operator's text, not ours.
    lead = (unit.model,) if unit.engine == "vllm" else ()
    sleeps = (VLLM_SLEEP_FLAG,) if sleep_mode and unit.engine == "vllm" else ()
    parts = (
        *lead,
        *(part for flag in sorted(flags) for part in (flag, str(flags[flag]))),
        *sleeps,
        *unit.extra,
    )
    # A native unit's argv is handed to the program as a list, never joined
    # into a line, so a path with a space (a Windows profile's) is kept.
    for part in () if unit.launcher == LAUNCHER_NATIVE else parts:
        if part.split() != [part]:
            raise EmitError(
                f"{unit.key.slug}: argument {part!r} contains whitespace, which the "
                "compose file and the bare command cannot spell the same way"
            )
    return parts


def render_command(unit: Unit, *, sleep_mode: bool = False) -> str:
    """The unit's process as one shell command line, quoted for a shell.

    The sleep-mode env assignment leads when it applies to a vLLM unit,
    then the engine's command, then `argv` -- the same parts the compose
    `command` carries, so the two renderings stay one configuration.
    """
    routes = (f"{VLLM_DEV_ROUTES}=1",) if sleep_mode and unit.engine == "vllm" else ()
    return shlex.join((*routes, *_command(unit), *argv(unit, sleep_mode=sleep_mode)))


def render_compose(unit: Unit | None, *, sleep_mode: bool = False) -> str:
    """The compose document for this one unit.

    `unit` is None when the host was never scanned: there is no unit to
    render, and a launch spec for a machine nobody measured is a guess.
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
    """Write one compose file per launch spec into `root`; return their paths.

    `root` is created if it is missing. Every spec is planned, and every
    refusal raised, before the first file is written, so a unit set that
    fails leaves the directory as it was.
    """
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for path, document in _planned(units, root, sleep_mode=sleep_mode):
        path.write_text(document, encoding="utf-8")
        written.append(path)
    return tuple(written)


@dataclass(frozen=True)
class Drift:
    """One planned file whose content on disk is not what this config renders."""

    path: Path
    #: What this config renders for the file.
    emitted: str
    #: What the file holds on disk, or None when there is no file there.
    found: str | None

    @property
    def missing(self) -> bool:
        return self.found is None

    def diff(self) -> tuple[str, ...]:
        """A one-context unified diff of disk against plan, line by line.

        An absent file has nothing to compare, so the tuple is empty and
        `missing` is what says so.
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
    """The planned files whose disk content differs, a missing file included."""
    return _drifts(_planned(units, root, sleep_mode=sleep_mode))


def planned_paths(
    units: Iterable[Unit], root: Path, *, sleep_mode: bool = False
) -> tuple[Path, ...]:
    """The paths `emit_all` would write, without writing anything."""
    return tuple(path for path, _ in _planned(units, root, sleep_mode=sleep_mode))


def unplanned(
    units: Iterable[Unit], root: Path, *, sleep_mode: bool = False
) -> tuple[Path, ...]:
    """Spec files under `root` for these hosts that this config does not plan.

    `spec_files` matches this host's compose files in `root`; whatever it
    finds that `planned_paths` does not account for is returned, sorted and
    deduplicated.
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
    """The (path, document) pairs the config-backed emit works from.

    Each pair is a compose file and its text, sorted by file name so two
    runs over one config write the same bytes in the same order.
    """
    planned: list[tuple[Path, str]] = []
    # `launch_specs` owns the grouping -- one spec per model on a host, or
    # one whole-host spec when the units there cannot share the box. This
    # loop only names and renders them: the name comes from `spec_name`, and
    # what claims it is the first unit's slug, or the bare host for a
    # whole-host spec. Two claimants on one name are refused rather than
    # overwritten, because the second write would be the only file left and
    # the first unit would lose its launch without anyone being told.
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
        # The name is built from `safe_host`/`safe_model`, so a plain host name
        # cannot escape `root`. A name is still data out of a config, so both
        # sides are resolved and compared before anything is written: a spec
        # whose file would land elsewhere is refused rather than followed, and
        # a launch written outside the named directory is nobody's to find.
        if path.resolve().parent != root.resolve():
            raise EmitError(f"{spec.host}: would write outside {root}")
        planned.append((path, _document(spec.units, sleep_mode=sleep_mode)))
    return tuple(sorted(planned, key=lambda pair: pair[0].name))


def _document(units: tuple[Unit, ...], *, sleep_mode: bool = False) -> str:
    """The compose document for the units of one launch spec.

    Every unit becomes one service under its `_service_name`; two units that
    would take one name are refused, since a file with a single service
    starts only one of them. Units sharing a card start together when each
    fixes its own memory, and are otherwise put in start order by
    `_sequence_on_one_card`; the dump sorts keys and widens lines so the
    same units always render the same bytes. Sleep mode prepends
    `SLEEP_MODE_NOTICE` when any unit here is vLLM.
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
        if unit.asleep:
            # A unit that is asleep is not started by a plain `docker compose
            # up`: it renders under the sleeper profile and is woken on purpose.
            services[name]["profiles"] = [SLEEPER_PROFILE]
    _sequence_on_one_card(units, services)
    document = yaml.safe_dump({"services": services}, sort_keys=True, width=200)
    if sleep_mode and any(unit.engine == "vllm" for unit in units):
        return SLEEP_MODE_NOTICE + document
    return document


def _sequence_on_one_card(
    units: tuple[Unit, ...], services: dict[str, dict[str, object]]
) -> None:
    """Order co-resident serving units by making each wait for one ahead.

    For each card, the units that serve on it start together when every one
    of them fixes its own memory (`_fixes_its_memory`): none sizes itself off
    what the others have not yet taken. Otherwise they are sorted largest fit
    first, and every one after the first gets `depends_on` on the one before
    with `condition: service_healthy`; that one gains a healthcheck on its
    port. `services` is modified in place.
    """
    on_card: dict[int, list[tuple[float, str, int]]] = {}
    fixed: dict[int, bool] = {}
    for unit in units:
        if unit.role != ROLE_SERVE:
            continue
        # Only a serve unit answers the `/v1/models` healthcheck the next unit
        # waits on; an rpc worker or a headless rank has no such endpoint.
        if unit.asleep:
            continue
        holds = _fixes_its_memory(
            unit.engine, list(argv(unit)), cast(Mapping[str, object], unit.env)
        )
        for card in unit.cards:
            on_card.setdefault(card, []).append(
                (unit.fit.vram_gb, _service_name(unit), unit.port)
            )
            fixed[card] = fixed.get(card, True) and holds
    for card, sharing in on_card.items():
        if len(sharing) < 2 or fixed[card]:
            continue
        ordered = sorted(sharing, key=lambda triple: (-triple[0], triple[1]))
        for (_, waiter, _), (_, ahead, port) in zip(
            ordered[1:], ordered[:-1], strict=True
        ):
            # Largest fit first: the unit that fits least goes last, so two
            # models on one card are not loading their weights at once.
            waits = services[waiter].setdefault("depends_on", {})
            assert isinstance(waits, dict)
            waits[ahead] = {"condition": "service_healthy"}
            services[ahead]["healthcheck"] = _healthcheck(port)


#: How long a service may take to answer its first healthcheck. Loading a
#: big GGUF's weights off disk takes minutes, and a start period that expired
#: early would mark a service that is merely slow as unhealthy -- and every
#: unit waiting on it, through `depends_on`, would wait for a never-met condition.
_HEALTH_START_PERIOD_S = 600


def _healthcheck(port: int) -> dict[str, object]:
    """A healthcheck that polls the unit's own port for `/v1/models`.

    `curl` is tried first and `wget` second because either may be missing
    from an engine's image; the `||` lives in the shell, so the check passes
    as soon as one of them answers.
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


def _states_fit(parts: Iterable[str], env: Mapping[str, object]) -> bool:
    """Whether a launch states llama.cpp's fitting itself, on or off.

    A `FIT_FLAGS` flag among `parts`, as `flag value` or `flag=value`, or
    `FIT_ENV` in `env` is the unit's own word, and `argv` adds no default
    over it.
    """
    for part in parts:
        if any(part == flag or part.startswith(f"{flag}=") for flag in FIT_FLAGS):
            return True
    return FIT_ENV in env


def _fixes_its_memory(
    engine: object, argv: list[str], env: Mapping[str, object]
) -> bool:
    """Whether a unit takes only the memory its own launch states.

    Such a unit can start at the same moment as the other units on its card:
    the room for all of them was reckoned before they were written, and none
    reads what is free to decide what it takes. That is a llama.cpp unit whose
    launch turns fitting off -- by a `FIT_FLAGS` flag, else by `FIT_ENV`, the
    way llama.cpp reads them. `argv` states it off by default, so an emitted
    llama.cpp unit fixes its memory unless its own flags turn fitting on; a
    locked unit is read from the argv it states. A llama.cpp unit that leaves
    fitting on sizes the arguments it leaves unset off what is free when it
    starts, and a vLLM unit sizes its cache that way, so either waits its turn.
    """
    if engine != "llama.cpp":
        return False
    stated = next(
        (
            value
            for flag in FIT_FLAGS
            if (value := _stated_flag(argv, flag)) is not None
        ),
        None,
    )
    if stated is None:
        said = env.get(FIT_ENV)
        stated = said if isinstance(said, str) else None
    return stated is not None and stated.strip().lower() in FIT_OFF


def _service(unit: Unit, *, sleep_mode: bool = False) -> dict[str, object]:
    """The compose service for one unit, picked by its engine and its role.

    `_check_role` refuses a role its engine has no process for first, then
    the service is built by engine: vLLM by `_vllm_service`, a llama.cpp rpc
    worker by `_rpc_service`, and anything else as a llama.cpp server.
    """
    _check_role(unit)
    if unit.launcher == LAUNCHER_NATIVE:
        return _native_service(unit)
    if unit.engine == "vllm":
        return _vllm_service(unit, sleep_mode=sleep_mode)
    if unit.role == ROLE_RPC:
        return _rpc_service(unit)
    store = _kernel_store(unit)
    return {
        "image": _image(unit),
        "container_name": f"mcgyvr-{safe_host(unit.host)}-{_service_name(unit)}",
        "command": list(argv(unit)),
        # `network_mode: host` is how the served port becomes the host's own:
        # the port is bound by `--port` inside `argv(unit)` above rather than
        # published by a `ports:` mapping, and the box's own address is what a
        # client states. No `entrypoint` is set, so the image runs that argv --
        # the same list `render_command` joins into a shell line, one
        # configuration in two spellings.
        "network_mode": "host",
        # `LLAMA_ARG_HOST=0.0.0.0` makes the server listen on every interface,
        # which under host networking is the box's own; `_environment` merges
        # the unit's env over it and refuses a key that would change the value.
        # The weights are mounted read-only twice, here and at their own path,
        # so a `-m` in the argv resolves against either spelling, beside the
        # rig's kernel store when its scan read one (`_kernel_store`), and
        # `deploy` reserves the card or cards `unit.cards` names.
        "environment": _environment(
            {"LLAMA_ARG_HOST": "0.0.0.0", **(store.env if store else {})}, unit
        ),
        "restart": "unless-stopped",
        "volumes": sorted(
            {
                f"{unit.weights_dir}:{MOUNT}:ro",
                f"{unit.weights_dir}:{unit.weights_dir}:ro",
                *((store.volume,) if store else ()),
            }
        ),
        "deploy": _reservation(*unit.cards),
    }


def _native_service(unit: Unit) -> dict[str, object]:
    """The launch spec of a unit the native launcher runs, in compose's shape.

    No image, no volumes, no devices: the program (`PROGRAM_KEY`) is the
    pinned llama.cpp build's server or rpc worker, run with the same argv a
    container is given, and the cards it may use are listed under
    `CARDS_KEY` (:func:`_native_block`).
    """
    if unit.role == ROLE_SERVE and HOST_FLAG not in unit.args:
        unit = replace(unit, args={**unit.args, HOST_FLAG: LOOPBACK})
    return _native_block(
        unit.key.slug,
        engine=unit.engine,
        host=unit.host,
        rpc=unit.role == ROLE_RPC,
        container=f"mcgyvr-{safe_host(unit.host)}-{_service_name(unit)}",
        command=list(argv(unit)),
        env=dict(unit.env),
        cards=unit.cards,
    )


def _native_block(
    slug: str,
    *,
    engine: str | None,
    host: str,
    rpc: bool,
    container: str,
    command: list[str],
    env: Mapping[str, str],
    cards: Iterable[int],
) -> dict[str, object]:
    """The native launch spec of one process, from an emitted unit or a locked one.

    Only llama.cpp has a native build, and it runs on this machine
    (`LOCAL_RIGS`) or on a rig whose rig file records macOS or Windows (the
    door ships the launcher there): another engine or rig is refused. A
    server listens on
    `LOOPBACK` alone: its `--host` must name it, or it is given it, and a
    `LLAMA_ARG_HOST` or another `--host` is refused.
    """
    if (engine or "llama.cpp") != "llama.cpp":
        raise EmitError(
            f"{slug}: launcher native runs the pinned llama.cpp build, "
            f"and {engine} has none; it runs in its container (launcher docker)"
        )
    if host not in LOCAL_RIGS and not nativerig.remote(host):
        raise EmitError(
            f"{slug}: launcher native runs the unit on the machine mcgyvr runs "
            f"on or on a macOS or Windows rig, and the rig file of {host} records "
            f"neither (`mcgyvr scan --rig {host}` writes it); a unit on a Linux "
            "rig runs in its container (launcher docker)"
        )
    beyond = llamacpp.beyond_loopback(command, dict(env))
    if beyond is not None:
        raise EmitError(f"{slug}: {beyond}")
    if not rpc and not llamacpp.stated_hosts(command):
        command = [*command, HOST_FLAG, LOOPBACK]
    service: dict[str, object] = {
        LAUNCHER_KEY: LAUNCHER_NATIVE,
        PROGRAM_KEY: llamacpp.RPC_SERVER if rpc else llamacpp.SERVER,
        "container_name": container,
        "command": command,
        CARDS_KEY: list(cards),
    }
    if env:
        service["environment"] = dict(env)
    return service


def _rpc_service(unit: Unit) -> dict[str, object]:
    """The compose service of a llama.cpp rpc-server worker.

    The worker holds no model file, so only the rig's kernel store is mounted,
    when its scan read one; `entrypoint` is `RPC_COMMAND` and `command` is the
    unit's flags alone. `environment` and `volumes` are written only when there
    is something in them, since the base here is empty.
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
    store = _kernel_store(unit)
    environment = _environment(dict(store.env) if store else {}, unit)
    if environment:
        service["environment"] = environment
    if store:
        service["volumes"] = [store.volume]
    return service


def _kernel_store(unit: Unit) -> kernelcache.Mount | None:
    """The mount that hands a llama.cpp unit the rig's kernel store, or None.

    A unit whose scan read no mcgyvr home has no store to mount, and its
    service is rendered as it was before there was one; a vLLM unit is never
    handed it here.
    """
    if unit.engine != "llama.cpp" or unit.kernel_cache is None:
        return None
    return kernelcache.mount(unit.kernel_cache)


def _environment(base: dict[str, str], unit: Unit) -> dict[str, str]:
    """`base` with the unit's own env merged over it, refusing a changed key.

    A key the emitted service already sets with a different value means an
    operator's env losing to a default, or the reverse, so it is refused by
    name rather than resolved.
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
    """The compose service of a vLLM unit: cache mount, host ipc, offline hub.

    `HF_HUB_OFFLINE=1` keeps the container off the network for weights --
    the mounted cache is their only source -- and sleep mode adds the
    dev-routes env var so `/sleep` and `/wake_up` exist on the serving port.
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


def _command(unit: Unit) -> tuple[str, ...]:
    _check_role(unit)
    if unit.role == ROLE_RPC:
        return RPC_COMMAND
    command = ENGINE_COMMANDS.get(unit.engine)
    if command is None:
        raise EmitError(
            f"{unit.key.slug}: no command line is known for engine {unit.engine!r}"
        )
    return command


def _check_role(unit: Unit) -> None:
    """Refuse a role its engine has no process for, naming the roles it has.

    `serve` is a process for either engine; llama.cpp's worker is `rpc` and
    vLLM's is `headless`, so any other pairing is caught here, before a
    service is built around it.
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
    """Whether this unit needs a llama.cpp image built with RPC support.

    An rpc worker, or a server whose args carry `--rpc`, needs one; the
    upstream CUDA images are built without it, so `_image` refuses to
    default to them.
    """
    return unit.engine == "llama.cpp" and (
        unit.role == ROLE_RPC or "--rpc" in unit.args
    )


def _image(unit: Unit) -> str:
    if unit.image:
        return unit.image
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
        raise EmitError(
            f"{unit.key.slug}: no container image is known for engine {unit.engine!r}"
        )
    return image


def _service_name(unit: Unit) -> str:
    """The compose service name: sanitised model, port, and the role if it is one.

    `_UNSAFE` folds anything a service name cannot carry to `-`. The port
    is in the name because two units of one model can be rendered together
    and the model alone would name both; a worker or a headless rank
    appends its role so it does not collide with the model's own service.
    """
    name = f"{_UNSAFE.sub('-', unit.model)}-{unit.port}"
    # A role other than `serve` gets its role appended, so the worker and
    # the server of one unit are two services with two names.
    return name if unit.role == ROLE_SERVE else f"{name}-{unit.role}"


def resolved_launch(unit: Unit, *, sleep_mode: bool = False) -> dict[str, Any]:
    """The unit's launch as a record, stamped from the service it renders.

    `engine`, `image` and `container` come out flat; `launch.argv` and
    `launch.env` are the service's command and environment. A vLLM unit
    records its `hf_cache` path, since its weights arrive as a cache mount;
    any other engine records the volume list instead.
    """
    service = _service(unit, sleep_mode=sleep_mode)
    launch: dict[str, Any] = {
        "engine": unit.engine,
        "image": service.get("image"),
        "container": service["container_name"],
        "launch": {
            "argv": list(cast(list[str], service["command"])),
            "env": dict(cast(dict[str, str], service.get("environment") or {})),
        },
    }
    if unit.engine == "vllm":
        launch["hf_cache"] = str(unit.weights_dir)
    else:
        launch["launch"]["volumes"] = list(
            cast(list[str], service.get("volumes") or ())
        )
    return launch


class LockedLaunchError(EmitError):
    """A locked fleet whose units or layout state too little to render."""


def is_locked(fleet: Mapping[str, Any]) -> bool:
    """Whether any unit in the fleet carries a `unit_id`, i.e. states its launch."""
    units = fleet.get("units") or {}
    return any(
        isinstance(block, Mapping) and bool(block.get("unit_id"))
        for block in units.values()
    )


def emit_locked(
    fleet: Mapping[str, Any], root: Path, setup: Path | None = None
) -> tuple[Path, ...]:
    """Write what a locked `fleet.yaml` states into `root`; return the paths.

    `root` is created if missing. `setup` is where the fleet's files live,
    read to find a profile a unit's `launch.seccomp` names. Each planned
    file is written as given: a compose document, or a seccomp profile
    copied under its own name.
    """
    planned = _planned_locked(fleet, root, setup)
    root.mkdir(parents=True, exist_ok=True)
    for path, document in planned:
        path.write_text(document, encoding="utf-8")
    return tuple(path for path, _ in planned)


def check_locked(
    fleet: Mapping[str, Any], root: Path, setup: Path | None = None
) -> tuple[Drift, ...]:
    """The planned locked files whose disk content differs, missing included."""
    return _drifts(_planned_locked(fleet, root, setup))


def planned_locked_paths(
    fleet: Mapping[str, Any], root: Path, setup: Path | None = None
) -> tuple[Path, ...]:
    """The paths `emit_locked` would write, without writing anything."""
    return tuple(path for path, _ in _planned_locked(fleet, root, setup))


def unplanned_locked(
    fleet: Mapping[str, Any], root: Path, setup: Path | None = None
) -> tuple[Path, ...]:
    """Spec files under `root` for the fleet's hosts that it does not plan.

    The hosts are the `layout` keys of every fleet in `fleet.yaml`; files
    there that match one of them and no planned path are returned, sorted.
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
    """The (path, document) pairs a locked fleet renders, plus its profiles.

    `spans` says which rigs and cards each split unit occupies, and
    `check_spans` holds every layout to laying a unit that spans rigs out on
    each of them. A unit split across rigs is its stated head on the head's
    rig and, on each other rig, the rpc-server workers `_locked_workers`
    renders; a worker takes no part in the start order, since it answers no
    healthcheck. A unit with no card on the host it is laid out on is
    refused. Each fleet's layout on each host becomes one document named by
    `spec_name(host, fleet_name)`, whose services start together when every
    one of them fixes its own memory (`_fixes_its_memory`), and otherwise in
    layout order -- each waiting on the healthcheck of the service before it.
    A stated
    seccomp profile is planned as a file of its own, read from `setup` and
    written under its bare file name.
    """
    units = fleet.get("units") or {}
    try:
        found = spans(fleet)
        for fleet_name, block in (fleet.get("fleets") or {}).items():
            check_spans(fleet, block.get("layout") or {}, name=fleet_name)
    except SpanError as exc:
        raise LockedLaunchError(str(exc)) from exc
    planned: list[tuple[Path, str]] = []
    profiles: dict[str, Path] = {}
    workers: dict[str, dict[str, dict[str, dict[str, object]]]] = {}
    for fleet_name, block in sorted((fleet.get("fleets") or {}).items()):
        for host, slots in sorted((block.get("layout") or {}).items()):
            services: dict[str, dict[str, object]] = {}
            # The service names this file gives to workers, mapped to the unit
            # each one lends a card to, so no unit or worker takes another's.
            lent: dict[str, str] = {}
            ahead: tuple[str, int] | None = None
            together = _start_together(units, slots, found, host)
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
                    if name not in workers:
                        workers[name] = _locked_workers(name, unit, span)
                    if host != span.head:
                        for called, worker in workers[name].get(host, {}).items():
                            if called in services:
                                raise LockedLaunchError(
                                    f"{name}: its worker on {host} would be the "
                                    f"compose service {called!r}, which this "
                                    "file already has"
                                )
                            services[called] = worker
                            lent[called] = name
                        continue
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
                if ahead is not None and not together:
                    waited_on, port = ahead
                    service["depends_on"] = {
                        waited_on: {"condition": "service_healthy"}
                    }
                    services[waited_on]["healthcheck"] = _healthcheck(port)
                if name in lent:
                    raise LockedLaunchError(
                        f"{name}: on {host} it would be the compose service "
                        f"{name!r}, which a worker of {lent[name]} already is"
                    )
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


def _start_together(
    units: Mapping[str, Any],
    slots: Iterable[Any],
    found: Mapping[str, Span],
    host: str,
) -> bool:
    """Whether every unit a host's layout serves there fixes its own memory.

    A unit split across rigs is served on its head's rig only; on another rig
    it is workers, which take no part in the start order. A unit fleet.yaml
    does not declare answers False here and is refused by name by the caller.
    """
    for slot in slots:
        unit = units.get(slot[0])
        span = found.get(slot[0])
        if span is not None and len(span.rigs) > 1 and host != span.head:
            continue
        if not isinstance(unit, Mapping):
            return False
        launch = unit.get("launch") or {}
        stated = launch.get("argv") if isinstance(launch, Mapping) else None
        env = launch.get("env") if isinstance(launch, Mapping) else None
        if not _fixes_its_memory(
            unit.get("engine"),
            [str(part) for part in stated] if isinstance(stated, list) else [],
            env if isinstance(env, Mapping) else {},
        ):
            return False
    return True


def _locked_service(
    name: str, unit: Mapping[str, Any], cards: tuple[int, ...] = (0,)
) -> dict[str, object]:
    """The compose service of a unit that states its own launch.

    Everything is taken from the unit's fields and its `launch` block, so a
    unit that states too little is refused before a half service exists: it
    must state `unit_id`, `image` and `container`, a non-empty `launch.argv`
    of strings, a `launch.env` of strings, and -- by engine -- `hf_cache`
    for vLLM or `launch.volumes` for llama.cpp, with `launch.seccomp` a
    file name when it states one at all.
    """
    if unit.get("launcher") == LAUNCHER_NATIVE:
        return _locked_native(name, unit, cards)
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
        # A seccomp profile is named by file name alone: the runtime resolves
        # it next to the compose file being applied. `_planned_locked`
        # therefore copies each stated profile into the output directory under
        # its own name, and refuses two different profiles that would arrive
        # as one -- which is also why any directories in the stated path are
        # dropped here, `Path(seccomp).name` being what the compose file quotes.
        service["security_opt"] = [f"seccomp={Path(seccomp).name}"]
    if engine == "vllm":
        service["ipc"] = "host"
        service["volumes"] = [f"{unit['hf_cache']}:{HF_CACHE_MOUNT}:ro"]
    else:
        service["volumes"] = list(volumes or ())
    return service


def _locked_native(
    name: str, unit: Mapping[str, Any], cards: tuple[int, ...]
) -> dict[str, object]:
    """The native launch spec of a locked unit, from what its lock states.

    The lock carries what the unlocked unit was emitted with: `unit_id`,
    `container`, `launch.argv` and `launch.env`; the cards come from its
    span. It is the same block an unlocked native unit renders
    (:func:`_native_block`), so locking a native fleet does not change how
    it runs.
    """
    launch = unit.get("launch") or {}
    argv = launch.get("argv")
    env = launch.get("env", {})
    missing: list[str] = []
    for key in ("unit_id", "container", "address"):
        if not isinstance(unit.get(key), str) or not unit.get(key):
            missing.append(key)
    if not _strings(argv) or not argv:
        missing.append("launch.argv (a list of strings)")
    if not isinstance(env, Mapping) or not _strings(list(env.values())):
        missing.append("launch.env (a mapping of strings)")
    if missing:
        raise LockedLaunchError(
            f"{name}: a locked unit is rendered from what it states, and it does "
            f"not state {', '.join(missing)}"
        )
    return _native_block(
        name,
        engine=unit.get("engine"),
        host=host_of(str(unit["address"])),
        rpc=False,
        container=str(unit["container"]),
        command=list(cast(list[str], argv)),
        env={str(k): str(v) for k, v in env.items()},
        cards=cards,
    )


#: The shared address space overlay networks hand out (RFC 6598). A worker
#: recorded at one of these is reached only by a head on the same overlay.
OVERLAY = ipaddress.IPv4Network("100.64.0.0/10")


def _locked_workers(
    name: str, unit: Mapping[str, Any], span: Span
) -> dict[str, dict[str, dict[str, object]]]:
    """The rpc-server workers of a locked unit split across rigs, by rig.

    Only llama.cpp splits across rigs as a head plus workers; another engine's
    other ranks state no launch of their own, so it is refused. The unit must
    state what its head renders from (`_locked_service`) and its `model`. The
    workers are the ones the unlocked path starts -- `rpc_workers` over the
    shards off the head's rig, their ports counted from `launch.rpc_port` --
    each rendered by `_rpc_service` under its `_service_name`. The head's
    stated `--rpc` must name exactly those workers, or the head would dial
    workers that are not there, and the unit is refused.
    """
    head = _locked_service(name, unit, span.cards[span.head])
    engine = unit.get("engine")
    if engine != "llama.cpp":
        raise LockedLaunchError(
            f"{name}: spans {', '.join(span.rigs)}, and only a llama.cpp unit is "
            f"rendered across rigs, as a head plus rpc-server workers; a "
            f"{engine} unit's other ranks state no launch of their own"
        )
    model = unit.get("model")
    if not isinstance(model, str) or not model:
        raise LockedLaunchError(
            f"{name}: spans {', '.join(span.rigs)}, and its workers are named "
            "for its model, which it does not state"
        )
    stated_port = (unit.get("launch") or {}).get("rpc_port")
    rpc_port = RPC_DEFAULT_PORT if stated_port is None else stated_port
    if isinstance(rpc_port, bool) or not isinstance(rpc_port, int) or rpc_port < 1:
        raise LockedLaunchError(f"{name}: launch.rpc_port is {rpc_port!r}, not a port")
    targets = tuple(
        Target(
            host=shard.rig,
            gpu=shard.gpu,
            free_bytes=0,
            bind=_worker_bind(name, span, shard),
        )
        for shard in span.shards
        if shard.rig != span.head
    )
    try:
        launched = rpc_workers(targets, model=name, rpc_port=rpc_port)
    except LaunchError as exc:
        raise LockedLaunchError(str(exc)) from exc
    wanted = rpc_endpoints(launched)
    stated = _stated_flag(cast(list[str], head["command"]), "--rpc")
    if stated != wanted:
        raise LockedLaunchError(
            f"{name}: its head's launch.argv states --rpc {stated or '(none)'}, "
            f"and its workers on {', '.join(span.workers)} listen at {wanted}; "
            "the head would dial workers that are not there. Emit the unit "
            "unlocked to stamp its launch again, or state each worker shard's "
            "`bind` as the address the head names"
        )
    out: dict[str, dict[str, dict[str, object]]] = {}
    for process in launched:
        # The rpc writer reads the image, host, model, port, role, args, env
        # and cards; weights, width and fit are sizing figures it never reads,
        # and a locked unit is not sized again.
        worker = Unit(
            key=UnitKey(
                host=process.host, model=model, engine=engine, port=process.port
            ),
            host=process.host,
            model=model,
            engine=engine,
            gpu=process.gpus[0],
            weights=Path(),
            width=Width(value=1, how="default"),
            args=process.args,
            fit=Fit(fits=True, headroom_gb=0.0, why=f"{name}: locked"),
            port=process.port,
            image=str(unit["image"]),
            extra=process.extra,
            gpus=process.gpus,
            role=process.role,
            env=dict(process.env),
        )
        out.setdefault(process.host, {})[_service_name(worker)] = _rpc_service(worker)
    return out


def _worker_bind(name: str, span: Span, shard: Shard) -> str | None:
    """The address a worker shard binds, as `rpc_workers` takes it.

    The shard's own `bind`, then a rig named by its IPv4 address (None here,
    since `rpc_workers` binds the rig name itself), as the unlocked path takes
    them; otherwise the private IPv4 the worker rig's file records. A worker
    rig whose file records none is refused by name, with the file's own
    sentence for why, and so is an overlay address when the head's rig file
    records no address on that overlay: the head would not reach it there.
    """
    if shard.bind is not None:
        return shard.bind
    try:
        ipaddress.IPv4Address(shard.rig)
    except ValueError:
        pass
    else:
        return None
    worker = _rig_file(name, shard.rig)
    address = worker.private_ipv4 if worker is not None else None
    if worker is None or address is None:
        why = (
            worker.private_ipv4_how
            if worker is not None
            else f"there is no rig file for it ({rigfile.path(shard.rig)})"
        )
        raise LockedLaunchError(
            f"{name}: its worker rig {shard.rig} has no recorded address: {why}. "
            f"`{rigfile.MAKE.format(rig=shard.rig)}` records it, or state the "
            "address the head reaches it at as that shard's `bind`"
        )
    if ipaddress.IPv4Address(address) in OVERLAY:
        head = _rig_file(name, span.head)
        if head is None or not _on_overlay(head):
            said = (
                "has no rig file"
                if head is None
                else "records no address on that overlay"
            )
            raise LockedLaunchError(
                f"{name}: its worker rig {shard.rig} records {address} "
                f"({worker.private_ipv4_how}), an address on the {OVERLAY} "
                f"overlay, and its head rig {span.head} {said}, so the head "
                "would not reach the worker there. State the address the head "
                "reaches it at as that shard's `bind`"
            )
    return address


def _rig_file(name: str, rig: str) -> rigfile.Rig | None:
    """The rig file of `rig`, None when it has none, refused when unreadable."""
    try:
        return rigfile.read(rig)
    except rigfile.RigFileError as exc:
        raise LockedLaunchError(f"{name}: rig {rig}: {exc}") from exc


def _on_overlay(rig: rigfile.Rig) -> bool:
    """Whether the rig's file records an address of its own on `OVERLAY`."""
    network = rig.scan.network
    if network is None:
        return False
    said = (network.reached_at, *(one.address for one in network.ipv4))
    for stated in said:
        try:
            if stated is not None and ipaddress.IPv4Address(stated) in OVERLAY:
                return True
        except ValueError:
            continue
    return False


def _stated_flag(argv: list[str], flag: str) -> str | None:
    """The value `argv` gives `flag`, as `flag value` or `flag=value`."""
    for at, part in enumerate(argv):
        if part == flag and at + 1 < len(argv):
            return argv[at + 1]
        if part.startswith(f"{flag}="):
            return part[len(flag) + 1 :]
    return None


def _profile_source(name: str, stated: str, setup: Path | None) -> Path:
    """The file a unit's `launch.seccomp` names, read from the fleet's dir.

    An emit that was not told where the fleet files are cannot read a
    profile, so `setup=None` is refused rather than guessed at, and so is a
    stated path that is not a file.
    """
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
