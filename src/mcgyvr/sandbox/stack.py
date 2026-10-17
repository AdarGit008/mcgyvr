"""Detect a repository's language stack and turn it into sandbox build inputs.

`detect_stack` reads the repository root for Python manifests (`pyproject.toml`,
the requirement files `requirements.lock`, `requirements.txt` and
`requirements-dev.txt`, `setup.py`, `setup.cfg`, `Pipfile`, and the lockfiles
`uv.lock` and `poetry.lock`) and for a Node `package.json` with a lockfile, and
returns a `Stack`.

A `Stack` holds one `StackComponent` per detected language - its package
manager, the manifests that were found, the install commands, and whether a
lockfile pins versions - plus the base image the sandbox builds from (a slim
Python image when Python was detected first, a slim Node image otherwise,
`None` when nothing was detected), the prose `notes` collected on the way, and
a `CheckerInstall` for every declared checker (mypy, pyright, eslint, prettier)
the image can install, with its version read out of the ecosystem's lockfile.
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

# Config keys a repository can set to override the detected image and to add
# build-time commands; this module only interpolates their names into notes.
IMAGE_OVERRIDE_KEY = "sandbox.image"
SETUP_OVERRIDE_KEY = "sandbox.setup"

# Base images the sandbox builds from, chosen by the first detected language.
# Both are slim, so a non-default package manager (uv, poetry, pipenv, pnpm,
# yarn, bun) has to be brought in by the component's own install commands,
# which is what those commands do before installing dependencies.
_PYTHON_BASE = "python:3.12-slim"
_NODE_BASE = "node:22-slim"

#: Paths inside the task image: the repository is mounted at `WORKSPACE`,
#: dependencies land in `VENV` (Python) or `NODE_MODULES` (Node), and
#: `TOOL_PATH` is prepended to PATH so a checker installed into either is
#: found by name.
WORKSPACE = "/workspace"
VENV = f"{WORKSPACE}/.venv"
NODE_MODULES = f"{WORKSPACE}/node_modules"
TOOL_PATH = f"{VENV}/bin:{NODE_MODULES}/.bin"


@dataclass(frozen=True)
class CheckerInstall:
    """One checker the image installs.

    `command` installs `tool` only when its binary is not already there, and
    `pin` is the version the repository's lockfile fixes, or `None` when
    nothing pinning it was found.
    """

    tool: str
    command: str
    pin: str | None


@dataclass(frozen=True)
class StackComponent:
    """One detected language and how to install its dependencies.

    `manifests` are the files the install reads; they are copied into the
    image and hashed into its cache key. `install` is the command sequence to
    run, `pinned` says whether a lockfile fixes the versions, and `how` is the
    phrase detection reports its decision with.
    """

    language: str  # "python" or "node"
    package_manager: str
    manifests: tuple[str, ...]
    install: tuple[str, ...]
    pinned: bool  # a lockfile fixes the dependency versions
    how: str


@dataclass(frozen=True)
class Stack:
    """What was detected for one repository, i.e. what the image is built from.

    `components` is empty when nothing was detected, and `base_image` is then
    `None`; otherwise the first component chose `base_image`. `notes` holds the
    prose warnings gathered along the way, and `checkers` the tools to install
    on top of the dependencies.
    """

    components: tuple[StackComponent, ...]
    base_image: str | None
    notes: tuple[str, ...] = ()
    checkers: tuple[CheckerInstall, ...] = ()

    @property
    def detected(self) -> bool:
        return bool(self.components)

    def manifest_paths(self) -> tuple[str, ...]:
        """Every manifest the components read, deduplicated and sorted.

        The image cache key hashes these files and the Dockerfile copies them
        in before running the installs.
        """
        seen = {m for c in self.components for m in c.manifests}
        return tuple(sorted(seen))

    def install_commands(self) -> tuple[tuple[str, ...], ...]:
        """Each component's install command sequence, in component order.

        The first component's sequence runs first, and the image joins each
        sequence into one shell step.
        """
        return tuple(c.install for c in self.components)

    def checker_commands(self) -> tuple[str, ...]:
        """The install command of each entry in `checkers`, in order."""
        return tuple(c.command for c in self.checkers)


# Python detection, tried before Node: it prefers the managers whose lockfile
# pins versions, then bare requirement lists, then a pyproject or setup file,
# and returns None when no Python manifest is present at all.
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
            # `POETRY_VIRTUALENVS_IN_PROJECT` puts the venv at `VENV`
            # (`/workspace/.venv`), which is where the checker commands probe for
            # a binary; `--no-root` installs the dependencies only.
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
            # Only `requirements.lock` counts as pinned: the other requirement
            # files are plain lists whose versions can move at install time.
            pinned=primary == "requirements.lock",
            how=f"{primary} present",
        )
    if pyproject is not None and _is_python_project(pyproject):
        how = "pyproject.toml declares a project, no lockfile"
        if not _has_dev_group(pyproject):
            return StackComponent(
                "python",
                "pip",
                _present(repo, "pyproject.toml"),
                ("pip install .",),
                pinned=False,
                how=how,
            )
        # A dev group is installed with `pip install --group`, a flag that pip
        # only gained in 25.1 (PEP 735 `[dependency-groups]`); pip is upgraded
        # first so the flag exists by the time the install runs).
        # A pyproject without a dev group takes the `pip install .` branch above.
        return StackComponent(
            "python",
            "pip",
            _present(repo, "pyproject.toml"),
            ("pip install --upgrade 'pip>=25.1'", "pip install . --group dev"),
            pinned=False,
            how=f"{how}; dev group installed",
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
        # No lockfile: `npm install` resolves versions fresh, so the component
        # is unpinned and there is no lockfile to copy or to read a pin from.
        manager, install, pinned = ("npm", ("npm install",), False)
        lock = ""

    manifests = (
        _present(repo, "package.json", lock) if lock else _present(repo, "package.json")
    )
    how = f"package.json with {lock}" if lock else "package.json, no lockfile"
    return StackComponent("node", manager, manifests, install, pinned, how)


def detect_stack(repo: str | Path) -> Stack:
    """Detect the stack of the repository at `repo`.

    Python and Node are probed in that order. With no manifest at all the
    result is empty and a single note names the two config keys a caller can
    set to supply an image and setup commands anyway. Otherwise the first
    component chooses the base image, an unpinned first component and a
    polyglot repository each add a note, and every declared checker becomes a
    `CheckerInstall` pinned from the lockfile, with a note when the lockfile
    pins the tool to no version - except pyright, which is skipped with a note
    because its package fetches a Node build over the network on first run.
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
    """The checkers `repo` declares configuration for, for one detected language.

    Python yields its type checker (mypy when declared, else pyright) or
    nothing; any other language yields eslint and prettier, each only if the
    repository configures it.
    """
    if language == "python":
        checker = declared_type_checker(repo)
        return (checker,) if checker is not None else ()
    return tuple(tool for tool in (ESLINT, PRETTIER) if declares_js(repo, tool))


def _checker_command(component: StackComponent, tool: str, pin: str | None) -> str:
    """The shell command that installs `tool` at `pin` for `component`.

    Every command is a guard plus an install, so the install runs only when
    the guard's check fails. Node checkers are guarded on a binary in
    `NODE_MODULES/.bin` and installed with `npm install --global`; uv and
    poetry checkers are guarded on `VENV/bin` and installed into that venv;
    any other manager's checker is installed with plain pip into the
    interpreter on PATH.
    """
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
    # pip, pipenv (--system) and any other manager install into the python on PATH.
    return f"command -v {tool} >/dev/null || pip install '{spec}'"


def _pin(repo: Path, component: StackComponent, tool: str) -> tuple[str | None, str]:
    """The version of `tool` that `component`'s lockfile pins, and a label.

    The label names the file the pin was read from, or `component.how` when
    the manager's lockfile format has no reader here. The version is `None`
    when that file does not list the tool or cannot be read.
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
    """`name` normalised for comparing a lockfile entry with a tool name.

    Runs of `-`, `_` and `.` collapse to one `-` and the result is
    lowercased; anything that is not a string gives the empty string.
    """
    return re.sub(r"[-_.]+", "-", name).lower() if isinstance(name, str) else ""


def _present(repo: Path, *names: str) -> tuple[str, ...]:
    """The subset of `names` that exist as files in `repo`, in the given order."""
    return tuple(n for n in names if (repo / n).is_file())


def _requirements_files(repo: Path) -> tuple[str, ...]:
    """The requirement files present in `repo`, in candidate order.

    The lock file is preferred over the plain and the dev requirement lists.
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
        # An unreadable or malformed `pyproject.toml` counts as absent, so
        # detection falls through to the other Python manifests, if any.
        return None


def _has_dev_group(pyproject: dict[str, object]) -> bool:
    """True when `pyproject.toml` declares a `[dependency-groups]` table whose
    `dev` entry is a non-empty list."""
    groups = pyproject.get("dependency-groups")
    if not isinstance(groups, dict):
        return False
    dev = groups.get("dev")
    return isinstance(dev, list) and bool(dev)


def _is_python_project(pyproject: dict[str, object]) -> bool:
    """True when `pyproject.toml` has a `[project]` or a `[tool.poetry]` table,
    i.e. the file declares an installable project."""
    if "project" in pyproject:
        return True
    tool = pyproject.get("tool")
    return isinstance(tool, dict) and "poetry" in tool
