"""Cleaning a style violation out of a change, at no model cost.

mcgyvr already draws the distinction this module acts on.
:class:`~mcgyvr.gate.GateResult` splits what the rungs saw into ``findings``,
which reject, ``observations``, which are real, line-attributed and deliberately
outside the verdict, and ``environment_issues``, which are checks that could not
run. What nothing did was *act* on the split: ``ruff format`` is run with
``--diff`` and ``ruff check`` without ``--fix``, so a change whose only remaining
problem is a space in the wrong place is reported and then handed to a model —
a dispatch, a full context and an attempt off the ceiling, to insert a space.
This module closes that: the gate's own verdict decides whether a change is
tidied or left alone, and the tidying is a formatter, not a model.

**Style is cleaned; correctness is rejected and never tidied.** The gate's two
buckets are most of that decision and not all of it. ``observations`` never
reject, so a change carrying only those is already accepted and is tidied. The
format rung is the awkward one: it emits ``check="format"``, which lands in
``findings``, so the single case this module was built for arrives as a
*rejection*. It is tidied anyway, and it is the only rejection that is — a
change is cleaned when every reason the gate gave for rejecting it is one the
formatter itself raised. That is the same rule the buckets were standing in for,
stated where the gate actually files the item rather than where the bucket's
name suggests it would. Every other rejection comes back byte-identical on
purpose: rewriting it would hand the next attempt a file the worker never wrote,
and every retry note about "your change" would then be about somebody else's.

**A cleanup overturns nothing, and it settles nothing either.** The gate
short-circuits — its typecheck, semantic and acceptance rungs run only while
nothing has rejected yet — so behind a format finding the contract's own suite
never ran at all. :attr:`Cleanup.accepted` is therefore the gate's own verdict
carried through unchanged, and it is a verdict about the bytes that went *in*.
:attr:`Cleanup.regate` is true whenever bytes came out different, acceptance or
rejection alike: what makes a verdict true is the file it was computed over, and
this module replaced that file. The caller re-runs the gate. Nothing here
reports a bar that nobody applied, and nothing here lets a file travel onward
under a verdict about a different one — which is the port's "nothing owns the
bytes" at this lever.

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

#: The rejecting checks a formatter answers on its own. Only the format rung is
#: here, and only because it *is* the formatter: its finding says ruff format
#: would reflow a worker-added line, so running ruff format is not a guess at
#: what would satisfy it but the same tool reaching the same fixed point. Both
#: language adapters spell it this way. The lint rung's style-classed codes are
#: deliberately absent — answering those means ``ruff check --fix``, which the
#: module docstring declines for a reason that has not changed.
_FORMATTER_CHECKS = frozenset({"format"})


@dataclass(frozen=True)
class Cleanup:
    """What a tidy-up left behind, and whether it happened at all.

    ``content`` is what the caller carries forward — always the input bytes
    unless something actually rewrote them, so a caller can use this result
    without first asking which branch it came from.

    Where they *were* rewritten, they are bytes no rung has read:
    :attr:`accepted` is the verdict the gate reached over what went in, and this
    is what came out. :attr:`regate` is how that is said, and it is the reason
    these bytes are allowed to travel as a plain ``str`` at all — a caller
    cannot get them into a tree that anything commits without running the gate
    again, and what it delivers is minted there
    (:meth:`mcgyvr.deliver.Accepted.read`).
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

    @property
    def regate(self) -> bool:
        """Whether the verdict behind this result is now stale.

        True whenever the bytes were rewritten, which is the only thing that can
        make a verdict stale: what makes one true is the file it was computed
        over, and the formatter replaced that file. This used to read
        ``cleaned and not accepted`` — stale only where the *rejection* had to
        be cleared — which left the worse branch silent. A rejected change gets
        re-run because nothing can ship under a rejection anyway; an accepted
        one was carried onward under a verdict reached on bytes the formatter
        had already replaced, and no rung anywhere had read what the caller was
        holding.

        Behind a rejection the gate also stopped before its typecheck, semantic
        and acceptance rungs, so there what is owed is a whole gate run rather
        than a re-read of this one. After an acceptance every rung did run, and
        the re-run is the cheap confirmation that a deterministic reformat
        changed nothing they cared about — which costs a subprocess and no
        tokens, the same trade this module already makes against a dispatch.

        Derived rather than stored, for the reason :attr:`tokens_spent` is: it
        is a fact about what happened, and a field would be somewhere to write
        a more convenient answer.
        """
        return self.cleaned


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

    The pipe is bytes on both sides. ``text=True`` would encode with the
    process's preferred encoding under ``strict``, which raises on the
    ``surrogateescape`` characters the rest of mcgyvr uses to carry an
    undecodable byte through a ``str`` (:mod:`mcgyvr.pending`) — a crash out of
    the one function in this module that promises never to raise. It would also
    translate the newlines on the way back, so a file with CRLF endings would
    come out of a *cleanup* with different ones.
    """
    try:
        # The gate's own formatter, named here and nowhere else in this module:
        # a cleanup that ran a different tool than the format rung checks would
        # tidy a file into a shape the gate then complains about.
        ruff = require_tool("ruff")
    except EnvironmentFaultError:
        return None
    try:
        stdin = content.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError:
        # `surrogateescape` is total over bytes that came off a disk and
        # partial over text that came off the wire: a lone `\ud800` is a legal
        # JSON escape and has no byte form at all. There is nothing to hand the
        # formatter, which is the same answer as a formatter that is not there.
        return None
    try:
        done = subprocess.run(
            [ruff, "format", "--force-exclude", "--stdin-filename", target, "-"],
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
        # Exit 2 is ruff refusing to parse; its stdout is empty, and writing
        # that back would delete the file. #261 is a record of empty output
        # being read as a clean answer three times in this project — here the
        # exit code is the test, and nothing else is consulted. Bytes ruff
        # cannot read as UTF-8 arrive here too, for the same reason and with
        # the same answer.
        return None
    if not done.stdout and content.strip():
        return None
    return done.stdout.decode("utf-8", "surrogateescape")


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
    """Clean a change whose only problem is formatting, or hand it back untouched.

    ``result`` is the gate's verdict on this change and is the only thing that
    decides which of those happens. A change it accepted is tidied; so is one it
    rejected *only* on the formatter's own rung, which is the case this module
    exists for and the one the gate files under ``findings`` rather than under
    ``observations``. Any other rejection — a lint code, a failed acceptance
    command, a rung that could not say what bar it applied — leaves the bytes
    alone, whatever else the result carries.

    The verdict itself is never overturned: :attr:`Cleanup.accepted` is
    ``result.accepted`` unchanged, and a cleaned rejection is reported through
    :attr:`Cleanup.regate` for the caller to re-gate. This function has no way
    of knowing what the rungs behind the rejection would have said, because
    behind a rejection they did not run.

    ``repo`` names the tree whose formatter configuration decides what clean
    means. It matters that this is the same tree the gate checked: a cleanup run
    under a different line length would tidy a file into a shape the gate then
    complains about, which is worse than not cleaning at all. ``None`` runs
    where the process already is.
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
            # Covers both "already formatted" and "the formatter declined this
            # path", which are the same fact to a caller: nothing to write.
            detail=f"nothing to rewrite in {target}; it came back unchanged.",
        )
    return Cleanup(
        content=tidied,
        accepted=result.accepted,
        cleaned=True,
        # Unconditional: the sentence used to end with a full stop when the gate
        # had accepted, which told the operator a rewritten file was settled.
        # The verdict in hand is about the bytes that went in either way.
        detail=(
            f"{target} was reformatted deterministically, at no model cost, "
            f"and the gate wants re-running over it."
        ),
    )


def _cleanable(result: GateResult) -> bool:
    """Whether these bytes are this module's to rewrite.

    True for a change the gate accepted, and for exactly one kind of rejection:
    one where every finding came from the formatter itself, so re-running the
    formatter removes all of it. An inconclusive rung disqualifies a change even
    with no findings beside it — a rung that ran and cannot say what bar it
    applied (ADR-0034) has not told anyone the problem is formatting, and
    tidying on that would be answering a question that was never asked.
    """
    if result.inconclusive:
        return False
    return all(finding.check in _FORMATTER_CHECKS for finding in result.findings)
