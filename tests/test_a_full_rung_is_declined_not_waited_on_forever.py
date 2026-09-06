"""A rung whose slots are all taken is declined, not waited on forever.

:meth:`~mcgyvr.capacity.Capacity.hold` blocks by default, and that default is
right for a batch inside one process: a queue is a legitimate wait, and the
kernel gives a crashed holder's slot back. It is the wrong default for a
command a person or an agent is waiting on. ``budgets.task_timeout_s`` has
bounded a task's wall clock in the schema since it was written and was read by
nothing, so an unbounded queue would have had no ceiling anywhere in the
product: no output, no timeout, nothing to stop it.

So a wait is bounded by the task's own ceiling, and running out of it is a
*decline* rather than a failure. That is not a new idea here — it is exactly
what :mod:`mcgyvr.cooldown` already does one branch above, and for the same
reason: a rung that was never tried produced no verdict, spent no attempt and
funded no escalation, so a climb walks past it to a rung that has room. A
saturated cheap rung sending work to a free dearer one is the behaviour
``ladder.fanout: idle`` was written for and could never reach.

The distinction the code has to keep is between two things one exception used
to say. "Every slot is busy" is a fact about right now and is a decline. "This
capacity does not bound that source" is a fact about two configs disagreeing
and must still raise, because declining it would route around a mistake
instead of naming it.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tests import livejournal as lj

ONE_WIDE = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: openai
    max_parallel: 1
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
budgets:
  task_timeout_s: 1
"""


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    (tmp_path / "rendezvous").mkdir(exist_ok=True)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "rendezvous"))
    return tmp_path / "home"


def test_a_rung_whose_only_slot_is_taken_is_declined_within_the_task_ceiling(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.capacity import Capacity
    from mcgyvr.config import load

    config_path = tmp_path / "mcgyvr.yaml"
    journal = tmp_path / "journal"
    config_path.write_text(ONE_WIDE + f"journal:\n  dir: {journal}\n", encoding="utf-8")
    repo = lj.make_repo(tmp_path / "repo")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    def unreached(model: str, request: Any) -> Any:
        raise AssertionError("the dispatch was made although no slot was free")

    lj.patch_backend(monkeypatch, unreached)

    # Somebody else holds the one slot this source declares, for longer than
    # the run's whole ceiling. The slot file is the rendezvous, so this stands
    # in for the other mcgyvr process the bound exists to keep out.
    holder = Capacity.of(load(config_path))
    released = threading.Event()
    took = threading.Event()

    def occupy() -> None:
        with holder.hold("workstation"):
            took.set()
            released.wait(timeout=30)

    keeper = threading.Thread(target=occupy, daemon=True)
    keeper.start()
    assert took.wait(timeout=10), "the stand-in holder never took the slot"

    try:
        started = time.monotonic()
        code = lj.main(lj.run_args(contract, repo, config_path))
        waited = time.monotonic() - started
    finally:
        released.set()
        keeper.join(timeout=10)

    assert waited < 25, (
        f"the run waited {waited:.1f}s for a slot nobody was going to free "
        "within its ceiling: an unbounded queue has no timeout anywhere in "
        "the product, so a saturated ladder hangs with no output"
    )
    assert code == 1
    out = capsys.readouterr().out
    result = json.loads(lj.result_path(out).read_text())
    assert result["outcome"] == "declined_throughout", result["outcome"]
    # The reason lives on the attempt, which is where a caller reads why one
    # rung did what it did; the summary above it speaks for the whole ladder.
    (declined,) = result["attempts"]
    assert declined["verdict"] == "declined", declined
    assert "no free slot" in declined["detail"], declined["detail"]


def test_a_busy_rung_is_not_learned_from_as_a_source_that_failed() -> None:
    """A queue is not a fault, so the cooldown must not be able to see one.

    :mod:`mcgyvr.cooldown` learns from ``RunnerError`` — a source that
    answered and generated badly. A source that is merely busy has answered
    nothing, and marking it unavailable would take a rung out of the ladder
    for being popular.
    """
    from mcgyvr.capacity import SlotUnavailableError
    from mcgyvr.runner import RunnerError

    assert not issubclass(SlotUnavailableError, RunnerError)


def test_a_capacity_that_does_not_bound_the_source_still_raises(
    tmp_path: Path, home: Path
) -> None:
    """A config disagreement is named, not declined around."""
    from mcgyvr.capacity import Capacity, CapacityError, SlotUnavailableError
    from mcgyvr.config import load

    config_path = tmp_path / "mcgyvr.yaml"
    config_path.write_text(ONE_WIDE, encoding="utf-8")
    capacity = Capacity.of(load(config_path))

    with (
        pytest.raises(CapacityError) as caught,
        capacity.hold("a-source-this-config-never-declared"),
    ):
        pass
    assert not isinstance(caught.value, SlotUnavailableError), (
        "a source the capacity does not bound was reported as a busy slot: "
        "a climb would route around two configs disagreeing instead of "
        "naming it"
    )
