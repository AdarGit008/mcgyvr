""

from __future__ import annotations

import configparser
import json
import tomllib
from pathlib import Path

MYPY = "mypy"
PYRIGHT = "pyright"
ESLINT = "eslint"
PRETTIER = "prettier"

#
#
#
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

#
#
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
    ""
    if declares_mypy(repo):
        return MYPY
    if declares_pyright(repo):
        return PYRIGHT
    return None


def declares_mypy(repo: Path) -> bool:
    ""
    if has_toml_table(repo / "pyproject.toml", "mypy"):
        return True
    if (repo / "mypy.ini").is_file() or (repo / ".mypy.ini").is_file():
        return True
    #
    #
    #
    return has_ini_section(repo / "setup.cfg", "mypy")


def declares_pyright(repo: Path) -> bool:
    if (repo / "pyrightconfig.json").is_file():
        return True
    return has_toml_table(repo / "pyproject.toml", "pyright")


def declares_js(repo: Path, tool: str) -> bool:
    ""
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
    ""
    if not path.is_file():
        return False
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        #
        #
        #
        #
        #nd
        #
        return False
    tool = document.get("tool")
    return isinstance(tool, dict) and isinstance(tool.get(name), dict)


def has_ini_section(path: Path, name: str) -> bool:
    ""
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
