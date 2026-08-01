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

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

# Config keys that override detection, named in every "undetectable" message
# so the remedy travels with the failure.
IMAGE_OVERRIDE_KEY = "sandbox.image"
SETUP_OVERRIDE_KEY = "sandbox.setup"

# Base images are referenced by tag here; the exact digest is resolved and
# frozen when the image is first built (REPRO-04, see mcgyvr.sandbox.image).
# Slim images keep the build small; the install step adds the toolchain the
# base omits (uv, poetry, corepack) rather than assuming a fat base.
_PYTHON_BASE = "python:3.12-slim"
_NODE_BASE = "node:22-slim"


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

    @property
    def fully_pinned(self) -> bool:
        """Whether every component installs from a lockfile."""
        return all(c.pinned for c in self.components)


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
            ("pip install poetry", "poetry install --no-root --no-interaction"),
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
            f"fresh, so the image is not reproducible and its cache never "
            f"invalidates on a dependency change. Commit a lockfile, or pin "
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

    return Stack(components=components, base_image=base_image, notes=tuple(notes))


def _present(repo: Path, *names: str) -> tuple[str, ...]:
    """The given names that actually exist in ``repo``, order preserved."""
    return tuple(n for n in names if (repo / n).is_file())


def _requirements_files(repo: Path) -> tuple[str, ...]:
    """Requirements files at the repository root, the conventional lock first.

    ``requirements.lock`` (pip-tools' output) is treated as the pinned set;
    a bare ``requirements.txt`` may or may not be pinned, so it is installed
    but not claimed reproducible.
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


def base_image_for(languages: Sequence[str]) -> str | None:
    """The slim base image for a single detected language, else None.

    Exposed for callers that have already narrowed the language set (the
    image builder) and want the same mapping detection used.
    """
    if "python" in languages:
        return _PYTHON_BASE
    if "node" in languages:
        return _NODE_BASE
    return None
