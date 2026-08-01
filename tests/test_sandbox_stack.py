"""Stack detection runs against a stranger's repository layout, sight unseen.

What matters is that it reads the right signal from the files that are there,
derives an install that matches the package manager the lockfile implies, and
says so explicitly when it cannot — never guesses a stack that fails later at
command time. Every case here builds a layout on disk and asserts the
detection, because the files are the whole input.
"""

from __future__ import annotations

from pathlib import Path

from mcgyvr.sandbox.stack import (
    IMAGE_OVERRIDE_KEY,
    detect_stack,
)


def write(repo: Path, name: str, content: str = "") -> None:
    (repo / name).write_text(content, encoding="utf-8")


# --- python ---------------------------------------------------------------


def test_uv_lock_selects_uv_and_pins(tmp_path: Path) -> None:
    write(tmp_path, "pyproject.toml", "[project]\nname='x'\n")
    write(tmp_path, "uv.lock", "# lock\n")
    stack = detect_stack(tmp_path)
    (component,) = stack.components
    assert component.language == "python"
    assert component.package_manager == "uv"
    assert component.install == ("pip install uv", "uv sync --frozen")
    assert component.pinned is True
    assert stack.base_image == "python:3.12-slim"
    # The lockfile is in the cache-key set — a change to it must rebuild.
    assert "uv.lock" in stack.manifest_paths()


def test_poetry_lock_selects_poetry(tmp_path: Path) -> None:
    write(tmp_path, "pyproject.toml", "[tool.poetry]\nname='x'\n")
    write(tmp_path, "poetry.lock", "")
    (component,) = detect_stack(tmp_path).components
    assert component.package_manager == "poetry"
    assert component.pinned is True


def test_requirements_without_lock_installs_but_is_unpinned(tmp_path: Path) -> None:
    write(tmp_path, "requirements.txt", "flask\n")
    stack = detect_stack(tmp_path)
    (component,) = stack.components
    assert component.package_manager == "pip"
    assert component.install == ("pip install -r requirements.txt",)
    assert component.pinned is False
    # An unpinned stack is surfaced, with the override key to fix it.
    assert any("no lockfile" in note for note in stack.notes)
    assert any(IMAGE_OVERRIDE_KEY in note for note in stack.notes)


def test_tool_only_pyproject_is_not_a_python_stack(tmp_path: Path) -> None:
    """A pyproject that only configures ruff is not an installable project."""
    write(tmp_path, "pyproject.toml", "[tool.ruff]\nline-length=88\n")
    assert detect_stack(tmp_path).detected is False


def test_pyproject_with_project_table_installs_itself(tmp_path: Path) -> None:
    write(tmp_path, "pyproject.toml", "[project]\nname='x'\nversion='0'\n")
    (component,) = detect_stack(tmp_path).components
    assert component.install == ("pip install .",)
    assert component.pinned is False


# --- node -----------------------------------------------------------------


def test_pnpm_lock_selects_pnpm(tmp_path: Path) -> None:
    write(tmp_path, "package.json", '{"name":"x"}')
    write(tmp_path, "pnpm-lock.yaml", "")
    (component,) = detect_stack(tmp_path).components
    assert component.language == "node"
    assert component.package_manager == "pnpm"
    assert "pnpm install --frozen-lockfile" in component.install
    assert component.pinned is True


def test_package_lock_selects_npm_ci(tmp_path: Path) -> None:
    write(tmp_path, "package.json", '{"name":"x"}')
    write(tmp_path, "package-lock.json", "{}")
    (component,) = detect_stack(tmp_path).components
    assert component.install == ("npm ci",)
    assert component.pinned is True


def test_package_json_without_lock_is_unpinned_npm_install(tmp_path: Path) -> None:
    write(tmp_path, "package.json", '{"name":"x"}')
    (component,) = detect_stack(tmp_path).components
    assert component.install == ("npm install",)
    assert component.pinned is False


# --- polyglot and undetectable -------------------------------------------


def test_polyglot_picks_python_base_and_reports_the_rest(tmp_path: Path) -> None:
    write(tmp_path, "pyproject.toml", "[project]\nname='x'\n")
    write(tmp_path, "uv.lock", "")
    write(tmp_path, "package.json", '{"name":"x"}')
    write(tmp_path, "package-lock.json", "{}")
    stack = detect_stack(tmp_path)
    assert {c.language for c in stack.components} == {"python", "node"}
    # First-detected (python) chooses the base; node is still reported.
    assert stack.base_image == "python:3.12-slim"
    assert any("Polyglot" in note for note in stack.notes)
    # Every language's install command is retained for a combined base.
    assert len(stack.install_commands()) == 2


def test_undetectable_stack_is_explicit_with_override(tmp_path: Path) -> None:
    write(tmp_path, "README.md", "# just docs\n")
    stack = detect_stack(tmp_path)
    assert stack.detected is False
    assert stack.base_image is None
    assert stack.manifest_paths() == ()
    # The remedy travels with the failure.
    assert any(IMAGE_OVERRIDE_KEY in note for note in stack.notes)


def test_unreadable_pyproject_does_not_crash_detection(tmp_path: Path) -> None:
    """A malformed manifest is not a stack signal; detection still returns."""
    write(tmp_path, "pyproject.toml", "this is not : valid : toml : [[[")
    write(tmp_path, "package.json", '{"name":"x"}')
    stack = detect_stack(tmp_path)
    # Python manifest was unparseable, so only node is detected — no raise.
    assert {c.language for c in stack.components} == {"node"}
