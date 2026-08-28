"""Cleaning a style violation out of an accepted change, at no model cost.

mcgyvr already draws the distinction this module acts on.
:class:`~mcgyvr.gate.GateResult` splits what the rungs saw into ``findings``,
which reject, ``observations``, which are real, line-attributed and deliberately
outside the verdict, and ``environment_issues``, which are checks that could not
run. What nothing did was *act* on the split: ``ruff format`` is run with
``--diff`` and ``ruff check`` without ``--fix``, so a change whose only remaining
problem is a space in the wrong place is reported and then handed to a model —
a dispatch, a full context and an attempt off the ceiling, to insert a space.
This module closes that: the gate's own two buckets decide whether a change is
tidied or rejected, and the tidying is a formatter, not a model.

**Style is cleaned; correctness is rejected and never tidied.** The bucket is
the whole decision, and it is read from the result rather than from a check's
name — which is what lets the split hold whichever rung produced the item. A
rejected change comes back byte-identical on purpose: rewriting it would hand
the next attempt a file the worker never wrote, and every retry note about
"your change" would then be about somebody else's.

**The spend is zero, structurally.** :attr:`Cleanup.tokens_spent` is a property
returning ``0`` rather than a field anything could set, and this module imports
nothing that can dispatch. That is the entire economic argument for the lever: a
cleanup that could reach a model is a retry wearing a cheaper name, and the way
to make that claim checkable is to leave no shape for it to happen in.

**A cleanup that cannot run does not overturn a verdict it arrived after.** The
gate reached its answer before this module was called, so a formatter that
crashed, is not installed, or met syntax it cannot parse leaves the change
exactly as accepted as it already was. It also never *claims* to have cleaned:
:attr:`Cleanup.cleaned` is false unless the bytes actually changed, because an
outcome that reports work it did not do is how a file with a known problem
stops being looked at.

**Determinism, because this sits inside the acceptance path.** ``ruff format``
is a fixed point — the same input gives the same bytes, and formatting
already-formatted content changes nothing — which is what makes the cleanup
safe to run twice, as it will be the moment it sits in a retry loop. D26 (no RNG
in the decision path) is on the list of things this port must not regress, and a
rewriter with an opinion that varied would put a coin flip inside an acceptance.

**Why the whole file, and when that stops being right.** ``ruff format`` reflows
everything, including lines the worker never touched, where the gate's format
rung reports only reformatting that lands on a worker-added line. That is safe
under ``whole_file`` — the default ``output_schema``, where the content handed
here is a file the worker wrote in its entirety — and would need an added-line
filter the day a scoped-edit shape (D14's AST merge-back) lands. ``ruff check
--fix`` is deliberately *not* run for the mirror-image reason: the gate already
rejects lint findings on worker-added lines, so a fix pass could only rewrite
lines the worker never wrote, which is diff expansion rather than cleanup.
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

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable

    from mcgyvr.gate import GateResult

#: A best-effort tidy-up must not be able to wedge a change the gate already
#: accepted, so the formatter is given a bound and a hang is answered the same
#: way an absent tool is: the content comes back untouched.
_FORMAT_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class Cleanup:
    """What a tidy-up left behind, and whether it happened at all.

    ``content`` is what the caller carries forward — always the input bytes
    unless something actually rewrote them, so a caller can use this result
    without first asking which branch it came from.
    """

    content: str
    accepted: bool
    cleaned: bool = False
    detail: str = ""

    @property
    def tokens_spent(self) -> int:
        """Always zero, and a property so that it cannot be anything else.

        Not a field with a default: a field is something a future caller can
        set, and the one claim this lever rests on is that cleaning a style
        violation costs nothing. Whoever makes this dispatch has to change the
        type, which is the point at which someone would notice.
        """
        return 0


def _ruff_format(content: str, target: str, repo: Path | None) -> str | None:
    """``content`` as ``ruff format`` would write it, or ``None`` if it could not.

    ``None`` covers every way this can fail to produce a trustworthy answer, and
    they are collapsed on purpose: an absent ruff, a ruff that timed out, and a
    file whose syntax it cannot parse all mean the same thing to a caller that
    has already accepted the change — nothing to apply.

    ``--stdin-filename`` is what makes the run configuration-correct without a
    temporary file: ruff resolves the same settings it would for that path, and
    with ``--force-exclude`` an excluded path is echoed back unchanged rather
    than reformatted, which is the gate's own behaviour for the same file.
    """
    try:
        # The gate's own formatter, named here and nowhere else in this module:
        # a cleanup that ran a different tool than the format rung checks would
        # tidy a file into a shape the gate then complains about.
        ruff = require_tool("ruff")
    except EnvironmentFaultError:
        return None
    try:
        done = subprocess.run(
            [ruff, "format", "--force-exclude", "--stdin-filename", target, "-"],
            input=content,
            cwd=repo,
            capture_output=True,
            text=True,
            env=plain_env(),
            timeout=_FORMAT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        # Exit 2 is ruff refusing to parse; its stdout is empty, and writing
        # that back would delete the file. #261 is a record of empty output
        # being read as a clean answer three times in this project — here the
        # exit code is the test, and nothing else is consulted.
        return None
    if not done.stdout and content.strip():
        return None
    return done.stdout


#: Suffix to formatter. Python's is ruff — the tool this project already gates
#: with, so a cleanup produces exactly the shape the format rung asks for rather
#: than a second opinion about it. A second language is an entry here: the gate's
#: :class:`~mcgyvr.gate.adapter.LanguageAdapter` has no "rewrite" method to
#: borrow, and this module deliberately does not need one added to it.
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
    """Clean an accepted change's style, or hand back a rejected one untouched.

    ``result`` is the gate's verdict on this change and is the only thing that
    decides which of those happens: a change with findings is rejected and its
    bytes are not this module's to alter, whatever its observations say.

    ``repo`` names the tree whose formatter configuration decides what clean
    means. It matters that this is the same tree the gate checked: a cleanup run
    under a different line length would tidy a file into a shape the gate then
    complains about, which is worse than not cleaning at all. ``None`` runs
    where the process already is.
    """
    if not result.accepted:
        return Cleanup(
            content=content,
            accepted=False,
            detail=(
                "the change was rejected on "
                f"{', '.join(result.by_check()) or 'no named check'}; a "
                "rejected change is not tidied, because what the next attempt "
                "is shown must be what the worker wrote."
            ),
        )

    cleaner = _CLEANERS.get(PurePosixPath(target).suffix)
    if cleaner is None:
        return Cleanup(
            content=content,
            accepted=True,
            detail=f"no deterministic cleaner is registered for {target}.",
        )

    tidied = cleaner(content, target, repo)
    if tidied is None:
        return Cleanup(
            content=content,
            accepted=True,
            detail=(
                f"the cleanup could not run over {target}; the gate had "
                f"already accepted this change and a tidy-up that failed does "
                f"not overturn that."
            ),
        )
    if tidied == content:
        return Cleanup(
            content=content,
            accepted=True,
            # Covers both "already formatted" and "the formatter declined this
            # path", which are the same fact to a caller: nothing to write.
            detail=f"nothing to rewrite in {target}; it came back unchanged.",
        )
    return Cleanup(
        content=tidied,
        accepted=True,
        cleaned=True,
        detail=f"{target} was reformatted deterministically, at no model cost.",
    )
