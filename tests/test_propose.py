"""The proposal turns what running servers list into rungs, and judges nothing.

A stranger's install is bound to what its servers list: one rung per listed
model, in the order the sources come and each source's own listing order, named
by what it is. A listing that would mint a name already taken is not bound and
is named; so is an id that cannot be written into a setup. The proposal reads
no table and no card, so these run on sources taken from the invented machines
of :mod:`tests.machine_shapes`.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from mcgyvr import detect
from mcgyvr import propose as propose_module
from mcgyvr.initialize import _sources_for
from mcgyvr.propose import (
    API,
    NO_BACKEND_NOTE,
    AvailableSource,
    binding_name,
    propose,
)
from tests.machine_shapes import Shape, detection, shape, shapes, with_server

KINDS = tuple(kind for kind, _, _ in detect.PORT_CONVENTIONS)


def _sources(machine: Shape, *reached: Shape) -> list[AvailableSource]:
    return _sources_for(detection(machine, reached=reached))


def _two_servers() -> Shape:
    """A machine here with two servers, each listing two invented models."""
    machine = with_server(
        shape("one-card"),
        kind=KINDS[1],
        models=("example-model-large", "example-model-small"),
    )
    return with_server(
        machine, kind=KINDS[0], models=("example-model-medium", "example-model-tiny")
    )


# --- one rung per listed model, in the order found -------------------------


def test_every_listed_model_is_one_rung_in_the_order_found() -> None:
    sources = _sources(_two_servers())
    proposal = propose(sources=sources)
    assert [(r.source, r.model) for r in proposal.rungs] == [
        (s.name, m) for s in sources for m in s.models_present
    ]


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_a_rung_is_never_a_model_its_source_does_not_list(machine: Shape) -> None:
    sources = {s.name: s for s in _sources(machine)}
    for rung in propose(sources=list(sources.values())).rungs:
        assert sources[rung.source].has(rung.model)
        assert rung.host == sources[rung.source].host


def test_a_rung_on_another_machine_carries_that_machines_host() -> None:
    far = [
        dataclasses.replace(
            machine,
            servers=tuple(
                dataclasses.replace(server, models=(f"example-model-{i}-{j}",))
                for j, server in enumerate(machine.servers)
            ),
        )
        for i, machine in enumerate(m for m in shapes() if not m.local and m.servers)
    ]
    proposal = propose(sources=_sources(far[0], *far[1:]))
    assert {r.host for r in proposal.rungs} == {m.host for m in far}


def test_the_sources_order_is_the_rungs_order() -> None:
    sources = _sources(_two_servers())
    forward = [r.model for r in propose(sources=sources).rungs]
    backward = [r.model for r in propose(sources=sources[::-1]).rungs]
    assert forward != backward
    assert sorted(forward) == sorted(backward)


# --- names ------------------------------------------------------------------


def test_rungs_are_named_by_what_they_are() -> None:
    """`<locality>_<model>` — a name that survives inserting a rung."""
    proposal = propose(sources=_sources(_two_servers()))
    assert [r.name for r in proposal.rungs] == [
        binding_name(r.model) for r in proposal.rungs
    ]
    assert all(r.name.startswith("local_") for r in proposal.rungs)


def test_binding_names_are_safe_to_use_as_config_keys() -> None:
    """A model id is not a name: it carries colons and path separators."""
    assert binding_name("example-model:7b") == "local_example-model-7b"
    assert binding_name("Org/Example-Model-14B-AWQ") == "local_example-model-14b-awq"
    assert binding_name("claude-opus-5", locality=API) == "api_claude-opus-5"


def test_a_tier_name_carries_no_role_token() -> None:
    """The role is derived from where a binding sits, never spelled in a name.

    Only ladder tiers carry a name, and the ladder holds workers only — so a
    role token would be constant everywhere it appeared. This is the
    regression guard for that being re-added.
    """
    assert not hasattr(propose_module, "ORCHESTRATOR")
    assert not hasattr(propose_module, "WORKER")
    assert "role" not in inspect.signature(binding_name).parameters


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_rung_names_are_unique_within_a_proposal(machine: Shape) -> None:
    """The config loader rejects duplicate unit names, so this must hold."""
    served = with_server(
        machine,
        kind=next(k for k in KINDS if k not in {s.kind for s in machine.servers}),
        models=("org-a/example-model-twin", "org-b/example-model-twin"),
    )
    names = [r.name for r in propose(sources=_sources(served)).rungs]
    assert len(names) == len(set(names))


# --- what is not bound is named ----------------------------------------------


def test_a_second_listing_of_a_taken_name_is_not_bound_and_is_named() -> None:
    machine = with_server(
        shape("one-card"), kind=KINDS[0], models=("org-a/example-model-twin",)
    )
    machine = with_server(machine, kind=KINDS[1], models=("org-b/example-model-twin",))
    sources = _sources(machine)
    proposal = propose(sources=sources)
    assert [r.model for r in proposal.rungs] == ["org-a/example-model-twin"]
    reason = proposal.why("org-b/example-model-twin")
    assert reason is not None
    assert reason in proposal.notes
    for said in (
        "org-a/example-model-twin",
        "org-b/example-model-twin",
        binding_name("org-a/example-model-twin"),
        sources[0].name,
        sources[1].name,
    ):
        assert said in reason


@pytest.mark.parametrize("model", ["", "   ", "example\nmodel", "example\tmodel"])
def test_an_id_a_setup_cannot_carry_is_not_bound_and_is_named(model: str) -> None:
    machine = with_server(
        shape("one-card"), kind=KINDS[0], models=(model, "example-model-small")
    )
    proposal = propose(sources=_sources(machine))
    assert [r.model for r in proposal.rungs] == ["example-model-small"]
    reason = proposal.why(model)
    assert reason is not None and repr(model) in reason
    assert reason in proposal.notes


# --- nothing listed is coherent, not an error --------------------------------


def test_no_backend_yields_an_empty_local_ladder_rather_than_an_error() -> None:
    proposal = propose(sources=[])
    assert proposal.is_local_empty
    assert proposal.rungs == ()
    assert proposal.notes == (NO_BACKEND_NOTE,)


def test_a_server_that_lists_nothing_yields_an_empty_ladder_and_no_note() -> None:
    """Nothing was bound, so there is no unit for a note to speak of."""
    machine = with_server(shape("one-card"), kind=KINDS[0], models=())
    proposal = propose(sources=_sources(machine))
    assert proposal.is_local_empty
    assert proposal.notes == ()


# --- the concurrency note ----------------------------------------------------


def test_the_proposal_warns_a_number_does_not_make_a_server_parallel() -> None:
    """CON-02, stated where the operator will read it.

    The failure it warns about is the invisible kind — a single-slot server
    handed four concurrent requests serializes them rather than refusing them,
    so an over-declared capacity is a queue rather than an error.
    """
    sources = _sources(_two_servers())
    notes = " ".join(propose(sources=sources).notes)
    assert "CON-02" in notes
    assert "parallel-slot setting" in notes
    assert "serializes" in notes
    # It names the sources whose backends the operator would have to change.
    for source in sources:
        assert source.name in notes


@pytest.mark.parametrize(
    "sources",
    [[], _sources(with_server(shape("one-card"), kind=KINDS[0], models=()))],
    ids=["no-source", "a-source-listing-nothing"],
)
def test_a_machine_with_no_ladder_gets_no_concurrency_advice(
    sources: list[AvailableSource],
) -> None:
    """Nothing to run concurrently on: the note would be advice about nothing."""
    notes = propose(sources=sources).notes
    assert not any("CON-02" in note for note in notes)
    assert not any(" on ," in note or note.endswith(" on ") for note in notes)


def test_the_proposal_is_deterministic() -> None:
    """Same inputs, same ladder — a proposal that wobbles cannot be reviewed."""
    sources = _sources(_two_servers())
    runs = [propose(sources=sources) for _ in range(5)]
    assert all(run == runs[0] for run in runs)
