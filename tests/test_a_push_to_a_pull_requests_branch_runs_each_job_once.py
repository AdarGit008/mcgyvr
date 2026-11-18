"""A push to a pull request's branch runs each CI job once, as the pull request.

Each push to an open pull request's branch starts the workflows' ``pull_request``
jobs. A ``push`` trigger that matched that branch too would start every job a
second time, as ``(push)``, on the same commit: the same check twice, and only
``ci / test (pull_request)`` is the one a merge waits for. So a workflow that
runs on pull requests runs a push on ``main`` only. The push run on main stays:
it is what says main itself is green.

``release.yml`` runs no pull request and keeps its own tag trigger; it is not
held here.
"""

from __future__ import annotations

from typing import Any

import yaml

from tests._paths import REPO

WORKFLOWS = REPO / ".github" / "workflows"

#: The events that run a workflow on a pull request.
PR_EVENTS = ("pull_request", "pull_request_target")

#: The push trigger of a workflow that runs on pull requests: main, and only main.
PUSH_ON_MAIN = {"branches": ["main"]}


def _runs_on_pull_requests(on: Any) -> bool:
    """Whether triggers ``on`` start the workflow on a pull request.

    A missing ``on`` runs on every event, so it runs on pull requests too.
    """
    if on is None:
        return True
    if isinstance(on, str):
        on = [on]
    return isinstance(on, (dict, list)) and any(event in on for event in PR_EVENTS)


def test_a_workflow_that_runs_pull_requests_runs_a_push_on_main_only() -> None:
    checked: list[str] = []
    for workflow in sorted(WORKFLOWS.glob("*.y*ml")):
        data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        # PyYAML reads the bare key ``on`` as the boolean ``True``.
        on = data.get("on", data.get(True))
        if not _runs_on_pull_requests(on):
            continue
        if isinstance(on, dict):
            has_push, push = "push" in on, on.get("push")
        else:
            # A bare event name or a flow list: events with no filter at all.
            events = [on] if isinstance(on, str) else list(on or [])
            has_push, push = "push" in events, None
        assert has_push, (
            f"{workflow.name} runs on pull requests and has no push trigger "
            f"({on!r}): a push to main must start it too, or no run says main "
            "itself is green"
        )
        assert push == PUSH_ON_MAIN, (
            f"{workflow.name} runs on pull requests and its push trigger is "
            f"{push!r}: write it as {PUSH_ON_MAIN} alone. A push trigger with "
            "no filter, or one that matches a pull request's branch, runs every "
            "job twice on each push to that branch"
        )
        checked.append(workflow.name)
    assert {"ci.yml", "platforms.yml"} <= set(checked), (
        f"ci.yml and platforms.yml run on pull requests; held here: {checked}"
    )
