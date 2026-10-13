"""The README clones the skill at the tag of the CLI it just installed.

The skill is rendered from the schema at the revision it is cloned from; the
CLI from PyPI is the latest release. The e2e run's F1 is the two drifting
apart: the README installed 0.4.16 and cloned `main`, whose skill taught a
`task_type: code` no release yet accepted. So the PyPI path clones the tag
the installed CLI names, read from ``mcgyvr --version``, and only the path
that installs the CLI from `main` clones `main`.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import mcgyvr
from tests._paths import REPO

README = REPO / "README.md"

#: The clone that follows the CLI: its tag is computed, not written down.
_DERIVED_BRANCH = re.compile(r'--branch "(v\$\([^"]*\))"')


def _install_section() -> str:
    text = README.read_text(encoding="utf-8")
    start = text.index("## Install\n")
    end = text.index("\n## ", start + 1)
    return text[start:end]


def _clone_lines() -> list[str]:
    return [ln for ln in _install_section().splitlines() if ln.startswith("git clone ")]


def _tag_expression() -> str:
    derived = [m.group(1) for ln in _clone_lines() if (m := _DERIVED_BRANCH.search(ln))]
    assert len(derived) == 1, _clone_lines()
    return derived[0]


def _expand(expression: str, path: str) -> str:
    """What the README's ``--branch`` argument expands to under ``path``."""
    ran = subprocess.run(
        ["bash", "-c", f'printf %s "{expression}"'],
        env={**os.environ, "PATH": path},
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return ran.stdout


def test_the_skill_clone_names_the_tag_of_the_installed_cli() -> None:
    """Expanded against the CLI built from this checkout, whose ``--version``
    is the real one: the version line first, then the config line."""
    venv_bin = Path(sys.executable).parent
    assert (venv_bin / "mcgyvr").exists(), venv_bin
    path = f"{venv_bin}{os.pathsep}{os.environ.get('PATH', '')}"

    assert _expand(_tag_expression(), path) == f"v{mcgyvr.__version__}"


def test_the_skill_clone_names_a_release_tag_for_a_released_cli(
    tmp_path: Path,
) -> None:
    shim = tmp_path / "mcgyvr"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        'echo "mcgyvr 0.5.0"\n'
        'echo "config: /home/someone/.mcgyvr/fleets/x@2026-10-12"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    path = f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"

    assert _expand(_tag_expression(), path) == "v0.5.0"


def test_only_the_cli_from_main_is_paired_with_a_clone_of_main() -> None:
    """Exactly one clone has no ``--branch``, and the text leading up to it
    is the one that names installing the CLI from the repository."""
    bare = [ln for ln in _clone_lines() if "--branch" not in ln]
    assert len(bare) == 1, _clone_lines()
    section = _install_section()
    at = section.index(bare[0])
    lead_in = section[section.rindex("```", 0, at - len("```sh\n")) : at]
    assert "uv tool install git+" in lead_in, lead_in
