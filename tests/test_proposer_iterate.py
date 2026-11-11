"""The re-ask: a refused field is asked again, once, with what was refused.

`reask` asks the classifier again for the field a refusal names, carrying the
fields already decided and dropping the rejected candidate from the next
question, with the refusal's ``what_to_change`` as that field's constraint.
`reaskable` says whether the classifier decides the field at all. A refused
proposal in a decomposition is not re-asked: it goes to the top rung
(test_a_refused_proposal_goes_to_the_top_rung_once_then_is_reported.py).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mcgyvr.decompose.decompose import DepRef, Evidence, Proposal, Refusal
from mcgyvr.decompose.fields import FIELD_ORDER
from mcgyvr.decompose.iterate import reask, reaskable

#: A model-written whole-file contract names a condition that sends it to
#: BLOCKED, so each scripted proposal carries one.
STOP = "the request is ambiguous"


def agent_proposal(target: str) -> Proposal:
    """A servable proposal against `target`, for the scripted classifier."""
    return Proposal(
        task_type="agent",
        task=f"document {target}",
        target=target,
        stop_conditions=(STOP,),
    )


class ScriptedClassifier:
    """A classifier-like fake whose `.propose` returns the next scripted result."""

    def __init__(self, *results: Proposal | Refusal):
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []

    def propose(
        self,
        evidence: Evidence,
        *,
        decided: Mapping[str, Any] | None = None,
        constraints: Mapping[str, str] | None = None,
        rejected: Mapping[str, Any] | None = None,
    ) -> Proposal | Refusal:
        self.calls.append(
            {"decided": decided, "constraints": constraints, "rejected": rejected}
        )
        if not self.results:
            raise AssertionError("scripted classifier ran out of results")
        return self.results.pop(0)


#: The evidence a re-ask is handed. The scripted classifier never reads it.
EVIDENCE: Any = object()


def test_a_refused_target_is_dropped_and_its_directive_becomes_a_constraint() -> None:
    """The re-ask is told to drop the refused target and to obey its directive."""
    classifier = ScriptedClassifier(agent_proposal("listing.py"))
    refusal = Refusal("gone.py", "no such file", field="target", what_to_change="x")
    decided: dict[str, Any] = {}
    constraints: dict[str, str] = {}
    rejected: dict[str, frozenset[Any]] = {}

    asked = reask(
        classifier,
        EVIDENCE,
        agent_proposal("gone.py"),
        refusal,
        decided=decided,
        constraints=constraints,
        rejected=rejected,
    )

    assert asked == agent_proposal("listing.py")
    (call,) = classifier.calls
    assert "gone.py" in call["rejected"]["target"]
    assert call["constraints"]["target"] == "x"
    assert call["decided"] == {"task_type": "agent"}, "the fields upstream of target"


def test_a_classifier_refusal_is_reasked_with_nothing_decided_or_rejected() -> None:
    """A `Refusal` from the classifier itself keeps what was decided."""
    classifier = ScriptedClassifier(agent_proposal("listing.py"))
    refusal = Refusal(
        "request",
        "the task_type answer fell below the confidence floor",
        field="task_type",
        what_to_change="answer with a candidate above the confidence floor",
    )

    reask(
        classifier,
        EVIDENCE,
        refusal,
        refusal,
        decided={},
        constraints={},
        rejected={},
    )

    (call,) = classifier.calls
    assert call["decided"] == {}
    assert call["rejected"] == {}
    assert call["constraints"]["task_type"] == (
        "answer with a candidate above the confidence floor"
    )


def test_a_refused_dependency_is_dropped_as_one_depref_not_the_tuple() -> None:
    """`Proposal.deps` is a tuple while `deps` candidates are single `DepRef`s.

    The re-ask converts back to the plan representation when recording the
    rejected value, or the next question would carry the whole tuple.
    """
    dep = DepRef("nowhere.py", "nope")
    refused = Proposal(
        task_type="agent",
        task="x",
        target="listing.py",
        deps=(dep,),
        stop_conditions=(STOP,),
    )
    classifier = ScriptedClassifier(agent_proposal("listing.py"))

    reask(
        classifier,
        EVIDENCE,
        refused,
        Refusal("nowhere.py", "no such symbol", field="deps", what_to_change="y"),
        decided={},
        constraints={},
        rejected={},
    )

    (call,) = classifier.calls
    assert call["rejected"]["deps"] == frozenset({dep})
    assert call["constraints"]["deps"] == "y"


def test_a_field_the_classifier_does_not_decide_is_not_reaskable() -> None:
    """A refusal naming a field outside `FIELD_ORDER` cannot be asked again."""
    assert reaskable(Refusal("x", "no checker", field="type_check")) is False
    assert reaskable(Refusal("x", "catch-all")) is False
    assert all(reaskable(Refusal("x", "r", field=name)) for name in FIELD_ORDER)
