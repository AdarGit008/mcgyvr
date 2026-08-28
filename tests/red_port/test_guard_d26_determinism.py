"""D26 — the same inputs give the same answer, on a busy machine and on a quiet one.

GREEN by design. The system being ported over sends no seed and takes sampling
variance as the cost of doing business. That is a decision mcgyvr made the other
way, and the three places it shows are the three places a port would undo it
without noticing, because in each of them the weaker behaviour is the one that
falls out of writing the obvious code.

* **Order.** ``src/mcgyvr/capacity.py:463`` returns batch results in input order
  "whatever order they finished in — a batch whose results were ordered by
  completion would be reproducible only on a quiet machine." ``as_completed`` is
  the loop everyone writes first, and it is also the v2 ``main_out_queue``'s
  natural delivery order, so this one is under active pressure rather than
  hypothetically at risk.
* **Identity.** A contract id drawn from a clock, a counter or a path would make
  every run's records incomparable with the last one's, and would turn the
  duplicate refusal into an ordinal nobody reads.
* **Cost of looking.** ``plan()`` and ``ascent()`` being pure is what lets a plan
  be inspected, diffed and ranked before a token is spent. A single lazy probe
  added inside either — a health check, a token count over a file — takes that
  away silently, because the function still returns the same thing.

Each test is one level up from what already exists.
``tests/test_capacity.py`` pins input order using staggered sleeps, which is an
observation about a machine rather than a proof: on a loaded box the sleeps can
land in submission order and the test passes without the inversion ever having
happened. This one forces strict reverse completion with a chain of events and
asserts the inversion occurred.
``tests/test_orchestrator_decompose.py`` pins the id against two calls over one
index, which cannot see an id that had picked up the repository's path or the
index object's identity. This one builds two repositories, in two directories,
and asserts they agree.
Nothing anywhere asserts that planning is free, so the last test installs a guard
that makes files, sockets and processes raise, and runs the pure path under it.
"""

from __future__ import annotations

import io
import socket
import subprocess
import threading
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.capacity import Capacity, run_batch
from mcgyvr.catalog import catalog
from mcgyvr.config import parse as parse_config
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.escalate import Assurance, Delivered, Judgement, ascent, escalate
from mcgyvr.orchestrator.decompose import DepRef, Proposal, RecordedProposer, decompose
from mcgyvr.orchestrator.index import build_index
from mcgyvr.pool import Endpoint, Protocol, SourceMap, source_map
from mcgyvr.route import Try, Verdict, plan
from tests.red_port.conftest import CONTRACT, git

CONFIG = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 3
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
    - name: local_qwen-14b
      source: workstation
      model: qwen2.5-coder:14b
"""

WORKSTATION = Endpoint(
    source="workstation",
    base_url="http://localhost:11434",
    protocol=Protocol.OLLAMA,
    max_parallel=3,
    credential_env=None,
)

PROPOSAL = Proposal(
    task_type="docstring",
    task="Document listing() and say how it pages its items.",
    target="listing.py",
    deps=(DepRef(path="pagination.py", symbol="paginate"),),
    stop_conditions=("The pager's contract is ambiguous.",),
)


def test_batch_results_come_back_in_input_order_when_completion_order_is_the_reverse(
    tmp_path: Path,
) -> None:
    """The inversion is forced, not hoped for, and it is asserted to have happened.

    Each job waits on its own event and releases its predecessor's, so the last
    job submitted is the first that can finish and the first submitted is the
    last. No sleeps: on any machine, at any load, completion runs backwards.

    Both orders are then asserted. The completion list is what makes the result
    list mean anything — without it, a batch that had switched to delivering by
    completion would pass on a machine where the jobs happened to finish in
    submission order, which is precisely the "reproducible only on a quiet
    machine" failure the module set out to avoid.

    The capacity is held inside each job rather than skipped, so the ordering is
    pinned on the real path a dispatching batch takes and not on a bare thread
    pool that happens to share a function name with it.
    """
    capacity = Capacity({"workstation": 3}, lock_dir=tmp_path / "capacity-locks")
    gates = [threading.Event() for _ in range(3)]
    finished: list[str] = []
    record = threading.Lock()

    def job_for(index: int) -> Any:
        def job(held: Capacity) -> str:
            with held.hold(WORKSTATION):
                assert gates[index].wait(timeout=30), f"job {index} was never released"
            if index:
                gates[index - 1].set()
            with record:
                finished.append(f"job-{index}")
            return f"job-{index}"

        return job

    gates[2].set()  # the last job submitted is the first one allowed to finish
    outcomes = run_batch([job_for(0), job_for(1), job_for(2)], capacity, workers=3)

    assert all(o.ok for o in outcomes), [o.error for o in outcomes if not o.ok]
    assert finished == ["job-2", "job-1", "job-0"], (
        f"the completion order was not inverted, so this proved nothing: {finished}"
    )
    assert [o.value for o in outcomes] == ["job-0", "job-1", "job-2"]
    assert [o.index for o in outcomes] == [0, 1, 2]


def test_the_same_work_in_two_different_repositories_gets_the_same_contract_id(
    tmp_path: Path,
) -> None:
    """Two checkouts, two directories, two indexes, one id.

    The existing repeatability test calls the decomposer twice over one index, so
    an id that had quietly folded in the repository's absolute path, the index
    object's identity, or the moment of the build would still come out equal.
    Here the only thing the two runs share is the work itself.

    The whole emitted document is compared as well as the id. An id derived from
    the work while some other field carried the clock would leave two runs of the
    same prompt producing records that cannot be diffed — which is the reason the
    id is stable in the first place, not an end in itself.
    """

    def a_repository(where: Path) -> Any:
        where.mkdir()
        (where / "pagination.py").write_text(
            "def paginate(items: list[int], size: int = 10) -> list[int]:\n"
            "    return items[:size]\n"
        )
        (where / "listing.py").write_text(
            "from pagination import paginate\n\n\ndef listing(items):\n    return "
            "items\n"
        )
        git(where.parent, "init", "-q", str(where))
        git(where, "config", "user.email", "test@example.invalid")
        git(where, "config", "user.name", "test")
        git(where, "add", "-A")
        git(where, "commit", "-qm", "base")
        return decompose(
            build_index(where),
            "the listing pager",
            propose=RecordedProposer((PROPOSAL,)),
        )

    here = a_repository(tmp_path / "here")
    there = a_repository(tmp_path / "there")

    (one,) = here.contracts
    (two,) = there.contracts
    assert one.id == two.id, "the contract id depends on where the repository sits"
    assert one.id.startswith("docstring-"), f"the id does not name its work: {one.id}"
    assert here.documents == there.documents, (
        "the emitted document is not a function of the work"
    )


@pytest.fixture
def routing_inputs() -> tuple[Any, SourceMap, Contract]:
    """Config, pool and contract, all built before any guard is installed."""
    config = parse_config(CONFIG)
    return config, source_map(config), load_contract(CONTRACT)


def test_planning_and_ascent_spend_nothing_and_answer_the_same_twice(
    routing_inputs: tuple[Any, SourceMap, Contract], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plan can be looked at for free, and looking twice shows the same thing.

    The guard is behavioural rather than a call count: files, sockets and
    subprocesses are made to raise, so a probe added inside either function fails
    the test by happening. The catalog is read once per process and cached, so it
    is warmed first — otherwise the very first test to touch it would fire the
    guard honestly and report the wrong culprit.

    Repeated-call equality is asserted alongside, and it is the half that keeps
    the guard honest: a monkeypatch that had silently stopped applying would leave
    a purity test passing on its own, while an unstable plan would still be
    caught here. The ascent is included because it is what a caller inspects
    before funding anything, and the escalation is driven with a constructed
    attempt so nothing but the routing itself is exercised.
    """
    config, pool, contract = routing_inputs
    catalog()  # the one legitimate read, cached for the process, warmed deliberately

    def refuse(name: str) -> Any:
        def guard(*args: object, **kwargs: object) -> Any:
            raise AssertionError(f"{name} was reached; planning must spend nothing")

        return guard

    def attempt(this: Try) -> Judgement[str]:
        return Judgement(
            verdict=Verdict.PASSED,
            value=f"{this.rung.name}#{this.attempt}",
            assurance=Assurance.UNVERIFIED,
        )

    monkeypatch.setattr(socket, "socket", refuse("socket.socket"))
    monkeypatch.setattr(subprocess, "Popen", refuse("subprocess.Popen"))
    monkeypatch.setattr(io, "open", refuse("io.open"))
    monkeypatch.setattr("builtins.open", refuse("open"))
    try:
        plans = (plan(config, pool, contract), plan(config, pool, contract))
        ascents = (ascent(config, pool, contract), ascent(config, pool, contract))
        climbs = (
            escalate(config, pool, contract, attempt),
            escalate(config, pool, contract, attempt),
        )
    finally:
        # Undone before asserting: a failure report reads source files, and a
        # guard still standing would replace the real message with its own.
        monkeypatch.undo()

    assert plans[0] == plans[1], "planning twice gave two different plans"
    assert plans[0].rungs == ("local_qwen-7b", "local_qwen-14b"), plans[0].rungs
    assert ascents[0] == ascents[1], "the ascent is not a function of its inputs"
    assert climbs[0] == climbs[1], (
        "the same ladder and the same attempt gave two answers"
    )
    delivered = climbs[0]
    assert isinstance(delivered, Delivered), f"the climb did not deliver: {delivered}"
    assert delivered.value == "local_qwen-7b#1", delivered
