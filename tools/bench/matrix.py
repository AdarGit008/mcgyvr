"""The condition matrix, as data rather than as arguments a runner improvises.

Issue: `#113 <https://github.com/AdarGit008/mcgyvr/issues/113>`_. The matrix
itself is ``tools/bench/matrix.json``; this module loads it, holds it to its own
rules, and applies a cell's levers to a dispatch.

**Why the matrix is data.** A condition that lives as a string constant in a
runner is a condition nobody can enumerate, diff, or point a second consumer at.
#233 consumes this matrix for baseline + singles + all-on and then leave-one-out;
if the runner owned the list, #233 would need a second format and the two would
drift. The engine reads the cells; it does not know them.

**Why a lever declares a slot.** ``noscaffold`` and ``planonly`` both rewrite
``target_content``. Applied together the result depends on which ran last, and an
order-dependent cell is not a condition — it is a bug with a name. Declaring the
one thing a lever writes makes the conflict checkable at load rather than
discoverable in a measurement, and it is what lets a multi-lever cell be
first-class instead of a corner case.

**Why the message stage re-costs the prompt.** A ``message`` lever edits the
rendered user message after assembly, so the token count computed during
assembly no longer describes what was sent. #113 asks for a cost axis beside
pass rate; a stale count would make an ablation that *removes* text look free.
The prompt is re-costed with the same estimator and re-checked against the same
ceiling, which is exactly what ``build_prompt`` does.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
MATRIX_FILE = Path(__file__).resolve().parent / "matrix.json"

CONTRACT = "contract"
MESSAGE = "message"
STAGES = (CONTRACT, MESSAGE)


class MatrixError(Exception):
    """The matrix contradicts its own rules, or a caller named something absent."""


@dataclass(frozen=True)
class Lever:
    """One named transformation of a dispatch."""

    id: str
    stage: str
    slot: str
    what: str
    why: str


@dataclass(frozen=True)
class Cell:
    """One condition: a set of levers, applied to the baseline dispatch."""

    id: str
    levers: tuple[Lever, ...]
    what: str

    @property
    def is_baseline(self) -> bool:
        return not self.levers

    def stage(self, stage: str) -> tuple[Lever, ...]:
        return tuple(lever for lever in self.levers if lever.stage == stage)


@dataclass(frozen=True)
class Matrix:
    """Every declared lever and cell, already checked against the rules."""

    levers: dict[str, Lever]
    cells: dict[str, Cell]

    @property
    def baseline(self) -> Cell:
        for cell in self.cells.values():
            if cell.is_baseline:
                return cell
        raise MatrixError("no baseline cell")  # pragma: no cover — load() checks

    def cell(self, cell_id: str) -> Cell:
        try:
            return self.cells[cell_id]
        except KeyError:
            known = ", ".join(sorted(self.cells))
            raise MatrixError(f"unknown cell {cell_id!r}; declared: {known}") from None

    def singles(self) -> tuple[Cell, ...]:
        """Cells naming exactly one lever — the one-thing-per-axis arms."""
        return tuple(c for c in self.cells.values() if len(c.levers) == 1)

    def single_for(self, lever: Lever) -> Cell | None:
        """The single-lever cell for ``lever``, if the matrix declares one.

        The interaction term is undefined without one for every lever in the
        combined cell, so the report asks before it subtracts.
        """
        for cell in self.singles():
            if cell.levers[0].id == lever.id:
                return cell
        return None


def load(path: Path | None = None) -> Matrix:
    """Read the matrix and hold it to the rules it declares."""
    source = path if path is not None else MATRIX_FILE
    try:
        raw = json.loads(source.read_text())
    except FileNotFoundError:
        raise MatrixError(f"no matrix at {source}") from None
    except json.JSONDecodeError as exc:
        raise MatrixError(f"{source} is not JSON: {exc}") from None

    levers: dict[str, Lever] = {}
    for lever_id, body in raw.get("levers", {}).items():
        stage = body.get("stage")
        if stage not in STAGES:
            raise MatrixError(
                f"lever {lever_id!r} declares stage {stage!r}; "
                f"expected one of {', '.join(STAGES)}"
            )
        if not body.get("slot"):
            raise MatrixError(f"lever {lever_id!r} declares no slot")
        levers[lever_id] = Lever(
            id=lever_id,
            stage=stage,
            slot=body["slot"],
            what=body.get("what", ""),
            why=body.get("why", ""),
        )

    cells: dict[str, Cell] = {}
    for body in raw.get("cells", []):
        cell_id = body.get("id")
        if not cell_id:
            raise MatrixError("a cell declares no id")
        if cell_id in cells:
            raise MatrixError(f"cell {cell_id!r} is declared twice")
        chosen: list[Lever] = []
        seen_slots: dict[str, str] = {}
        for lever_id in body.get("levers", []):
            if lever_id not in levers:
                raise MatrixError(
                    f"cell {cell_id!r} names undeclared lever {lever_id!r}"
                )
            lever = levers[lever_id]
            if lever.slot in seen_slots:
                raise MatrixError(
                    f"cell {cell_id!r} names {seen_slots[lever.slot]!r} and "
                    f"{lever_id!r}, which both write {lever.slot!r}; the cell "
                    "would depend on the order they were applied"
                )
            seen_slots[lever.slot] = lever_id
            chosen.append(lever)
        cells[cell_id] = Cell(
            id=cell_id, levers=tuple(chosen), what=body.get("what", "")
        )

    if not cells:
        raise MatrixError("the matrix declares no cells")
    baselines = [c.id for c in cells.values() if c.is_baseline]
    if len(baselines) != 1:
        raise MatrixError(
            f"exactly one cell must declare no levers; found {len(baselines)}"
            + (f" ({', '.join(baselines)})" if baselines else "")
        )
    return Matrix(levers=levers, cells=cells)


# --- applying a cell -------------------------------------------------------
#
# The two stages are kept apart deliberately. A contract lever changes the task
# the worker is given; a message lever changes only how it is asked. Folding
# them into one hook would make it impossible to say which of those a cell did.


def apply_contract(cell: Cell, contract: Any, *, plan_of: Callable[[str], str]) -> Any:
    """Apply the cell's contract-stage levers, in declaration order.

    ``plan_of`` is injected rather than imported so this module does not depend
    on the runner it serves — the runner owns the scaffold's comment syntax.
    """
    out = contract
    for lever in cell.stage(CONTRACT):
        if lever.id == "noscaffold":
            out = replace(out, target_content="")
        elif lever.id == "planonly":
            out = replace(out, target_content=plan_of(out.target_content))
        else:
            raise MatrixError(
                f"lever {lever.id!r} is declared at the contract stage but the "
                "runner has no implementation for it"
            )
    return out


def strip_output_section(user: str) -> str:
    """Drop the OUTPUT section from a rendered user message.

    ``render_user_message`` joins its sections with a blank line and appends a
    trailing newline, so a section is a paragraph beginning with its own label.
    Matching the label at a paragraph boundary keeps the ablation from reaching
    into a task description that happens to contain the word.
    """
    paragraphs = user.split("\n\n")
    kept = [p for p in paragraphs if not p.startswith("OUTPUT: ")]
    if len(kept) == len(paragraphs):
        raise MatrixError(
            "the rendered message carries no OUTPUT section, so removing it is "
            "a no-op; an ineligible task dilutes the paired test rather than "
            "contributing to it"
        )
    return "\n\n".join(kept)


def apply_message(
    cell: Cell,
    prompt: Any,
    *,
    contract: Any,
    estimate: Callable[[str], int],
    check_fits: Callable[..., Any],
) -> Any:
    """Apply the cell's message-stage levers and re-cost the prompt.

    Returns the prompt unchanged when the cell names no message lever, so the
    baseline path is byte-identical to not calling this at all.
    """
    levers = cell.stage(MESSAGE)
    if not levers:
        return prompt
    user = prompt.user
    for lever in levers:
        if lever.id == "norule":
            user = strip_output_section(user)
        else:
            raise MatrixError(
                f"lever {lever.id!r} is declared at the message stage but the "
                "runner has no implementation for it"
            )
    tokens = estimate(prompt.system + "\n" + user)
    return replace(
        prompt,
        user=user,
        tokens=tokens,
        fit_issue=check_fits(
            tokens, contract.max_input_tokens, counted_by=prompt.counted_by
        ),
    )


# --- the interaction term --------------------------------------------------


@dataclass(frozen=True)
class Interaction:
    """What a multi-lever cell bought over the sum of its singles.

    ``term`` is the quantity #113 asks the report to carry: the combined effect
    minus the sum of the single-lever effects, all measured against the
    baseline. Zero means the levers are additive on this set. Negative means
    they overlap — two levers that fix the same three tasks give +3, not +6,
    which is the arithmetic #233 exists to stop anyone assuming away.
    """

    cell: str
    combined: float
    singles: dict[str, float]
    term: float

    @property
    def additive(self) -> bool:
        return abs(self.term) < 1e-9


def interaction(
    matrix: Matrix, cell_id: str, rate: dict[str, float]
) -> Interaction | None:
    """The interaction term for ``cell_id``, or ``None`` if it is not defined.

    ``rate`` maps cell id to that cell's pass rate. Returns ``None`` — never a
    zero — when the matrix or the run does not carry every part the subtraction
    needs: a missing single is not evidence of additivity.
    """
    cell = matrix.cell(cell_id)
    if len(cell.levers) < 2:
        return None
    base_cell = matrix.baseline
    if base_cell.id not in rate or cell_id not in rate:
        return None

    base = rate[base_cell.id]
    singles: dict[str, float] = {}
    for lever in cell.levers:
        single = matrix.single_for(lever)
        if single is None or single.id not in rate:
            return None
        singles[lever.id] = rate[single.id] - base

    combined = rate[cell_id] - base
    return Interaction(
        cell=cell_id,
        combined=combined,
        singles=singles,
        term=combined - sum(singles.values()),
    )
