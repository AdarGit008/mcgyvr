"""Answer which checker a repository declares, by reading files only.

Every probe here is a static read of the repository root: file names, TOML
tables in ``pyproject.toml``, INI sections in ``setup.cfg``, and keys in
``package.json``. Nothing is imported, evaluated, or spawned, so a repository
whose own modules would explode on import still reports its declaration, and
the answer never depends on what is installed on the host.
"""

from __future__ import annotations

import configparser
import json
import tomllib
from pathlib import Path

MYPY = "mypy"
PYRIGHT = "pyright"
ESLINT = "eslint"
PRETTIER = "prettier"

# Suffixes of a JavaScript/TypeScript module. A config file with one of these
# is a program the tool imports, so these names are kept apart from the
# data-format config files below and grouped per tool in CONFIG_MODULES.
_MODULE_SUFFIXES = (".js", ".cjs", ".mjs", ".ts", ".cts", ".mts")
CONFIG_MODULES = {
    ESLINT: frozenset(
        {f"eslint.config{suffix}" for suffix in _MODULE_SUFFIXES}
        | {".eslintrc.js", ".eslintrc.cjs"}
    ),
    PRETTIER: frozenset(
        {f"prettier.config{suffix}" for suffix in _MODULE_SUFFIXES}
        | {f".prettierrc{suffix}" for suffix in _MODULE_SUFFIXES}
    ),
}

# Config files the tool parses as data rather than importing, plus the
# package.json key that carries the same settings inline in _PACKAGE_KEYS.
_CONFIG_DATA = {
    ESLINT: frozenset(
        {".eslintrc", ".eslintrc.json", ".eslintrc.yaml", ".eslintrc.yml"}
    ),
    PRETTIER: frozenset(
        {
            ".prettierrc",
            ".prettierrc.json",
            ".prettierrc.json5",
            ".prettierrc.yaml",
            ".prettierrc.yml",
            ".prettierrc.toml",
        }
    ),
}
_PACKAGE_KEYS = {ESLINT: "eslintConfig", PRETTIER: "prettier"}


def declared_type_checker(repo: Path) -> str | None:
    """The type checker the gate runs for `repo`, or None when it declares none.

    The order mypy is checked before pyright is arbitrary, not a ranking: mcgyvr
    does not rank type checkers. A repository that cares which one to run
    declares the command in its contract, which always wins over a sniff.
    """
    if declares_mypy(repo):
        return MYPY
    if declares_pyright(repo):
        return PYRIGHT
    return None


def declares_mypy(repo: Path) -> bool:
    """Whether mypy is declared by pyproject.toml, an ini file, or setup.cfg."""
    if has_toml_table(repo / "pyproject.toml", "mypy"):
        return True
    if (repo / "mypy.ini").is_file() or (repo / ".mypy.ini").is_file():
        return True
    # setup.cfg is INI rather than TOML, so the same declaration appears there
    # as a [mypy] section instead of a [tool.mypy] table. Bare presence of the
    # file is not enough: a setup.cfg without that section declares no checker.
    return has_ini_section(repo / "setup.cfg", "mypy")


def declares_pyright(repo: Path) -> bool:
    if (repo / "pyrightconfig.json").is_file():
        return True
    return has_toml_table(repo / "pyproject.toml", "pyright")


def declares_js(repo: Path, tool: str) -> bool:
    """Whether the repository configures `tool` (eslint or prettier).

    The dedicated config files are checked first, in both their module and
    data-format spellings; failing those, the tool's key inside package.json.
    """
    names = CONFIG_MODULES[tool] | _CONFIG_DATA[tool]
    if any((repo / name).is_file() for name in names):
        return True
    package = repo / "package.json"
    if not package.is_file():
        return False
    try:
        manifest = json.loads(package.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    return isinstance(manifest, dict) and _PACKAGE_KEYS[tool] in manifest


def has_toml_table(path: Path, name: str) -> bool:
    """Whether `path` is a readable TOML file holding a [tool.<name>] table."""
    if not path.is_file():
        return False
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        # A manifest that cannot be read, decoded, or parsed declares nothing.
        # A broken pyproject.toml is a pre-existing property of the target, not
        # of the probe, so it is answered in the negative here rather than
        # raised: locating a command must not fail because the repository is
        # malformed, and the table lookup below only ever sees a real document.
        return False
    tool = document.get("tool")
    return isinstance(tool, dict) and isinstance(tool.get(name), dict)


def has_ini_section(path: Path, name: str) -> bool:
    """Whether `path` is an INI file with a section named `name`.

    A file that cannot be read or parsed is treated as having no such section.
    """
    if not path.is_file():
        return False
    parser = configparser.ConfigParser()
    try:
        parser.read_string(_read_or_empty(path))
    except configparser.Error:
        return False
    return parser.has_section(name)


def _read_or_empty(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError:
        return ""
