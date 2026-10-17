"""The gate's Jev rung: typed questions put to a model about a change.

Each text change that adds lines is offered to a `decide` seam as a state of
the contract prose, the file's path, its base and current text, and the added
lines. `JEV_QUESTIONS` asks whether the change satisfies the contract's task,
whether it stays in scope, and how likely it is to break existing behaviour;
a No to either yes/no question or a regression risk of medium or above becomes
a Finding on the file's first added line. A blocking check reports those as
findings and a non-blocking one as observations, and a file whose decision
could not be read is reported as an environment issue rather than judged.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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

# Name every finding and environment issue this check produces carries.
CHECK = "jev"

# The questions every judged file is put to, keyed by the name each answer is
# stored under on the Decision and copied onto the finding's code. Two are
# yes/no — does the change satisfy the task, and is it within scope — and one
# rates regression risk on the low/medium/high scale, where the answer's level
# is the expected index of a level on a 0..2 scale.
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

# Expected regression level, on that 0..2 scale, at which a rating is reported:
# medium and above are objections, low is not.
_REGRESSION_LEVEL = 1.0

# Seam that turns a state into a Decision. It is injected rather than built
# here, so a caller can wrap it — with a wake, or a reviewer's remembered
# refusal — and a test can answer without a wire.
type Decide = Callable[[Any], Decision]


@dataclass(frozen=True)
class JevReport:
    """What one run of a Jev check produced.

    `findings` are the objections of a blocking check, `observations` the same
    items from a non-blocking one, and `environment_issues` the files that could
    not be judged at all.
    """

    findings: tuple[Finding, ...] = ()
    observations: tuple[Finding, ...] = ()
    environment_issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class JevCheck:
    """The gate rung that puts `JEV_QUESTIONS` to each changed file through `decide`."""

    decide: Decide
    blocking: bool = False

    def run(self, changeset: ChangeSet, contract_text: str = "") -> JevReport:
        """Judge every text change that adds lines, and report what came back.

        A blocking check reports the objections as findings and a non-blocking
        one as observations, so the default cannot turn an acceptance into a
        rejection.
        """
        items: list[Finding] = []
        issues: list[str] = []
        for change in _targets(changeset):
            state = build_state(changeset, change, contract_text)
            try:
                decision = self.decide(state)
            except Exception as exc:
                # A seam that raised gave no answer for this file: an unreadable
                # reply or an unreachable unit is the environment's problem, so
                # it is named and the remaining files are still judged.
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
    timeout_s: float | None = None,
    blocking: bool = False,
    capacity: Capacity | None = None,
) -> JevCheck | None:
    """The check that asks `role` the Jev questions, or None when it cannot.

    None means the map has no model bound to `role`, so there is nothing to ask
    and the gate is given no check at all. `decide` goes through `classify_for`,
    so a unit bound to the `jev` role answers instead of `role`, and `timeout_s`
    and `capacity` are passed on to that request.
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


# The state one file is judged from: the contract prose as `task`, the file's
# path, its text at the base and as it stands now, and every added line with
# its line number.
def build_state(
    changeset: ChangeSet, change: FileChange, contract_text: str
) -> dict[str, object]:
    """The state describing one changed file, in the shape `JEV_QUESTIONS` reads."""
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
    """The text changes that add at least one line, which are the ones judged."""
    return tuple(change for change in changeset.text_changes() if change.added_lines)


def _as_finding(change: FileChange, name: str, answer: Answer) -> Finding | None:
    """The objection one answer amounts to, or None when it is no objection.

    A yes/no answer objects when it said No, and a reasoned message names the
    question; a score objects at or above `_REGRESSION_LEVEL` and names the most
    probable level. The finding lands on the file's first added line, or on the
    file itself when the change added none.
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
    """The level the answer gave the most probability to."""
    return max(answer.probabilities.items(), key=lambda item: item[1])[0]
