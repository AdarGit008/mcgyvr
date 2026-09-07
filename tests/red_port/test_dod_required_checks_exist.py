"""Every status check `main` requires is a check some workflow actually reports.

``.github/rulesets/main.json`` requires two contexts before a pull request may
merge: ``baseline`` and ``test``. ``.github/workflows/ci.yml`` is the only
workflow in the tree and defines one job, ``test``. The baseline job was deleted
("remove the vendored baseline-skill and its CI gate"), and the ruleset was not
followed. ``ci.yml`` still reasons about "the baseline job's Node 20" and
``pyproject.toml`` still justifies a block as "a machine-readable statement of
intent the baseline detects (QUAL-02)".

Only one of two things can be true, and both are bad: either the ruleset in the
repository is not the ruleset in force — in which case the committed file
describes a protection nobody has — or it is in force, and every pull request
waits forever on a check that can never report.

What must be observably true: the set of required contexts is a subset of the
jobs the workflows define. The check is worth having as a test rather than as a
habit because the failure is silent in both directions — a deleted job reports
nothing, and a required context that never arrives looks like a queue.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RULESETS = REPO / ".github" / "rulesets"
WORKFLOWS = REPO / ".github" / "workflows"

#: ``  test:`` at two-space indent under ``jobs:`` — how a job is declared.
JOB = re.compile(r"^  ([A-Za-z0-9_-]+):", re.MULTILINE)

#: ``    name: Full CI`` — the label GitHub actually reports as the check's
#: context when a job sets one. A required context is matched against this,
#: not against the job id, so a workflow can define ``test:`` with a ``name:``
#: and still never report the context the ruleset waits for.
JOB_NAME = re.compile(r"^    name:\s*(.+?)\s*$", re.MULTILINE)


def _required_contexts() -> set[str]:
    found: set[str] = set()
    for ruleset in sorted(RULESETS.glob("*.json")):
        data = json.loads(ruleset.read_text(encoding="utf-8"))
        for rule in data.get("rules", []):
            checks = rule.get("parameters", {}).get("required_status_checks", [])
            for check in checks:
                context = check.get("context")
                if context:
                    found.add(str(context))
    return found


def _reported_contexts() -> set[str]:
    """What the workflows would actually report, ids and declared names alike.

    Both are collected because a required context matches whichever the job
    ends up publishing; requiring only the id would call a workflow sound that
    reports something else entirely.
    """
    contexts: set[str] = set()
    for workflow in sorted(WORKFLOWS.glob("*.y*ml")):
        text = workflow.read_text(encoding="utf-8")
        after = text.partition("\njobs:\n")[2]
        contexts.update(JOB.findall(after))
        contexts.update(name.strip("\"'") for name in JOB_NAME.findall(after))
    return contexts


def test_every_required_check_has_a_job_that_reports_it() -> None:
    """The subset that must hold for a required check to be a check at all."""
    required = _required_contexts()
    assert required, "a ruleset that requires nothing is not the file we mean"
    defined = _reported_contexts()
    missing = sorted(required - defined)
    assert not missing, (
        f"{', '.join(missing)} is required before merge and no workflow job "
        f"reports it; the workflows define {', '.join(sorted(defined))}"
    )


def test_the_prose_does_not_name_a_job_that_is_gone() -> None:
    """The comments that outlived the job, and would mislead the next reader.

    A stale required check is a broken gate. A stale sentence explaining why a
    setting exists is how the gate gets rebuilt wrong.
    """
    stale: list[str] = []
    for path in (
        WORKFLOWS / "ci.yml",
        REPO / "pyproject.toml",
    ):
        if not path.is_file():
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if "baseline" in line and "baseline" not in _reported_contexts():
                stale.append(f"{path.relative_to(REPO)}:{number}: {line.strip()}")
    assert not stale, (
        "prose still explains itself against a deleted job:\n" + "\n".join(stale)
    )
