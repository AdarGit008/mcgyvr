""

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

#
#
#
ENGINE_COMMANDS = {"llama.cpp": ("llama-server",), "vllm": ("vllm", "serve")}
#
#
ALIAS_FLAGS = ("--alias", "-a")
#
#
#
RPC_COMMAND = ("rpc-server",)
ENGINE_IMAGES = {
    "llama.cpp": "ghcr.io/ggml-org/llama.cpp:server-cuda",
    #
    "vllm": "vllm/vllm-openai:v0.26.0",
}

#
#se
#
MOUNT = "/models"

#
#
#
VLLM_SLEEP_FLAG = "--enable-sleep-mode"
VLLM_DEV_ROUTES = "VLLM_SERVER_DEV_MODE"

#
#
SLEEP_MODE_NOTICE = """\
# serving.enable_sleep_wake is on, so every vLLM unit below runs with
# --enable-sleep-mode and VLLM_SERVER_DEV_MODE=1. That registers vLLM's
# development routes on each unit's serving port -- /sleep, /wake_up,
# /is_sleeping, /reset_prefix_cache, /collective_rpc and others -- and they are
# unauthenticated: anyone who can reach the port can put the unit to sleep,
# wake it or reset it. Keep the port reachable only by who should do that.
"""


def sleep_mode(config: Config) -> bool:
    ""
    return bool(config.get("serving.enable_sleep_wake"))


if TYPE_CHECKING:  #
    from mcgyvr.config import Config

#
__all__ = ["COMPOSE_PREFIX", "COMPOSE_SUFFIX", "safe_host", "safe_model"]

#
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class EmitError(Exception):
    ""


def _media_engine_not_wired(unit: Unit) -> str:
    ""
    return (
        f"{unit.key.slug}: engine {unit.engine!r} is not wired in this build; "
        "mcgyvr will not render a unit for an engine it has no launch spec "
        "for rather than emit another engine's flags."
    )


def argv(unit: Unit, *, sleep_mode: bool = False) -> tuple[str, ...]:
    ""
    if unit.engine in MEDIA_ENGINES_NOT_WIRED:
        raise EmitError(_media_engine_not_wired(unit))
    flags = {**unit.args, "--port": str(unit.port)}
    if (
        unit.engine == "llama.cpp"
        and unit.role == ROLE_SERVE
        and not any(flag in ALIAS_FLAGS for flag in (*flags, *unit.extra))
    ):
        flags["--alias"] = unit.model
    #
    #Then
    #
    #
    #
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
    ""
    routes = (f"{VLLM_DEV_ROUTES}=1",) if sleep_mode and unit.engine == "vllm" else ()
    return shlex.join((*routes, *_command(unit), *argv(unit, sleep_mode=sleep_mode)))


def render_compose(unit: Unit | None, *, sleep_mode: bool = False) -> str:
    ""
    if unit is None:
        raise EmitError(
            "no serving unit to render: the host is unscanned, and a launch spec "
            "for a machine nobody measured would be a guess wearing a file name"
        )
    return _document((unit,), sleep_mode=sleep_mode)


def emit_all(
    units: Iterable[Unit], root: Path, *, sleep_mode: bool = False
) -> tuple[Path, ...]:
    ""
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for path, document in _planned(units, root, sleep_mode=sleep_mode):
        path.write_text(document, encoding="utf-8")
        written.append(path)
    return tuple(written)


@dataclass(frozen=True)
class Drift:
    ""

    path: Path
    #
    emitted: str
    #
    found: str | None

    @property
    def missing(self) -> bool:
        return self.found is None

    def diff(self) -> tuple[str, ...]:
        ""
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
    ""
    return _drifts(_planned(units, root, sleep_mode=sleep_mode))


def planned_paths(
    units: Iterable[Unit], root: Path, *, sleep_mode: bool = False
) -> tuple[Path, ...]:
    ""
    return tuple(path for path, _ in _planned(units, root, sleep_mode=sleep_mode))


def unplanned(
    units: Iterable[Unit], root: Path, *, sleep_mode: bool = False
) -> tuple[Path, ...]:
    ""
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
    ""
    planned: list[tuple[Path, str]] = []
    #
    #
    #nd
    #
    #
    #
    #
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
        #
        #
        #
        #
        #
        if path.resolve().parent != root.resolve():
            raise EmitError(f"{spec.host}: would write outside {root}")
        planned.append((path, _document(spec.units, sleep_mode=sleep_mode)))
    return tuple(sorted(planned, key=lambda pair: pair[0].name))


def _document(units: tuple[Unit, ...], *, sleep_mode: bool = False) -> str:
    ""
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
            #
            #
            services[name]["profiles"] = [SLEEPER_PROFILE]
    _sequence_on_one_card(units, services)
    document = yaml.safe_dump({"services": services}, sort_keys=True, width=200)
    if sleep_mode and any(unit.engine == "vllm" for unit in units):
        return SLEEP_MODE_NOTICE + document
    return document


def _sequence_on_one_card(
    units: tuple[Unit, ...], services: dict[str, dict[str, object]]
) -> None:
    ""
    on_card: dict[int, list[tuple[float, str, int]]] = {}
    for unit in units:
        if unit.cpu_only:
            continue
        #
        #
        #
        if unit.role != ROLE_SERVE:
            continue
        #
        #
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
            #
            #
            waits = services[waiter].setdefault("depends_on", {})
            assert isinstance(waits, dict)
            waits[ahead] = {"condition": "service_healthy"}
            services[ahead]["healthcheck"] = _healthcheck(port)


#
#
#
#
_HEALTH_START_PERIOD_S = 600


def _healthcheck(port: int) -> dict[str, object]:
    ""
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
    ""
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
        #
        #
        #
        #he
        #
        #
        "network_mode": "host",
        #
        #ve
        #
        #
        #
        #
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
    ""
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
    ""
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
    ""
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
    ""
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
    ""
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
    ""
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
    ""
    name = f"{_UNSAFE.sub('-', unit.model)}-{unit.port}"
    #
    #
    return name if unit.role == ROLE_SERVE else f"{name}-{unit.role}"


def resolved_launch(unit: Unit, *, sleep_mode: bool = False) -> dict[str, Any]:
    ""
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
    ""


def is_locked(fleet: Mapping[str, Any]) -> bool:
    ""
    units = fleet.get("units") or {}
    return any(
        isinstance(block, Mapping) and bool(block.get("unit_id"))
        for block in units.values()
    )


def emit_locked(
    fleet: Mapping[str, Any], root: Path, setup: Path | None = None
) -> tuple[Path, ...]:
    ""
    planned = _planned_locked(fleet, root, setup)
    root.mkdir(parents=True, exist_ok=True)
    for path, document in planned:
        path.write_text(document, encoding="utf-8")
    return tuple(path for path, _ in planned)


def check_locked(
    fleet: Mapping[str, Any], root: Path, setup: Path | None = None
) -> tuple[Drift, ...]:
    ""
    return _drifts(_planned_locked(fleet, root, setup))


def planned_locked_paths(
    fleet: Mapping[str, Any], root: Path, setup: Path | None = None
) -> tuple[Path, ...]:
    ""
    return tuple(path for path, _ in _planned_locked(fleet, root, setup))


def unplanned_locked(
    fleet: Mapping[str, Any], root: Path, setup: Path | None = None
) -> tuple[Path, ...]:
    ""
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
    ""
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
    ""
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
        #he
        #to
        #
        #
        #
        #
        service["security_opt"] = [f"seccomp={Path(seccomp).name}"]
    if engine == "vllm":
        service["ipc"] = "host"
        service["volumes"] = [f"{unit['hf_cache']}:{HF_CACHE_MOUNT}:ro"]
    else:
        service["volumes"] = list(volumes or ())
    return service


def _profile_source(name: str, stated: str, setup: Path | None) -> Path:
    ""
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
