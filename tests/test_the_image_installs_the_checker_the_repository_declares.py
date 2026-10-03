"""The task image carries the checker the repository declares, on its PATH.

In docker mode the gate's type checker, eslint and prettier run in the task's
container, so they are found on the image's PATH or their rung is skipped. The
image mcgyvr builds therefore installs, into the environment the dependency
install made, the checker the repository declares: mypy where it configures
mypy, eslint and prettier where it configures them. It installs one only when
the dependency install did not already provide it, at the version the
repository's lockfile pins where it pins one, and unpinned otherwise — said in
a note, as an unpinned dependency install is. The install is part of the
image's cache key. A checker the repository does not declare is not installed:
its rung is skipped and said so, as before.

pyright is the exception, named in a note: its PyPI package fetches its own
Node build on first run, which a task container may have no network for.

The environment's tool folders, ``/workspace/.venv/bin`` and
``/workspace/node_modules/.bin``, lead the image's PATH, so a checker or a
project script installed there is what a command finds.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcgyvr.sandbox.image import cache_key, render_dockerfile
from mcgyvr.sandbox.stack import detect_stack

_BASE = "python:3.12-slim@sha256:pinned"
_UV_LOCK_WITH_MYPY = """version = 1

[[package]]
name = "mypy"
version = "1.13.0"
"""


def _write(repo: Path, name: str, text: str = "") -> None:
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(text, encoding="utf-8")


def _dockerfile(repo: Path) -> str:
    return render_dockerfile(detect_stack(repo), _BASE, ())


def _runs(repo: Path) -> list[str]:
    return [line for line in _dockerfile(repo).splitlines() if line.startswith("RUN ")]


def _uv_repo(repo: Path, lock: str = "version = 1\n") -> Path:
    _write(
        repo,
        "pyproject.toml",
        "[project]\nname = 'x'\n\n[tool.mypy]\nfiles = ['x.py']\n",
    )
    _write(repo, "uv.lock", lock)
    return repo


def test_uv_installs_the_locked_mypy_into_the_project_environment(
    tmp_path: Path,
) -> None:
    repo = _uv_repo(tmp_path, _UV_LOCK_WITH_MYPY)

    runs = _runs(repo)

    install = (
        "RUN [ -x /workspace/.venv/bin/mypy ] || uv pip install "
        "--python /workspace/.venv/bin/python 'mypy==1.13.0'"
    )
    assert install in runs
    assert runs.index(install) > runs.index("RUN pip install uv && uv sync --frozen")
    assert not any("mypy" in note for note in detect_stack(repo).notes)


def test_a_checker_no_lockfile_pins_is_installed_unpinned_and_said_so(
    tmp_path: Path,
) -> None:
    repo = _uv_repo(tmp_path)

    assert (
        "RUN [ -x /workspace/.venv/bin/mypy ] || uv pip install "
        "--python /workspace/.venv/bin/python 'mypy'"
    ) in _runs(repo)
    notes = " ".join(detect_stack(repo).notes)
    assert "mypy" in notes
    assert "unpinned" in notes


def test_a_system_install_gets_the_version_a_requirements_file_pins(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "requirements.txt", "flask==3.0.0\n")
    _write(tmp_path, "requirements-dev.txt", "mypy==1.10.0  # the checker\n")
    _write(tmp_path, "mypy.ini", "[mypy]\nfiles = x.py\n")

    assert "RUN command -v mypy >/dev/null || pip install 'mypy==1.10.0'" in _runs(
        tmp_path
    )


def test_pipenv_gets_the_version_its_lock_pins_in_develop(tmp_path: Path) -> None:
    _write(tmp_path, "Pipfile", "[packages]\n")
    lock = {"default": {}, "develop": {"mypy": {"version": "==1.9.0"}}}
    _write(tmp_path, "Pipfile.lock", json.dumps(lock))
    _write(tmp_path, "setup.cfg", "[mypy]\nfiles = x.py\n")

    assert "RUN command -v mypy >/dev/null || pip install 'mypy==1.9.0'" in _runs(
        tmp_path
    )


def test_poetry_keeps_its_environment_in_the_project_and_the_checker_in_it(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pyproject.toml", "[tool.poetry]\nname = 'x'\n\n[tool.mypy]\n")
    _write(tmp_path, "poetry.lock", '[[package]]\nname = "mypy"\nversion = "1.11.2"\n')

    runs = _runs(tmp_path)

    assert (
        "RUN pip install poetry && POETRY_VIRTUALENVS_IN_PROJECT=true "
        "poetry install --no-root --no-interaction"
    ) in runs
    assert (
        "RUN [ -x /workspace/.venv/bin/mypy ] || "
        "/workspace/.venv/bin/python -m pip install 'mypy==1.11.2'"
    ) in runs


def test_npm_installs_a_declared_eslint_its_lock_does_not_carry(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "package.json", json.dumps({"name": "x"}))
    _write(tmp_path, "package-lock.json", json.dumps({"packages": {}}))
    _write(tmp_path, "eslint.config.mjs", "export default [];\n")

    runs = _runs(tmp_path)

    assert (
        "RUN [ -x /workspace/node_modules/.bin/eslint ] || "
        "npm install --global 'eslint'"
    ) in runs
    assert not any("prettier" in run for run in runs), "prettier is not declared"
    assert "eslint" in " ".join(detect_stack(tmp_path).notes)


def test_npm_gets_the_prettier_its_lock_pins(tmp_path: Path) -> None:
    _write(tmp_path, "package.json", json.dumps({"name": "x", "prettier": {}}))
    lock = {"packages": {"node_modules/prettier": {"version": "3.3.3"}}}
    _write(tmp_path, "package-lock.json", json.dumps(lock))

    assert (
        "RUN [ -x /workspace/node_modules/.bin/prettier ] || "
        "npm install --global 'prettier@3.3.3'"
    ) in _runs(tmp_path)


def test_nothing_declared_installs_nothing(tmp_path: Path) -> None:
    _write(tmp_path, "pyproject.toml", "[project]\nname = 'x'\n")
    _write(tmp_path, "uv.lock", _UV_LOCK_WITH_MYPY)

    assert not any("mypy" in run for run in _runs(tmp_path))


def test_declaring_a_checker_changes_the_image_key(tmp_path: Path) -> None:
    _write(tmp_path, "pyproject.toml", "[project]\nname = 'x'\n")
    _write(tmp_path, "uv.lock", _UV_LOCK_WITH_MYPY)
    before = cache_key(detect_stack(tmp_path), tmp_path, ())

    _write(tmp_path, "mypy.ini", "[mypy]\n")

    assert cache_key(detect_stack(tmp_path), tmp_path, ()) != before


def test_pyright_is_named_and_not_installed(tmp_path: Path) -> None:
    _write(tmp_path, "pyproject.toml", "[project]\nname = 'x'\n\n[tool.pyright]\n")
    _write(tmp_path, "uv.lock", "version = 1\n")

    assert not any("pyright" in run for run in _runs(tmp_path))
    notes = " ".join(detect_stack(tmp_path).notes)
    assert "pyright" in notes
    assert "network" in notes


def test_the_environments_tool_folders_lead_the_path(tmp_path: Path) -> None:
    lines = _dockerfile(_uv_repo(tmp_path)).splitlines()

    path = "ENV PATH=/workspace/.venv/bin:/workspace/node_modules/.bin:$PATH"
    assert path in lines
    assert lines.index(path) < min(
        i for i, line in enumerate(lines) if line.startswith("RUN ")
    )
