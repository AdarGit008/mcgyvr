"""Render serving units into launch artifacts, and compare them with disk.

A unit is rendered two ways that must agree: a compose document under
``services:`` -- written by `emit_all`, compared by `check_all`, named by
`spec_name` -- and a bare command line (`render_command`) for an operator
who starts the process by hand. Nothing here starts anything: emitting is
writing a file, and the rig's operator runs it.

A second family renders a ``fleet.yaml`` whose units state their own
launch -- image, container, argv, env, a "locked" unit: `emit_locked`
writes those documents, `check_locked` compares them, and both refuse a
unit that states too little to render.

Every refusal is an `EmitError`: an engine this build cannot render (see
`MEDIA_ENGINES_NOT_WIRED`), an argument the compose file and the shell
command cannot spell the same way, a file name two units would both
claim, or a path that resolves outside the output directory.
"""

from __future__ import annotations

import difflib
import re
import shlex
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

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
    SLEEPER_PROFILE,
    Unit,
    launch_specs,
    port_of,
    safe_host,
    safe_model,
    spec_files,
    spec_name,
)

# The shell command that starts each engine's own server, for the engines
# that have one: a media engine's server is its image's entrypoint, so
# `_command` refuses it rather than inventing a command line.
ENGINE_COMMANDS = {"llama.cpp": ("llama-server",), "vllm": ("vllm", "serve")}
# The flags llama.cpp spells a served model's name with. `argv` adds
# `--alias` only for a serve unit of that engine that carries none already.
ALIAS_FLAGS = ("--alias", "-a")
# The command of a llama.cpp rpc-server worker: one process of a model
# split across rigs, which serves no model of its own. `_rpc_service` also
# makes it the service's entrypoint, so the image's own one does not run.
RPC_COMMAND = ("rpc-server",)
ENGINE_IMAGES = {
    "llama.cpp": "ghcr.io/ggml-org/llama.cpp:server-cuda",
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


def _media_engine_not_wired(unit: Unit) -> str:
    """The refusal for an engine listed in `MEDIA_ENGINES_NOT_WIRED`."""
    return (
        f"{unit.key.slug}: engine {unit.engine!r} is not wired in this build; "
        "mcgyvr will not render a unit for an engine it has no launch spec "
        "for rather than emit another engine's flags."
    )


def argv(unit: Unit, *, sleep_mode: bool = False) -> tuple[str, ...]:
    """The argv of the process that serves `unit`, in one canonical order.

    vLLM takes its model as a positional argument, so the model leads. The
    unit's flags follow sorted by name, `--port` among them and `--alias`
    added for a serve unit that carries none of `ALIAS_FLAGS`; the sleep
    flag comes next, and the unit's `extra` parts are appended as written.
    A part containing whitespace is refused: the compose `command` and the
    shell command could not spell it the same way.
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
    for part in parts:
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
    starts only one of them. Units sharing a card are put in start order by
    `_sequence_on_one_card`, and the dump sorts keys and widens lines so the
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

    For each card, the units that serve on it are sorted largest fit first,
    and every one after the first gets `depends_on` on the one before with
    `condition: service_healthy`; that one gains a healthcheck on its port.
    `services` is modified in place.
    """
    on_card: dict[int, list[tuple[float, str, int]]] = {}
    for unit in units:
        if unit.cpu_only:
            continue
        # A `cpu_only` unit stands on no card, so it has nothing to queue
        # behind; skipping it keeps its `gpu` index (often 0) from reading as
        # a card it shares.
        if unit.role != ROLE_SERVE:
            continue
        # Only a serve unit answers the `/v1/models` healthcheck the next unit
        # waits on; an rpc worker or a headless rank has no such endpoint.
        if unit.asleep:
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


def _service(unit: Unit, *, sleep_mode: bool = False) -> dict[str, object]:
    """The compose service for one unit, picked by its engine and its role.

    `_check_role` refuses a role its engine has no process for first, then
    the service is built by engine: vLLM by `_vllm_service`, a media engine
    by `_media_service`, a llama.cpp rpc worker by `_rpc_service`, and
    anything else as a llama.cpp server.
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
        # so a `-m` in the argv resolves against either spelling, and `deploy`
        # reserves the card or cards `unit.cards` names.
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
    """The compose service of a llama.cpp rpc-server worker.

    The worker holds no model file, so nothing is mounted; `entrypoint` is
    `RPC_COMMAND` and `command` is the unit's flags alone. `environment` is
    written only when the unit states env, since the base here is empty.
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


def _media_service(unit: Unit) -> dict[str, object]:
    """The compose service of a media engine unit, built from what it states.

    A media engine has no default image here, so the unit's own `image` is
    required; the weights are mounted read-only at their own path, and only
    a unit that holds a card reserves one.
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
        "image": service["image"],
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

    `spans` says which rigs and cards each split unit occupies. A unit
    whose shards span rigs is refused: a locked launch states one argv, its
    head's, and rendering it on a worker rig would make a second head. A
    unit with no card on the host it is laid out on is refused too. Each
    fleet's layout on each host becomes one document named by
    `spec_name(host, fleet_name)`, with services started in layout order --
    each waiting on the healthcheck of the service before it. A stated
    seccomp profile is planned as a file of its own, read from `setup` and
    written under its bare file name.
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
    """The compose service of a unit that states its own launch.

    Everything is taken from the unit's fields and its `launch` block, so a
    unit that states too little is refused before a half service exists: it
    must state `unit_id`, `image` and `container`, a non-empty `launch.argv`
    of strings, a `launch.env` of strings, and -- by engine -- `hf_cache`
    for vLLM or `launch.volumes` for llama.cpp, with `launch.seccomp` a
    file name when it states one at all.
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
