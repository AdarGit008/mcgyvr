"""The release workflow runs only scripts the product holds.

A release is built from this repository by its release workflow, and every
script that workflow runs has to be part of the product: a script kept
anywhere else could leave the repository and take the release with it. The
product keeps the scripts its release runs under ``scripts/``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
RELEASE = REPO / ".github" / "workflows" / "release.yml"

#: A script a run line hands to an interpreter, spelled as a repository path.
SCRIPT = re.compile(r"(?<![\w/.-])([\w.-]+(?:/[\w.-]+)*\.py)\b")


def _run_lines() -> list[str]:
    loaded: dict[Any, Any] = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
    lines: list[str] = []
    for job in loaded["jobs"].values():
        for step in job.get("steps", []):
            if isinstance(step, dict) and "run" in step:
                lines.append(str(step["run"]))
    return lines


def test_the_release_workflow_runs_only_scripts_the_product_holds() -> None:
    scripts = sorted({m for line in _run_lines() for m in SCRIPT.findall(line)})
    assert scripts, "the release workflow runs no script at all"
    outside = [s for s in scripts if Path(s).parts[0] != "scripts"]
    assert outside == [], f"the release runs scripts outside scripts/: {outside}"
    missing = [s for s in scripts if not (REPO / s).is_file()]
    assert missing == [], f"the release runs scripts that do not exist: {missing}"
