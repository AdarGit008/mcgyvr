"""Whether a figure describes one tier or the whole ladder, stated once.

Issue: `#231 <https://github.com/AdarGit008/mcgyvr/issues/231>`_, the sixth
acceptance item — *"Every bench figure states whether it is single-tier or
full-ladder."*

**Why it has to be said out loud.** With escalation live, a floor failure is
rescued by a higher rung and the floor is invisible. A rate of 12.8% and a rate
of 12.8% mean opposite things depending on which of the two produced them: one
says the floor unit solved it, the other says *something* in the ladder did. The
number cannot carry that distinction, so the report must.

**Why a recorded field and not a constant in each report.** Two reports already
printed the sentence as a string literal, and seven other tools that produce
bench figures printed nothing. A literal is a claim the code cannot check: it
stays "single-tier" through the change that adds escalation, and it stays right
by luck until it is silently wrong. So the runner records what it did, and every
report renders that record. ``UNRECORDED`` below is what a manifest written
before the field says, and it is answered rather than guessed at — see
``declare``.

**Why the ladder value exists with nothing producing it.** ADR-0017's P3 says
the floor can move and no tool may hard-code its tier. A vocabulary with one
member is a vocabulary that will be widened by whoever adds the second mode,
under time pressure, in the same change that adds escalation. Declaring both now
costs nothing and makes the addition a data change rather than a design one.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
MEASUREMENTS = REPO / "records" / "measurements"

SINGLE_TIER = "single-tier"
FULL_LADDER = "full-ladder"
MODES = (SINGLE_TIER, FULL_LADDER)

# What a manifest written before #231 carries. The rigs under `tools/` have
# never had an escalation path — neither `tools/breadth/measure.py` nor
# `tools/bundle/measure.py` imports `mcgyvr.escalate` or calls a second worker,
# in any revision — so an absent field is answerable from the code rather than
# from the date, and `declare` answers it instead of refusing to describe a
# measurement that is on disk and readable.
UNRECORDED = None


class ModeError(Exception):
    """A manifest declares a mode this project does not have."""


def of(manifest: Mapping[str, Any]) -> str:
    """The recorded mode, or the single-tier default a pre-#231 manifest implies."""
    recorded = manifest.get("mode", UNRECORDED)
    if recorded is UNRECORDED:
        return SINGLE_TIER
    if recorded not in MODES:
        raise ModeError(
            f"the manifest declares mode {recorded!r}, which is not one of "
            f"{', '.join(MODES)}; a figure whose mode cannot be read cannot say "
            "whether it describes the floor or the ladder"
        )
    return str(recorded)


def declare(manifest: Mapping[str, Any]) -> str:
    """The one-line mode declaration a report puts above its figures."""
    mode = of(manifest)
    if mode == FULL_LADDER:
        return (
            f"- mode: **{FULL_LADDER}** — escalation is live, so a rate below is "
            "the ladder's and not any one tier's; a floor failure rescued by a "
            "higher rung is counted as a pass here"
        )
    line = (
        f"- mode: **{SINGLE_TIER}** — one model, no escalation, so every figure "
        "below is that tier's own and not the ladder's"
    )
    if manifest.get("mode", UNRECORDED) is UNRECORDED:
        line += (
            " (not recorded in this manifest; the rig that wrote it had no"
            " escalation path)"
        )
    return line


def read(*cells: Path | str) -> list[dict[str, Any]]:
    """Every ``run.json`` behind a figure, given the cell directories it reads.

    A cell may be named as a path — absolute, or relative to the working
    directory as ``--run`` arguments arrive — or as a bare ``run/arm`` string
    resolved under ``records/measurements``. The campaign's tools carry cells in
    both shapes (``ablation_report`` takes a ``--run`` path and walks
    ``run/condition/arm``; ``null`` names its runs by directory name and walks
    ``run/arm``), and a helper that accepted only one of them would be adopted
    by half of them.

    A missing manifest is skipped rather than raised on. These tools are read
    over run directories a reader may hold only part of, and the declaration
    states what *was* found; refusing to print a figure because one of four
    provenance files is absent would trade a real answer for a tidy one.
    """
    found = []
    for cell in cells:
        base = Path(cell)
        for candidate in (base / "run.json", MEASUREMENTS / base / "run.json"):
            if candidate.is_file():
                found.append(json.loads(candidate.read_text(encoding="utf-8")))
                break
    return found


def banner(found: Iterable[Mapping[str, Any]]) -> str:
    """The mode declaration for a figure read across several run directories.

    Refuses a mixture. A table drawn half from single-tier runs and half from
    ladder runs has no single answer to "is this the floor's rate?", and the
    honest response to that is to stop, not to print whichever mode came first.
    """
    found = list(found)
    if not found:
        return (
            f"- mode: **{SINGLE_TIER}** — no manifest was read for this figure; "
            "no rig in this tree escalates, so the claim is the code's and not "
            "this run's"
        )
    modes = {of(m) for m in found}
    if len(modes) > 1:
        raise ModeError(
            f"this figure is drawn across {', '.join(sorted(modes))} runs. A "
            "rate pooled over both answers neither question: whether the floor "
            "unit solved these tasks, or whether the ladder did."
        )
    return declare(found[0] if any(m.get("mode") for m in found) else {})
