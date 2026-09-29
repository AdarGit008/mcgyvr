"""The CI test job installs the JavaScript toolchain the suite skips without.

A test that needs the pinned JavaScript toolchain skips where it is not
installed (today ``test_the_javascript_formatter_reads_the_target_as_a_path_too``
in ``tests/test_fix_outcomes_and_argv.py``, which runs only when
``node_modules/.bin/prettier`` exists). That skip is right on a developer's
machine and wrong on the runner that is supposed to hold the property.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_ci_installs_the_js_toolchain_so_the_skip_cannot_become_permanent() -> None:
    """A skip on missing tools must never be the reason the check stops running.

    A check that silently skips everywhere is the same defect as a rung that
    silently passes, one layer out.

    This asserts the **workflow**, not the environment: reading the declaration
    holds the one job that must have the toolchain, from any machine, with
    nothing to install.
    """
    workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    # The job is read up to the next job, so another job's steps cannot stand
    # in for it.
    job = workflow[workflow.index("\n  test:") + 1 :]
    following = re.search(r"\n  [A-Za-z_-]+:\n", job)
    test_job = job[: following.start()] if following else job
    assert "npm ci" in test_job, "the test job must install the pinned toolchain"
    assert "node_modules/.bin" in test_job and "GITHUB_PATH" in test_job, (
        "installing is not enough — `require_tool` resolves linters with "
        "shutil.which, so node_modules/.bin must be exported onto PATH or "
        "eslint and prettier read as not installed"
    )
