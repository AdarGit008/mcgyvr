""

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

if TYPE_CHECKING:  #
    from mcgyvr.capacity import Capacity

#
CHECK = "jev"

#
#
#
#
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

#
#
#
_REGRESSION_LEVEL = 1.0

#
#
type Decide = Callable[[Any], Decision]


@dataclass(frozen=True)
class JevReport:
    ""

    findings: tuple[Finding, ...] = ()
    observations: tuple[Finding, ...] = ()
    environment_issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class JevCheck:
    ""

    decide: Decide
    blocking: bool = False

    def run(self, changeset: ChangeSet, contract_text: str = "") -> JevReport:
        ""
        items: list[Finding] = []
        issues: list[str] = []
        for change in _targets(changeset):
            state = build_state(changeset, change, contract_text)
            try:
                decision = self.decide(state)
            except Exception as exc:
                # a
                # a
                #
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
    ""
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


#


def build_state(
    changeset: ChangeSet, change: FileChange, contract_text: str
) -> dict[str, object]:
    ""
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
    ""
    return tuple(change for change in changeset.text_changes() if change.added_lines)


def _as_finding(change: FileChange, name: str, answer: Answer) -> Finding | None:
    ""
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
    ""
    return max(answer.probabilities.items(), key=lambda item: item[1])[0]
