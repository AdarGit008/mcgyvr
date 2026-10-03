"""Work out what the target repository needs to run its own checks.

A fresh container has none of a project's dependencies, so an acceptance
command fails because an import is missing rather than because the worker was
wrong — and the gate cannot tell those two apart. The answer is to build the
sandbox image with the project's dependencies already installed, which means
knowing, from the repository alone, three things:

1. **which base image** carries the right runtime,
2. **which files define its dependencies** — because a change to exactly
   those, and nothing else, is what should rebuild the image (#29), and
3. **which command installs them.**

Detection is by manifest and lockfile, never by reading code. Two rules
shape it, both inherited from :mod:`mcgyvr.detect`:

- **Absence is an explicit outcome.** A repository whose stack cannot be
  determined produces a :class:`Stack` with no components and a note saying
  so, plus the config key that overrides it — never a silent guess that
  fails later at command time.
- **Every fact carries how it was found.** A base image or install command
  with no provenance is indistinguishable from a default, and a stranger
  whose build it describes has to be able to see why.

The package manager is derived from the lockfile that is present, because the
lockfile is the file whose change must invalidate the image cache. When a
language ships a manifest but no lockfile, the weaker unpinned install is
used and said so.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from mcgyvr.sandbox.declared import (
    ESLINT,
    PRETTIER,
    PYRIGHT,
    declared_type_checker,
    declares_js,
)

# Config keys that override detection, named in every "undetectable" message
# so the remedy travels with the failure.
IMAGE_OVERRIDE_KEY = "sandbox.image"
SETUP_OVERRIDE_KEY = "sandbox.setup"

# Base images are referenced by tag here; the exact digest is resolved and
# frozen when the image is first built (see mcgyvr.sandbox.image).
# Slim images keep the build small; the install step adds the toolchain the
# base omits (uv, poetry, corepack) rather than assuming a fat base.
_PYTHON_BASE = "python:3.12-slim"
_NODE_BASE = "node:22-slim"

#: Where the image's dependency install leaves its environments. The task
#: keeps each one the image populated visible over the workspace's mount
#: (:mod:`mcgyvr.sandbox.docker`), and their tool folders lead the PATH.
WORKSPACE = "/workspace"
VENV = f"{WORKSPACE}/.venv"
NODE_MODULES = f"{WORKSPACE}/node_modules"
TOOL_PATH = f"{VENV}/bin:{NODE_MODULES}/.bin"


@dataclass(frozen=True)
class CheckerInstall:
    """A checker the repository declares, installed into the image if absent.

    ``command`` installs it only when the dependency install did not provide
    it. ``pin`` is the version the repository's lockfile holds for it, or
    ``None`` when nothing pins it and the install is unpinned (said in a note).
    """

    tool: str
    command: str
    pin: str | None


@dataclass(frozen=True)
class StackComponent:
    """One language found in the repository, and how to provision it.

    ``manifests`` are the repository-relative paths whose content defines the
    dependency set. They are the cache key for the image (#29): a change to
    one of them rebuilds, a change to anything else does not. ``install`` is
    the command sequence that installs the dependencies inside the image.
    """

    language: str  # "python" | "node"
    package_manager: str
    manifests: tuple[str, ...]
    install: tuple[str, ...]
    pinned: bool  # whether a lockfile makes the install reproducible
    how: str


@dataclass(frozen=True)
class Stack:
    """What a repository needs to run its checks, or an explicit nothing.

    ``base_image`` is the tag the sandbox image is built ``FROM``. ``notes``
    carry what could not be determined and what to do about it — the same
    contract :class:`mcgyvr.detect.Detection` holds.
    """

    components: tuple[StackComponent, ...]
    base_image: str | None
    notes: tuple[str, ...] = ()
    checkers: tuple[CheckerInstall, ...] = ()

    @property
    def detected(self) -> bool:
        return bool(self.components)

    def manifest_paths(self) -> tuple[str, ...]:
        """Every dependency-defining path, sorted and de-duplicated.

        This is the set whose change invalidates the per-repo image and
        nothing else does (#29). Sorted so the cache key is order-stable.
        """
        seen = {m for c in self.components for m in c.manifests}
        return tuple(sorted(seen))

    def install_commands(self) -> tuple[tuple[str, ...], ...]:
        """The install command of each component, in detection order."""
        return tuple(c.install for c in self.components)

    def checker_commands(self) -> tuple[str, ...]:
        """The command installing each declared checker the install may lack."""
        return tuple(c.command for c in self.checkers)


# Each detector returns a component when its language is present. Ordered so
# that, in a polyglot repository, the first match picks the base image and
# the rest are reported as needing a combined base (see ``detect_stack``).
def _detect_python(repo: Path) -> StackComponent | None:
    def has(name: str) -> bool:
        return (repo / name).is_file()

    pyproject = _read_pyproject(repo)

    if has("uv.lock"):
        return StackComponent(
            "python",
            "uv",
            _present(repo, "pyproject.toml", "uv.lock"),
            ("pip install uv", "uv sync --frozen"),
            pinned=True,
            how="uv.lock present",
        )
    if has("poetry.lock"):
        return StackComponent(
            "python",
            "poetry",
            _present(repo, "pyproject.toml", "poetry.lock"),
            # In the project, so the environment is /workspace/.venv: by
            # default poetry keeps it under root's home, which is off the PATH
            # and unreadable to the task's user.
            (
                "pip install poetry",
                "POETRY_VIRTUALENVS_IN_PROJECT=true "
                "poetry install --no-root --no-interaction",
            ),
            pinned=True,
            how="poetry.lock present",
        )
    if has("Pipfile.lock") or has("Pipfile"):
        return StackComponent(
            "python",
            "pipenv",
            _present(repo, "Pipfile", "Pipfile.lock"),
            ("pip install pipenv", "pipenv install --deploy --system"),
            pinned=has("Pipfile.lock"),
            how="Pipfile.lock present" if has("Pipfile.lock") else "Pipfile present",
        )
    requirements = _requirements_files(repo)
    if requirements:
        primary = requirements[0]
        return StackComponent(
            "python",
            "pip",
            requirements,
            (f"pip install -r {primary}",),
            # A requirements file may or may not be a full lock; treat it as
            # reproducible only when it is the conventional lock name.
            pinned=primary == "requirements.lock",
            how=f"{primary} present",
        )
    if pyproject is not None and _is_python_project(pyproject):
        return StackComponent(
            "python",
            "pip",
            _present(repo, "pyproject.toml"),
            ("pip install .",),
            pinned=False,
            how="pyproject.toml declares a project, no lockfile",
        )
    if has("setup.py") or has("setup.cfg"):
        return StackComponent(
            "python",
            "pip",
            _present(repo, "setup.py", "setup.cfg"),
            ("pip install .",),
            pinned=False,
            how="setup.py/setup.cfg present, no lockfile",
        )
    return None


def _detect_node(repo: Path) -> StackComponent | None:
    if not (repo / "package.json").is_file():
        return None

    def has(name: str) -> bool:
        return (repo / name).is_file()

    manager: str
    install: tuple[str, ...]
    pinned: bool
    lock: str
    if has("pnpm-lock.yaml"):
        manager, install, pinned = (
            "pnpm",
            ("corepack enable", "pnpm install --frozen-lockfile"),
            True,
        )
        lock = "pnpm-lock.yaml"
    elif has("yarn.lock"):
        manager, install, pinned = (
            "yarn",
            ("corepack enable", "yarn install --immutable"),
            True,
        )
        lock = "yarn.lock"
    elif has("bun.lockb"):
        manager, install, pinned = ("bun", ("bun install --frozen-lockfile",), True)
        lock = "bun.lockb"
    elif has("package-lock.json"):
        manager, install, pinned = ("npm", ("npm ci",), True)
        lock = "package-lock.json"
    else:
        # No lockfile: `npm install` resolves fresh, so the build is not
        # reproducible. Said so via ``pinned`` and a note upstream.
        manager, install, pinned = ("npm", ("npm install",), False)
        lock = ""

    manifests = (
        _present(repo, "package.json", lock) if lock else _present(repo, "package.json")
    )
    how = f"package.json with {lock}" if lock else "package.json, no lockfile"
    return StackComponent("node", manager, manifests, install, pinned, how)


def detect_stack(repo: str | Path) -> Stack:
    """Determine what ``repo`` needs to run its checks. Never raises.

    A base image is chosen from the first language detected; a second language
    is still reported, with a note that a combined base image must be supplied
    via config, because a single slim base cannot serve two runtimes and
    guessing one is the failure this module exists to prevent.
    """
    root = Path(repo)
    components = tuple(
        c for c in (_detect_python(root), _detect_node(root)) if c is not None
    )

    if not components:
        return Stack(
            components=(),
            base_image=None,
            notes=(
                "Stack not detected — no Python (pyproject/requirements/"
                "setup) or Node (package.json) manifest was found. The "
                f"sandbox cannot install this repository's dependencies. Set "
                f"`{IMAGE_OVERRIDE_KEY}` to an image that already has them, "
                f"and `{SETUP_OVERRIDE_KEY}` to any build-time commands.",
            ),
        )

    base_image = _PYTHON_BASE if components[0].language == "python" else _NODE_BASE
    notes: list[str] = []
    if not components[0].pinned:
        notes.append(
            f"{components[0].language}: no lockfile — the install resolves "
            f"fresh, so the image is not reproducible and its cache does not "
            f"invalidate when an unpinned dependency releases a new version. "
            f"Commit a lockfile, or pin "
            f"the base with `{IMAGE_OVERRIDE_KEY}`."
        )
    if len(components) > 1:
        others = ", ".join(c.language for c in components[1:])
        notes.append(
            f"Polyglot repository: {components[0].language} chose the base "
            f"image ({base_image}); {others} also detected but a slim base "
            f"serves one runtime. Set `{IMAGE_OVERRIDE_KEY}` to a base that "
            f"carries both — every language's install command is still run."
        )

    checkers: list[CheckerInstall] = []
    for component in components:
        for tool in _declared_for(root, component.language):
            if tool == PYRIGHT:
                notes.append(
                    "pyright: declared, and not installed in the image: its "
                    "PyPI package fetches its Node build on first run, which a "
                    "task container may have no network for. Put it on the "
                    f"image yourself (`{IMAGE_OVERRIDE_KEY}`); until then its "
                    "rung is skipped and said so."
                )
                continue
            pin, source = _pin(root, component, tool)
            checkers.append(
                CheckerInstall(tool, _checker_command(component, tool, pin), pin)
            )
            if pin is None:
                notes.append(
                    f"{tool}: declared, and {source} pins no version of it — "
                    f"installed unpinned where the dependency install does not "
                    f"provide it, so the image is not reproducible in it. Pin "
                    f"it in the lockfile."
                )

    return Stack(
        components=components,
        base_image=base_image,
        notes=tuple(notes),
        checkers=tuple(checkers),
    )


def _declared_for(repo: Path, language: str) -> tuple[str, ...]:
    """The checkers ``repo`` declares that the gate runs over ``language``."""
    if language == "python":
        checker = declared_type_checker(repo)
        return (checker,) if checker is not None else ()
    return tuple(tool for tool in (ESLINT, PRETTIER) if declares_js(repo, tool))


def _checker_command(component: StackComponent, tool: str, pin: str | None) -> str:
    """Install ``tool`` into ``component``'s environment unless it is there."""
    if component.language == "node":
        spec = f"{tool}@{pin}" if pin else tool
        return f"[ -x {NODE_MODULES}/.bin/{tool} ] || npm install --global '{spec}'"
    spec = f"{tool}=={pin}" if pin else tool
    if component.package_manager == "uv":
        return (
            f"[ -x {VENV}/bin/{tool} ] || "
            f"uv pip install --python {VENV}/bin/python '{spec}'"
        )
    if component.package_manager == "poetry":
        return f"[ -x {VENV}/bin/{tool} ] || {VENV}/bin/python -m pip install '{spec}'"
    # pip and pipenv install into the base image's own Python.
    return f"command -v {tool} >/dev/null || pip install '{spec}'"


def _pin(repo: Path, component: StackComponent, tool: str) -> tuple[str | None, str]:
    """The version ``component``'s lockfile pins for ``tool``, and what was read.

    Read as data, never raising: a lockfile that does not parse pins nothing.
    """
    manager = component.package_manager
    if manager in ("uv", "poetry"):
        name = "uv.lock" if manager == "uv" else "poetry.lock"
        return _toml_lock_pin(repo / name, tool), name
    if manager == "pipenv":
        return _pipfile_pin(repo / "Pipfile.lock", tool), "Pipfile.lock"
    if manager == "pip":
        files = [m for m in component.manifests if m.startswith("requirements")]
        return _requirements_pin(repo, files, tool), " or ".join(files) or "no lockfile"
    if manager == "npm" and (repo / "package-lock.json").is_file():
        return _package_lock_pin(repo / "package-lock.json", tool), "package-lock.json"
    return None, component.how


def _toml_lock_pin(path: Path, tool: str) -> str | None:
    try:
        with path.open("rb") as handle:
            packages = tomllib.load(handle).get("package")
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None
    for package in packages if isinstance(packages, list) else ():
        if isinstance(package, dict) and _normal(package.get("name")) == tool:
            version = package.get("version")
            return version if isinstance(version, str) else None
    return None


def _pipfile_pin(path: Path, tool: str) -> str | None:
    lock = _json(path)
    for section in ("default", "develop"):
        entries = lock.get(section) if isinstance(lock, dict) else None
        entry = entries.get(tool) if isinstance(entries, dict) else None
        version = entry.get("version") if isinstance(entry, dict) else None
        if isinstance(version, str) and version.startswith("=="):
            return version[2:]
    return None


def _requirements_pin(repo: Path, files: list[str], tool: str) -> str | None:
    pattern = re.compile(rf"^\s*{re.escape(tool)}\s*==\s*([A-Za-z0-9.+!_-]+)", re.I)
    for name in files:
        try:
            text = (repo / name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            found = pattern.match(line)
            if found:
                return found.group(1)
    return None


def _package_lock_pin(path: Path, tool: str) -> str | None:
    lock = _json(path)
    packages = lock.get("packages") if isinstance(lock, dict) else None
    entry = packages.get(f"node_modules/{tool}") if isinstance(packages, dict) else None
    version = entry.get("version") if isinstance(entry, dict) else None
    return version if isinstance(version, str) else None


def _json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _normal(name: object) -> str:
    """A package name as PyPI compares them: lower case, ``_``/``.`` as ``-``."""
    return re.sub(r"[-_.]+", "-", name).lower() if isinstance(name, str) else ""


def _present(repo: Path, *names: str) -> tuple[str, ...]:
    """The given names that actually exist in ``repo``, order preserved."""
    return tuple(n for n in names if (repo / n).is_file())


def _requirements_files(repo: Path) -> tuple[str, ...]:
    """Requirements files at the repository root, the conventional lock first.

    ``requirements.lock`` (a conventional name for a fully pinned set) is
    treated as the pinned set; a bare ``requirements.txt`` may or may not be
    pinned, so it is installed but not claimed reproducible.
    """
    candidates = ("requirements.lock", "requirements.txt", "requirements-dev.txt")
    return tuple(name for name in candidates if (repo / name).is_file())


def _read_pyproject(repo: Path) -> dict[str, object] | None:
    path = repo / "pyproject.toml"
    if not path.is_file():
        return None
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        # An unreadable manifest is not a stack signal; other detectors still
        # run. A malformed pyproject surfaces from the build, not from here.
        return None


def _is_python_project(pyproject: dict[str, object]) -> bool:
    """Whether a pyproject actually declares a project, not just tool config.

    A repository can carry a ``pyproject.toml`` that only configures ruff or
    black without being a Python package. Requiring a ``[project]`` or
    Poetry table avoids treating tool-only config as an installable stack.
    """
    if "project" in pyproject:
        return True
    tool = pyproject.get("tool")
    return isinstance(tool, dict) and "poetry" in tool
