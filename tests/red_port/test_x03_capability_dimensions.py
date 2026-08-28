"""X03 — a task asks for a *capability*, and a model is chosen on that capability.

mcgyvr's capability table is the best rate card in either project: measured
HumanEval+ pass@1, tok/s and VRAM, each carried with the backend and rig that
produced it, and invalidated measurements kept rather than quietly replaced by an
estimate. What it carries per model is one number. So the only question mcgyvr can
ask about a model today is "how good is it", and the only comparison it can make is
a total order.

That is the wrong shape for the decision. A model that writes a clean docstring and
a model that gets a loop invariant right are not two points on one line, and a
ladder that ranks them on one line will send an algorithm contract to whichever
model happened to score higher on a benchmark that is mostly short functions. The
lever is not "add more numbers": it is that **the task type says which capability it
needs**, and selection filters on that capability rather than on the scalar.

Four statements, and the last two are the ones that keep this from being a
regression:

* A task type names a dimension, and two task types that ask for different things
  name different ones. Asserted with a third clause — that the dimension is not
  simply the task type's own name — because a "dimension" that is one-per-task-type
  is not a dimension at all: it would demand a measured score per task type, which
  is a table nobody has, and it would make the filter a synonym for the routing key
  it is supposed to refine.
* Selection excludes a model that is strong overall and weak on what was asked for.
  This is the whole point, and it is asserted on the *identity* of what was chosen
  rather than on a count, because a filter that returned both candidates in the
  wrong order would pass a length check.
* A model with **no** capability vector is judged on its scalar quality instead of
  being excluded. Not a nicety — every model in ``data/capability-table.json`` ships
  without a vector today, so a filter that treats "no data" as "fails the floor"
  empties the pool on the day it lands and makes every install unroutable. local-ai
  gets this right (``m.capabilities.get(dim, m.quality)``) and it is the easiest
  half to drop.
* When nothing meets the dimension, the refusal names the dimension. An operator
  told "no model is good enough" cannot act; one told which capability came up short
  can bind a rung that has it. A refusal that only said "no candidates" would pass a
  test asserting merely that the call failed, so the dimension is asserted by name.

The fixture writes its own table rather than using the shipped one, because the
shipped one has no vectors and this is about what happens when it does. It is
written from the dimension the *code* names, not from a dimension this test invents:
a test that hard-coded ``"algorithm"`` would be asserting local-ai's vocabulary
rather than mcgyvr's.

The table is handed over as a **path**. Today's :func:`mcgyvr.capability.load`
drops any key it does not know, so a vector would not survive it; handing the
loaded object over would mean asserting a filter against data the loader had
already thrown away, and the test would go green on a port that never read the
vectors at all.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tests.red_port.conftest import required

DIMENSION = "say which capability dimension a task type needs"
SELECT = (
    "choose a worker model by the capability dimension a task needs, not by a scalar"
)

# Two types from mcgyvr's own vocabulary that plainly ask for different things:
# one must produce logic that works, the other must produce prose over logic it
# is forbidden to change (`no_semantic_change` is its required evidence).
LOGIC = "function_implementation"
PROSE = "docstring"


def _dimension() -> Any:
    return required(
        DIMENSION,
        lambda: (
            __import__("mcgyvr.capability", fromlist=["dimension_for"]).dimension_for
        ),
    )


def _select() -> Any:
    return required(
        SELECT,
        lambda: (
            __import__(
                "mcgyvr.capability", fromlist=["select_for_task"]
            ).select_for_task
        ),
    )


def _model(
    model_id: str, quality: float, capabilities: dict[str, float] | None
) -> dict[str, Any]:
    """One table row, complete enough for the shipped loader to accept it."""
    row: dict[str, Any] = {
        "id": model_id,
        "family": "fixture",
        "params_b": 7.0,
        "quant": "q4_K_M",
        "weights_gb": 4.0,
        "vram_gb_working": 5.0,
        "quality": [
            {
                "humaneval_plus_pass1": quality,
                "backend": "ollama",
                "rig": "rig_a",
                "date": "2026-08-28",
            }
        ],
        "throughput_tok_s": [
            {"value": 60.0, "backend": "ollama", "rig": "rig_a", "date": "2026-08-28"}
        ],
        "notes": "fixture row",
    }
    if capabilities is not None:
        row["capabilities"] = capabilities
    return row


def _table(tmp_path: Path, *models: dict[str, Any]) -> Path:
    path = tmp_path / "capability-table.json"
    path.write_text(
        json.dumps({"schema_version": 1, "models": list(models)}), encoding="utf-8"
    )
    return path


def _refusal(call: Callable[[], Any]) -> str:
    """What a refusal said, however it was expressed.

    A refusal may be raised or returned; which one is the port's choice and not a
    behavior. What is a behavior is that it says something, and what it says is
    what these tests read.
    """
    try:
        answer = call()
    except Exception as refused:
        return str(refused)
    reason = getattr(answer, "reason", None)
    return str(answer) if reason is None else str(reason)


def test_a_task_type_names_the_capability_it_needs() -> None:
    """Two tasks that ask for different things ask for different capabilities.

    The third assertion is the load-bearing one. A mapping that returned the task
    type's own name would satisfy the first two and would still leave selection
    with nothing to filter on, because no measurement exists per task type.
    """
    dimension_for = _dimension()

    logic, prose = dimension_for(LOGIC), dimension_for(PROSE)

    assert logic, f"{LOGIC!r} names no capability dimension"
    assert prose, f"{PROSE!r} names no capability dimension"
    assert logic != prose, (
        f"{LOGIC!r} and {PROSE!r} both ask for {logic!r}: writing working logic and "
        f"writing prose about logic are not the same capability, and a mapping that "
        f"collapses them cannot change any routing decision"
    )
    assert {logic, prose}.isdisjoint({LOGIC, PROSE}), (
        f"the dimension is the task type's own name ({logic!r}, {prose!r}): a "
        f"dimension per task type is not a dimension, it is the routing key again, "
        f"and it would need a measured score per task type to filter on"
    )


def test_a_model_strong_overall_but_weak_on_the_dimension_is_not_chosen(
    tmp_path: Path,
) -> None:
    """The scalar leader loses to the model that can do the thing that was asked."""
    dimension = _dimension()(LOGIC)
    table = _table(
        tmp_path,
        _model("scalar-leader", quality=0.82, capabilities={dimension: 0.08}),
        _model("dimension-fit", quality=0.61, capabilities={dimension: 0.79}),
    )

    chosen = _select()(task_type=LOGIC, table=table)

    assert getattr(chosen, "id", None) == "dimension-fit", (
        f"a {LOGIC!r} contract needs {dimension!r} and went to "
        f"{getattr(chosen, 'id', chosen)!r}: 'scalar-leader' is ahead on overall "
        f"quality and hopeless at the one thing this task requires, which is the "
        f"whole difference between a scalar and a dimension"
    )


def test_a_model_with_no_capability_vector_falls_back_to_its_scalar_quality(
    tmp_path: Path,
) -> None:
    """No vector means unmeasured, not unfit.

    Every row in the shipped table is in exactly this state, so a filter that reads
    a missing vector as a failed floor takes the whole pool out on the day it lands.
    """
    dimension = _dimension()(LOGIC)
    table = _table(
        tmp_path,
        _model("no-vector", quality=0.74, capabilities=None),
        _model("vectored-but-weak", quality=0.30, capabilities={dimension: 0.09}),
    )

    chosen = _select()(task_type=LOGIC, table=table)

    assert getattr(chosen, "id", None) == "no-vector", (
        f"a model with no {dimension!r} score was passed over for "
        f"{getattr(chosen, 'id', chosen)!r}: an absent vector is missing data, and "
        f"the table ships with none at all, so treating it as a failed floor leaves "
        f"nothing to route to"
    )


def test_when_nothing_meets_the_dimension_the_refusal_names_it(tmp_path: Path) -> None:
    """An operator can bind a rung for a named capability; they cannot act on 'no'.

    Asserted on the dimension by name rather than on the refusal merely happening,
    because "no model is good enough" is the answer that sends someone to read the
    ladder they already read.
    """
    dimension = _dimension()(LOGIC)
    table = _table(
        tmp_path,
        _model("weak-a", quality=0.55, capabilities={dimension: 0.05}),
        _model("weak-b", quality=0.58, capabilities={dimension: 0.07}),
    )

    said = _refusal(lambda: _select()(task_type=LOGIC, table=table))

    assert dimension in said, (
        f"the refusal does not name {dimension!r}, so an operator cannot tell which "
        f"capability to go and bind a rung for. It said: {said!r}"
    )
