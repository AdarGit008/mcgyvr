"""Deterministic cleanup of a change the gate rejected on formatting alone.

The gate's verdict is what decides whether any rewrite happens: where every
finding came from a formatter check, the text is run through ruff's formatter
and handed back ready to be gated again, at no model cost. Where the rejection
was about anything else, the bytes come back exactly as the worker wrote them,
because what the next attempt is shown has to be what the worker produced.

Every way a rewrite can fail — no ruff on PATH, a formatter that crashes or
times out, text that cannot be handed over as UTF-8, syntax the formatter
refuses — is "nothing to apply". The rung already reached its verdict, and a
tidy-up running behind it has no standing to overturn one.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from mcgyvr.gate.adapter import (
    EnvironmentFaultError,
    plain_env,
    require_tool,
)
from mcgyvr.gate.adapters.python import ruff_config_args

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable

    from mcgyvr.gate import GateResult

#: A formatter is a child process reading a pipe, so it can hang or outlive its
#: usefulness with no verdict to show for it. The run is bounded instead, and a
#: timeout arrives as "nothing to apply" like every other failure.
_FORMAT_TIMEOUT_S = 30.0

#: The checks a rewrite is allowed to answer. ``format`` is the only one whose
#: finding is about the bytes the worker wrote rather than about what they mean,
#: so it is the only one a deterministic tool can clear; any other name in a
#: verdict means the change goes back to the worker untouched. The set holds
#: check names because that is what a finding carries, and the one name here is
#: the string ``Gate.run`` files in ``findings`` for a formatting problem, so the
#: split the caller sees and the split this module trusts are the same split.
_FORMATTER_CHECKS = frozenset({"format"})


@dataclass(frozen=True)
class Cleanup:
    """The outcome of one deterministic tidy-up, and what it moved.

    ``content`` is what the caller carries forward: the rewritten text where a
    cleaner ran and changed something, the input unchanged everywhere else.
    ``accepted`` is the gate's verdict restated rather than improved, since a
    cleanup that runs only behind a rejection cannot accept anything and one
    that fails cannot reject. ``cleaned`` is true only where the bytes actually
    changed, and ``detail`` is the line a reader is shown saying why.
    """

    content: str
    accepted: bool
    cleaned: bool = False
    detail: str = ""

    @property
    def tokens_spent(self) -> int:
        """Zero: a local formatter rewrites the text and no model is asked."""
        return 0

    @property
    def regate(self) -> bool:
        """Whether the verdict in hand is stale and the gate has to run again."""
        return self.cleaned


def _ruff_format(content: str, target: str, repo: Path | None) -> str | None:
    """Return ``content`` as ruff's formatter would write it, or ``None``.

    ``target`` is the name the formatter is given for the text, so per-file
    rules, extension dispatch and excludes apply as they would to the file on
    disk; ``repo`` is the directory the tool runs in, and the tree whose own
    ruff configuration is used where it declares one.

    ``None`` means nothing is to be applied. That is the answer for every
    failure — no ruff on PATH, a subprocess that fails or times out, a
    formatter that exits non-zero, and text that cannot be handed over as
    UTF-8 — so the caller keeps the bytes the gate judged.
    """
    try:
        # Best effort from here on: a missing ruff is an environment
        # fault the gate has already had its say about, so it comes
        # back as "nothing to apply" rather than as an exception out
        # of a function whose contract is that it raises none.
        ruff = require_tool("ruff")
    except EnvironmentFaultError:
        return None
    try:
        stdin = content.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError:
        # Text that will not round-trip through UTF-8 is
        # surrogate-escaped bytes off the wire, which no formatter
        # will read. Nothing is applied: rewriting those bytes would
        # be rewriting what the worker wrote.
        return None
    try:
        done = subprocess.run(
            [
                ruff,
                # The config flags come first so they govern the
                # invocation as a whole; ``--stdin-filename`` is the
                # path that decides the file's excludes and per-file
                # rules, since the text arrives on a pipe rather than
                # from disk, and ``-`` is where it is read from.
                *(ruff_config_args(repo) if repo is not None else []),
                "format",
                "--force-exclude",
                "--stdin-filename",
                target,
                "-",
            ],
            input=stdin,
            cwd=repo,
            capture_output=True,
            env=plain_env(),
            timeout=_FORMAT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        # A formatter that exited non-zero formatted nothing:
        # unparseable syntax, a crash, a temporary it could not
        # write. Nothing is applied, so the caller keeps the bytes
        # the gate judged and the cleanup reports no change.
        return None
    if not done.stdout and content.strip():
        return None
    return done.stdout.decode("utf-8", "surrogateescape")


#: One deterministic cleaner per suffix: the caller's target decides which
#: language's formatter answers, and a suffix absent here is one no rewrite is
#: registered for. Every entry takes the same arguments as ``_ruff_format`` and
#: follows the same contract — ``None`` for "nothing to apply", and no exception
#: for any reason.
_CLEANERS: dict[str, Callable[[str, str, Path | None], str | None]] = {
    ".py": _ruff_format,
    ".pyi": _ruff_format,
}


def tidy(
    *,
    content: str,
    result: GateResult,
    target: str,
    repo: Path | None = None,
) -> Cleanup:
    """Tidy a change with the deterministic cleaner, and say what that moved.

    The rewrite happens only where ``result`` is a rejection a formatter can
    answer: a verdict with findings from formatter checks alone, and no rung
    left inconclusive. Anything else is handed back untouched, because what the
    next attempt is shown has to be what the worker wrote. Where ``target``'s
    suffix has a cleaner registered in ``_CLEANERS``, that cleaner formats the
    text, with ``repo`` supplying the tooling configuration and the directory
    the tool runs in.

    A cleaner that cannot run, or that returns the text unchanged, leaves the
    verdict exactly where it stood. One that changes bytes sets ``cleaned`` and
    so ``regate``: the verdict in hand is then about text nobody carries
    forward, and the gate has to run again. No model is involved in any branch,
    so ``tokens_spent`` stays zero.
    """
    if not _cleanable(result):
        return Cleanup(
            content=content,
            accepted=False,
            detail=(
                "the change was rejected on "
                f"{', '.join(result.by_check()) or 'a rung that could not run'}"
                "; only a rejection the formatter itself raised is tidied, "
                "because what the next attempt is shown must be what the "
                "worker wrote."
            ),
        )

    cleaner = _CLEANERS.get(PurePosixPath(target).suffix)
    if cleaner is None:
        return Cleanup(
            content=content,
            accepted=result.accepted,
            detail=f"no deterministic cleaner is registered for {target}.",
        )

    tidied = cleaner(content, target, repo)
    if tidied is None:
        return Cleanup(
            content=content,
            accepted=result.accepted,
            detail=(
                f"the cleanup could not run over {target}; the gate had "
                f"already reached its verdict and a tidy-up that failed does "
                f"not move it."
            ),
        )
    if tidied == content:
        return Cleanup(
            content=content,
            accepted=result.accepted,
            # A fixed point: there was nothing to rewrite, so the
            # verdict is still about exactly these bytes.
            detail=f"nothing to rewrite in {target}; it came back unchanged.",
        )
    return Cleanup(
        content=tidied,
        accepted=result.accepted,
        cleaned=True,
        # The bytes changed, so the verdict is stale and the caller
        # has to re-run the gate over this text.
        detail=(
            f"{target} was reformatted deterministically, at no model cost, "
            f"and the gate wants re-running over it."
        ),
    )


def _cleanable(result: GateResult) -> bool:
    """Whether ``result`` is a verdict a deterministic rewrite may move.

    An inconclusive rung is never cleanable: the change was not rejected for
    anything a reader can point at, and treating "we do not know" as "it is
    only whitespace" would rewrite the bytes under a bar that never ran.
    Otherwise every finding must name a check in ``_FORMATTER_CHECKS``.

    An accepting verdict has no findings, so it passes here — which is what
    keeps the ordinary case, tidying a change that already passed, working.
    """
    if result.inconclusive:
        return False
    return all(finding.check in _FORMATTER_CHECKS for finding in result.findings)
