"""Per-field jev choice rendering for the classifier proposer (W3).

Each W3 field is asked as one :class:`~mcgyvr.decision.Choice` whose option keys
are the candidate ids of the W2 :class:`~mcgyvr.orchestrator.candidates.CandidateSet`
and whose option texts are the per-field rendered lines. The abstain option is a
real candidate (the empty/default sentinel) that renders its human sentence
here; no field reserves a letter, and the letter a candidate shows under is the
positional one :mod:`mcgyvr.decision` assigns.

Only six fields are decided in W3 — `task_type, target, symbol, interface,
deps, allow`. `sources` and `operation` are deferred because a `Proposal` has no
slot for them today, and `task`/`stop_conditions`/`forbid`/`acceptance`/
`demonstration` are deterministic single-candidate folds, not decisions.

Observability note: `mcgyvr.decision.classify` asks for at most 20 label logits
per position (`_MAX_TOP_LOGPROBS`), so candidates shown past position 20 are
structurally unobservable (their score reads 0.0). W3 does not cap the number of
candidates presented; the presented-cap sweep is a later workstream.
"""

from __future__ import annotations

from typing import Any

from mcgyvr.catalog import catalog
from mcgyvr.decision import Choice
from mcgyvr.orchestrator.candidates import (
    _NO_SYMBOL,
    CandidateSet,
    FieldCandidate,
)
from mcgyvr.orchestrator.decompose import DepRef

#: The fields W3 asks the jev unit, in the dependency order the proposer follows.
FIELD_ORDER: tuple[str, ...] = (
    "task_type",
    "target",
    "symbol",
    "interface",
    "deps",
    "allow",
)

#: The criterion each field asks jev to rank candidates against. `{target}` is
#: the file already chosen, filled for the `symbol` field.
_CRITERIA: dict[str, str] = {
    "task_type": "Which task type does this request call for?",
    "target": "Which file should the change land in?",
    "symbol": "Which symbol in {target} does the task work on?",
    "interface": "Which interface signature must the change satisfy?",
    "deps": (
        "Which dependency (a symbol declared in a different file) must the "
        "change import?"
    ),
    "allow": "Which allow-scope covers every file the work touches?",
}

#: The candidate value that means "none" for each field that has one. `task_type`
#: and `target` have none: they are load-bearing, so an unreadable or
#: low-confidence answer declines the whole proposal instead.
_ABSTAIN_VALUE: dict[str, Any] = {
    "symbol": _NO_SYMBOL,
    "interface": "",
    "deps": (),
    "allow": (),
}

#: The option text of each field's abstain candidate.
_ABSTAIN_TEXT: dict[str, str] = {
    "symbol": "no specific symbol — the whole file is the work",
    "interface": "no interface — the change states none",
    "deps": "no dependency — nothing new must be imported",
    "allow": "omit — default to the target",
}

#: The instruction line appended when a field can be answered "none".
_ABSTAIN_LINE: dict[str, str] = {
    "symbol": "Choose the no-symbol option when the whole file is the work.",
    "interface": "Choose the no-interface option when the change states none.",
    "deps": "Choose the no-dependency option when nothing new must be imported.",
    "allow": "Choose the omit option to leave the default scope in place.",
}


def criterion(field: str, *, target: str | None = None) -> str:
    """Render the criterion for `field`, filling `{target}` where it appears."""
    return _CRITERIA[field].format(target=target or "")


def abstain_value(field: str) -> Any | None:
    """The value that means "none" for `field`, or None when it has none."""
    return _ABSTAIN_VALUE.get(field)


def abstain_line(field: str) -> str:
    """The instruction naming the abstain option, or "" when the field has none."""
    return _ABSTAIN_LINE.get(field, "")


def option_text(field: str, candidate: FieldCandidate) -> str:
    """The option line for one candidate of `field`, for the model to read.

    The abstain candidate renders the human sentence in `_ABSTAIN_TEXT`; a real
    candidate renders its value — a task-type doc, a path, a signature, a
    dependency ``path::symbol``, or an allow scope. A symbol renders its name
    (its richer detail line is deferred with the E4 field context), and a task
    type's doc is looked up from the catalog.
    """
    value = candidate.value
    if field == "task_type":
        return catalog().require(str(value)).doc
    if field == "target":
        return str(value)
    if field == "symbol":
        return _ABSTAIN_TEXT["symbol"] if value == _NO_SYMBOL else str(value)
    if field == "interface":
        return _ABSTAIN_TEXT["interface"] if value == "" else str(value)
    if field == "deps":
        if value == ():
            return _ABSTAIN_TEXT["deps"]
        assert isinstance(value, DepRef)  # one dependency per candidate
        return f"{value.path}::{value.symbol}"
    if field == "allow":
        return _allow_text(value)
    raise KeyError(f"no option text for field {field!r}")


def _allow_text(value: Any) -> str:
    """The option line for an `allow` candidate: omit, one target, or every path."""
    if value == ():
        return _ABSTAIN_TEXT["allow"]
    if isinstance(value, tuple):
        paths = tuple(str(path) for path in value)
        if len(paths) == 1:
            return f"{paths[0]} only"
        return "every evidence path: " + ", ".join(paths)
    return str(value)


def instructions(field: str, criterion: str, abstain_line: str = "") -> str:
    """The instruction block for one field's question.

    The empty CONSTRAINTS section is where a later workstream fills the retry
    loop's constraints; W3 leaves it empty.
    """
    lines = [
        f"FIELD {field}: {criterion}",
        "",
        "CONSTRAINTS (ignore this section if empty):",
        "",
        "Pick the candidate that best satisfies the criterion above.",
    ]
    if abstain_line:
        lines.append(abstain_line)
    return "\n".join(lines)


def render_choice(set: CandidateSet, *, criterion: str, abstain_line: str) -> Choice:
    """Render one candidate set as the single `Choice` jev answers for it.

    Option keys are the candidate ids, so a readback maps the answered key back
    to a candidate value with :func:`value_by_id`.
    """
    return Choice(
        instructions=instructions(set.field, criterion, abstain_line),
        options={
            candidate.id: option_text(set.field, candidate)
            for candidate in set.candidates
        },
    )


def value_by_id(set: CandidateSet, candidate_id: str) -> Any:
    """The candidate value filed under `candidate_id`, or KeyError when absent."""
    for candidate in set.candidates:
        if candidate.id == candidate_id:
            return candidate.value
    raise KeyError(f"no candidate {candidate_id!r} in field {set.field!r}")
