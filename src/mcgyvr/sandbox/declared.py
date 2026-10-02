"""Which checkers a repository declares, read from its files as data.

One answer for two readers: the gate, which runs the checker a repository
configured (``PythonAdapter.locate_type_check_command``, the JS adapter's
eslint and prettier), and the task image, which installs it
(:mod:`mcgyvr.sandbox.stack`). It lives
here, below the gate, because the sandbox may not import the gate and the gate
may import the sandbox.

Nothing here imports, executes or otherwise evaluates the repository's code.
Reading configuration is the whole of the method; a file that does not parse
is not a declaration, and nothing raises.
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

# The file names each JS tool imports as its configuration: a module, so code.
# The legacy `.eslintrc.js`/`.cjs` is listed because an eslint that still reads
# it runs it.
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

# The data forms of the same configuration, and the `package.json` key each
# tool also reads: a declaration as much as a module is.
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
    """The type checker the gate runs for ``repo``, or ``None``.

    The order mypy appears in before pyright is ARBITRARY and must stay that
    way: mcgyvr does not rank type checkers. A repository configuring both is
    telling us it runs both; this returns one, and a repository that cares
    which declares the command in its contract, which always wins over a sniff.
    """
    if declares_mypy(repo):
        return MYPY
    if declares_pyright(repo):
        return PYRIGHT
    return None


def declares_mypy(repo: Path) -> bool:
    """Whether mypy is configured here, in any of the four places it looks."""
    if has_toml_table(repo / "pyproject.toml", "mypy"):
        return True
    if (repo / "mypy.ini").is_file() or (repo / ".mypy.ini").is_file():
        return True
    # setup.cfg is INI, and a bare substring would match a comment or a
    # `[mypy-somepackage.*]` per-module override in a file that never
    # configures mypy itself. The section header is the declaration.
    return has_ini_section(repo / "setup.cfg", "mypy")


def declares_pyright(repo: Path) -> bool:
    if (repo / "pyrightconfig.json").is_file():
        return True
    return has_toml_table(repo / "pyproject.toml", "pyright")


def declares_js(repo: Path, tool: str) -> bool:
    """Whether ``repo`` configures ``tool`` (eslint or prettier) at its root."""
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
    """Whether ``[tool.<name>]`` is really present — parsed, not grepped.

    A substring test would fire on a comment, on a dependency pin naming the
    tool, or on ``[tool.ruff.lint.mypy-init-return]``. Getting this wrong
    fabricates a type-check command for a repository that runs none.
    """
    if not path.is_file():
        return False
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        # An unparseable manifest is not a declaration. Nothing here raises:
        # a malformed file is the target's business, and the honest answer to
        # "does it declare a checker" is no. `UnicodeDecodeError` is named
        # separately because `tomllib` decodes the bytes itself and answers a
        # non-UTF-8 manifest with that rather than with `TOMLDecodeError` — and
        # it is a `ValueError`, which neither of the other two catches.
        return False
    tool = document.get("tool")
    return isinstance(tool, dict) and isinstance(tool.get(name), dict)


def has_ini_section(path: Path, name: str) -> bool:
    """Whether an INI file carries a ``[name]`` section, parsed as INI."""
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
