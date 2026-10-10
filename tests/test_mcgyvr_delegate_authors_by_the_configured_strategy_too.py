"""`mcgyvr delegate` authors by `orchestrator.authoring` too, not only mcorch.

The field names how a request becomes contracts, and the same measured choice
should drive both doors. `classifier` has `mcgyvr delegate` ask the jev unit
(or the orchestrator role, when none is bound) the typed choices first and
fall back to the prose proposer when the classifier returns nothing; any other
value — `prose`, `direct`, or unbound — is the prose proposer the command has
always used, since `direct` is a strategy only a conversing rung can carry out.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mcgyvr.config import parse
from mcgyvr.delegate import proposer_by_authoring
from mcgyvr.local_pool import source_map
from mcgyvr.orchestrator.decompose import Evidence, Proposal

SETUP = """\
units:
  cheap:
    address: http://box.invalid:11434
    model: coder-7b
    rig: box
    width: 3
ladder:
- cheap
orchestrator:
  unit: cheap
"""


def _evidence() -> Evidence:
    return Evidence(
        prompt="x",
        index=None,  # type: ignore[arg-type]  # never read by the doubles below
        resolution=None,  # type: ignore[arg-type]
        exploration=None,  # type: ignore[arg-type]
        vocabulary=(),
    )


def _proposal(name: str) -> Proposal:
    return Proposal(task_type="docstring", task=name, target="a.py")


def test_classifier_asks_the_typed_proposer_first_and_falls_back_to_prose() -> None:
    asked: list[str] = []

    def typed(evidence: Evidence) -> Sequence[Proposal]:
        asked.append("typed")
        return ()

    def prose(evidence: Evidence) -> Sequence[Proposal]:
        asked.append("prose")
        return (_proposal("from prose"),)

    propose = proposer_by_authoring("classifier", typed=typed, prose=prose)
    assert propose is not None
    assert [p.task for p in propose(_evidence())] == ["from prose"]
    assert asked == ["typed", "prose"]


def test_a_typed_answer_is_taken_without_asking_prose() -> None:
    asked: list[str] = []

    def typed(evidence: Evidence) -> Sequence[Proposal]:
        asked.append("typed")
        return (_proposal("from typed"),)

    def prose(evidence: Evidence) -> Sequence[Proposal]:
        asked.append("prose")
        return ()

    propose = proposer_by_authoring("classifier", typed=typed, prose=prose)
    assert propose is not None
    assert [p.task for p in propose(_evidence())] == ["from typed"]
    assert asked == ["typed"]


def test_any_other_strategy_is_the_prose_proposer_as_before() -> None:
    def typed(evidence: Evidence) -> Sequence[Proposal]:
        raise AssertionError("not asked")

    def prose(evidence: Evidence) -> Sequence[Proposal]:
        return (_proposal("prose"),)

    for strategy in ("prose", "direct", None):
        propose = proposer_by_authoring(strategy, typed=typed, prose=prose)
        assert propose is prose


def test_with_no_prose_proposer_there_is_none_to_fall_back_to() -> None:
    def typed(evidence: Evidence) -> Sequence[Proposal]:
        return ()

    assert proposer_by_authoring("classifier", typed=typed, prose=None) is None
    assert proposer_by_authoring("prose", typed=typed, prose=None) is None


def test_the_command_reads_the_field_from_the_config(monkeypatch: Any) -> None:
    """The wiring: `_delegate` passes the config's `orchestrator.authoring`."""
    import pytest

    from mcgyvr import cli, delegate

    assert isinstance(monkeypatch, pytest.MonkeyPatch)
    seen: list[str | None] = []
    real = delegate.proposer_by_authoring

    def spy(strategy: str | None, **kwargs: Any) -> Any:
        seen.append(strategy)
        return real(strategy, **kwargs)

    monkeypatch.setattr(delegate, "proposer_by_authoring", spy)
    config = parse(SETUP + "  authoring: classifier\n")
    cli._proposer_for_delegate(config, source_map(config))
    assert seen == ["classifier"]
