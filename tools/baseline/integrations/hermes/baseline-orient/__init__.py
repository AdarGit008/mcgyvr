"""baseline-orient — a Hermes Agent plugin that opens each session oriented.

Registers, via the standard ``register(ctx)`` entry point:

  * an ``/orient`` slash command that prints the baseline skill's derived-state
    survey (live lanes / backlog / divergence) on demand, and
  * an ``on_session_start`` hook that runs the same survey at session start so a
    session opens from derived state instead of a hand-maintained status doc (C16).

It shells out to the baseline CLI (``baseline.mjs orient``) — no provider keys and
no network of its own; orient itself degrades gracefully when a plane is unreachable.

Authored against the NousResearch hermes-agent plugin API:
``ctx.register_command(name, handler, description, args_hint)`` and
``ctx.register_hook(hook_name, callback)`` with ``hook_name`` in ``VALID_HOOKS``
(``on_session_start`` is a member). See README.md — the only detail not verifiable
offline is the exact way ``on_session_start`` injects a system-prompt block; the
``/orient`` command surface is spec-confirmed.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)


def _baseline_cmd() -> list[str] | None:
    """Locate the baseline CLI: BASELINE_CLI override, else an installed skill, else PATH."""
    override = os.environ.get("BASELINE_CLI")
    if override:
        return ["node", override]
    for cand in (
        os.path.expanduser("~/.hermes/skills/software-development/baseline/baseline.mjs"),
        os.path.expanduser("~/.claude/skills/baseline/baseline.mjs"),
    ):
        if os.path.exists(cand):
            return ["node", cand]
    if shutil.which("baseline"):
        return ["baseline"]
    return None


def _run_orient(repo: str | None = None) -> str:
    cmd = _baseline_cmd()
    if not cmd:
        return "_baseline CLI not found — set BASELINE_CLI, or install the baseline skill._"
    args = cmd + ["orient", "--repo", repo or os.getcwd()]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return (proc.stdout or "").strip() or "_baseline orient produced no output._"
    except Exception as exc:  # a wrapper failure must never break a session (orient is advisory)
        logger.debug("baseline orient failed: %s", exc)
        return f"_baseline orient unavailable: {exc}_"


def register(ctx) -> None:
    # /orient — print the derived-state survey on demand.
    def _orient_command(args: str = "", **kwargs) -> str:
        return _run_orient()

    ctx.register_command(
        "orient",
        _orient_command,
        description="Derived-state survey (live lanes, backlog, divergence) from the baseline skill.",
        args_hint="",
    )

    # on_session_start — open the session with the survey as context.
    # The survey text is returned so the host can surface it at session start. The precise
    # injection contract for on_session_start (return a block vs. mutate a passed context
    # object) is the one thing not verifiable without a live Hermes runtime — see README.
    def _on_session_start(**kwargs) -> str | None:
        survey = _run_orient()
        return f"# Session orientation (baseline)\n\n{survey}" if survey else None

    ctx.register_hook("on_session_start", _on_session_start)
