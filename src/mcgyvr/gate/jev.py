"""Jev-class verifier rung: typed questions over the change and contract.

The gate's deterministic rungs answer questions a tool can answer; this one
asks the questions that need a model, and asks them the way the Jev-class
primitive (:mod:`mcgyvr.decision`) does — typed, single-token, read from
next-token probabilities rather than prose. Per changed file it asks whether
the added change satisfies the contract's task, whether it stays in scope, and
how likely it is to regress existing behaviour.

**It reports; it does not reject.** ``blocking`` defaults to ``False``, so
findings arrive as ``observations`` that never fail a change, exactly as the
semantic rung (:mod:`mcgyvr.gate.semantic`) ships. Flipping ``blocking`` is a
policy decision and out of scope here.

**The whole change is shown; only added lines are judged.** The state sent
to the model carries the file at the change's base (``original``), the file
as the worker left it (``change``) and the worker's added lines — the same
material :func:`mcgyvr.verify.verdict_state` shows the reviewer, because in
the pilot a rung shown added lines alone scored AUROC 0.44-0.65 and the
reviewer shown both scored 0.73-0.75 (owner ruling). What is judged has not
moved: a finding is attributed to an added line
(:func:`~mcgyvr.gate.changeset.read_added_text`), so a pre-existing line in a
touched file can never fail a worker. A change with no added lines is a no-op.

**A model that cannot run is an environment issue, never a rejection.** An
unreachable endpoint, a backend that answered outside the protocol, a decision
that cannot be read: all are recorded as degraded coverage, the same rule the
semantic rung and the acceptance rung hold.

The rung is injected into the gate — like
:class:`~mcgyvr.gate.semantic.SemanticCheck` — rather than constructed there,
because it needs a model only a caller above the pool seam can bind. It holds
a ``decide`` seam (state in, a :class:`~mcgyvr.decision.Decision` out) rather
than an endpoint, so nothing above the seam learns where the model runs;
:func:`jev_check_for` builds that seam from the pool's role.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcgyvr.config import DEFAULT_REQUEST_TIMEOUT_S
from mcgyvr.decision import (
    Answer,
    BoolAnswer,
    Decision,
    Noul,
    Question,
    Score,
    ScoreAnswer,
    classify_for,
)
from mcgyvr.gate.changeset import (
    ChangeSet,
    FileChange,
    read_added_text,
    read_base_text,
    read_current_text,
)
from mcgyvr.gate.findings import Finding
from mcgyvr.local_pool import SourceMap

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity

#: The check name every Jev finding carries.
CHECK = "jev"

#: The typed questions asked of each changed file. A :class:`Noul` answers
#: Yes/No; a :class:`Score` rates on the given levels, lowest first. Public so
#: a caller can bind the same questions to a role through
#: :func:`~mcgyvr.decision.classify_role`.
JEV_QUESTIONS: Mapping[str, Question] = {
    "satisfies_task": Noul(
        "Does the added change satisfy the contract's task, as stated?"
    ),
    "in_scope": Noul("Is every added line within the scope the contract allows?"),
    "regression_risk": Score(
        "How likely is the added change to break existing behaviour?",
        levels=("low", "medium", "high"),
    ),
}

#: The expected Score level at or above which regression risk is reported.
#: 0 is low, 1 medium, 2 high; flagging from medium keeps a low-risk change
#: silent.
_REGRESSION_LEVEL = 1.0

#: The seam the rung holds: one change's state in, a typed decision out. Built
#: from :func:`~mcgyvr.decision.classify` by :func:`jev_check_for`.
type Decide = Callable[[Any], Decision]


class JevUnavailableError(RuntimeError):
    """The verifier role was bound and then had nothing to answer a decision."""


@dataclass(frozen=True)
class JevReport:
    """What the rung saw, in the gate's own currency.

    ``findings`` reject the change and are populated only when ``blocking`` is
    set; otherwise the same items arrive as ``observations``, which are
    reported and never rejecting. ``environment_issues`` mirror
    :class:`~mcgyvr.gate.semantic.SemanticReport`'s, so the gate folds one into
    the other.
    """

    findings: tuple[Finding, ...] = ()
    observations: tuple[Finding, ...] = ()
    environment_issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class JevCheck:
    """The Jev verifier rung, bound to a typed-decision seam.

    ``decide`` answers :data:`JEV_QUESTIONS` about one change's state, and is
    supplied by the caller above the pool seam (via :func:`jev_check_for`), so
    the rung itself never holds an endpoint. ``blocking`` defaults to
    ``False``, so a negative answer reports without rejecting.
    """

    decide: Decide
    blocking: bool = False

    def run(self, changeset: ChangeSet, contract_text: str = "") -> JevReport:
        """Ask the typed questions of each changed file, over its added lines."""
        items: list[Finding] = []
        issues: list[str] = []
        for change in _targets(changeset):
            state = build_state(changeset, change, contract_text)
            try:
                decision = self.decide(state)
            except Exception as exc:
                # Anything the seam can raise — unreachable, unreadable, a
                # credential gone mid-run — is a reviewer-side fault, never a
                # verdict about the worker's change.
                issues.append(
                    f"{CHECK}: {change.path} was not judged — "
                    f"{type(exc).__name__}: {exc}"
                )
                continue
            for name, answer in decision.answers.items():
                finding = _as_finding(change, name, answer)
                if finding is not None:
                    items.append(finding)
        return JevReport(
            findings=tuple(items) if self.blocking else (),
            observations=() if self.blocking else tuple(items),
            environment_issues=tuple(issues),
        )


def jev_check_for(
    source_map: SourceMap,
    role: str,
    *,
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
    blocking: bool = False,
    capacity: Capacity | None = None,
) -> JevCheck | None:
    """The install's ``role`` as a Jev rung, or ``None`` when it has none.

    Mirrors :func:`mcgyvr.verify.reviewer_for` one seam over: the endpoint and
    model stay below the seam inside :func:`~mcgyvr.decision.classify_for`, and
    only the ``decide`` seam crosses it. ``capacity`` holds the answering
    unit's source slot for each question, as a dispatch to it would.

    Whether the rung exists is ``role``'s to say; who answers it is not. With
    ``jev.unit`` bound the questions go to that unit, and without it to
    ``role``'s own, as they did before a Jev unit existed.
    """
    if source_map.role_model(role) is None:
        return None

    def decide(state: Any) -> Decision:
        return classify_for(
            source_map,
            state,
            JEV_QUESTIONS,
            role=role,
            capacity=capacity,
            timeout_s=timeout_s,
        )

    return JevCheck(decide=decide, blocking=blocking)


# --- state -----------------------------------------------------------------


def build_state(
    changeset: ChangeSet, change: FileChange, contract_text: str
) -> dict[str, object]:
    """The JSON state a decision is asked over, for one changed file.

    ``original`` is the file at the change's base — read from git, empty where
    the base has no such file or the repository cannot say — and ``change`` is
    the file as the worker left it; ``added_lines`` are the worker's, read
    through :func:`~mcgyvr.gate.changeset.read_added_text`, and are the only
    lines a finding is attributed to.
    """
    added = read_added_text(change, changeset.repo)
    return {
        "task": contract_text,
        "path": change.path,
        "original": read_base_text(change, changeset),
        "change": read_current_text(change, changeset.repo),
        "added_lines": [
            {"line": line, "text": text} for line, text in sorted(added.items())
        ],
    }


def _targets(changeset: ChangeSet) -> tuple[FileChange, ...]:
    """The changed files the rung judges: non-binary, non-deleted, with adds."""
    return tuple(change for change in changeset.text_changes() if change.added_lines)


def _as_finding(change: FileChange, name: str, answer: Answer) -> Finding | None:
    """Turn a negative answer into a finding, or ``None`` for a clean answer.

    A ``Yes`` on a :class:`Noul` and a low :class:`Score` are silent; a ``No``
    and a rating at or above :data:`_REGRESSION_LEVEL` are reported, attributed
    to the first added line of the file the question was asked about.
    """
    line = min(change.added_lines) if change.added_lines else None
    if isinstance(answer, BoolAnswer):
        if answer.value:
            return None
        problem = (
            "does not satisfy the contract's task"
            if name == "satisfies_task"
            else "is judged outside the contract's scope"
        )
        message = (
            f"the Jev verifier answered No to {name}: the added change "
            f"{problem} (probability of Yes {answer.probability_true:.2f}, "
            f"confidence {answer.confidence:.2f})"
        )
    elif isinstance(answer, ScoreAnswer):
        if answer.level < _REGRESSION_LEVEL:
            return None
        peak = _peak_level(answer)
        message = (
            f"the Jev verifier rated regression risk {peak} (expected level "
            f"{answer.level:.2f} on a 0..2 scale, confidence "
            f"{answer.confidence:.2f})"
        )
    else:
        return None
    return Finding(check=CHECK, path=change.path, line=line, code=name, message=message)


def _peak_level(answer: ScoreAnswer) -> str:
    """The level name carrying the most probability."""
    return max(answer.probabilities.items(), key=lambda item: item[1])[0]
