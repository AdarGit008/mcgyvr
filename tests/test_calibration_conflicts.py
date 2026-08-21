"""Six recorded conflicts, and the check each one becomes.

Session 6 read the D7 campaign's evidence and counted six contradictions
between what the record claims and what the files under
``records/evidence/calibration-*`` hold. All six were re-derived at
``d4d6b8c1``: **four survive, two dissolve.** Before this file nothing read any
of them — ``grep -rl xfail tests`` found nothing at filing, and the only
guards over the campaign's journals were the disposition tables beside the
sinks, which account for the FIELDS of a row and say nothing about the VALUES
inside it. That is why the session record could say of one of these that it
"would not be caught today".

ADR-0037 (#323) is the rule this file is the first real member of:

* Rule 1 — a finding is a check, not a paragraph. Red means the defect is
  present; "is this still open?" is answered by running the suite.
* Rule 2 — a finding the owner has not ruled on keeps its check, marked
  ``xfail(strict=True, reason=...)`` with a dated reason: the ISO date, then
  ``owed — <the question>`` while the owner has not ruled and
  ``decided — <the decision>`` once they have. Four of the six are owed.
  ``strict`` is what keeps them live: a campaign that fixes one turns XPASS
  and fails the suite until the marker comes off.
* Rule 3 — the append-only record names its check. The block ``## Conflicts
  recorded 2026-08-21`` in the campaign README carries K1-K6, each naming the
  test below that reads it.

The two that dissolve stay as green checks rather than as a deleted paragraph:
their job is to keep a re-derived non-finding from being re-filed, and to go
red if a later campaign turns either into a real one.

**The population is the newest campaign, not this one.** Every check resolves
its evidence through :func:`campaign` — the newest ``calibration-*`` directory
under ``records/evidence/``. The 2026-08-19 files are frozen history and can
never turn green, so a check pinned to them would be an ``xfail`` that outlives
its own finding and can never XPASS. Pointed at the newest campaign, each of
these is a question put to the NEXT run, which is what every "owed" reason
asks, and the run that answers it flips the marker.

Two checks read wider than the issue that filed them (#328 quotes the narrower
population; the K-lines in the README say so):

* K5 covers both engines rather than ollama alone. A vLLM width matrix quotes
  1.0 against 3.76 for the same model at the same token count, and what
  separates them is ``configured_width`` — so the declared conditions are
  ``tokens`` AND the width, over 227 pairs rather than 27.
* K6 covers every figure-bearing ramp row in the campaign's journals (36),
  not only the twelve of the ramp phase's own journal.
"""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path
from typing import Any, NamedTuple

import pytest

REPO = Path(__file__).resolve().parent.parent
EVIDENCE = REPO / "records" / "evidence"

#: The sampler fields ``serving_semantic_sha256`` pins, in the names both
#: layers use: the digest's ``semantic`` block and a served slot's ``params``.
#: Every one of them decides an emitted token.
SAMPLER_FIELDS: tuple[str, ...] = (
    "temperature",
    "top_k",
    "top_p",
    "min_p",
    "repeat_penalty",
)

#: Floating point read out of two JSON captures of the same C float; the
#: comparison is of configuration, not of arithmetic.
TOLERANCE = 1e-6

#: The name K2 proposes for the context total the child was launched with.
#: ``n_ctx`` is already taken — ``serving_config`` overwrites the parsed ``-c``
#: with the per-slot window off ``/props`` — so the total needs a name of its
#: own or it is not recorded at all. A check that accepted "some key equals the
#: total" would pass on any single-slot host, where the per-slot window IS the
#: total; this one asks for the name.
CONTEXT_TOTAL_KEY = "n_ctx_total"

#: Two ramp figures for the same host, engine and model may disagree only if
#: one of these differs. Both are conditions the harness CHOSE and wrote down,
#: which is what makes a disagreement attributable rather than noise.
DECLARED_CONDITIONS: tuple[str, ...] = ("tokens", "configured_width")

#: How far two speedups may differ before they count as disagreeing, relative
#: to the smaller of the two.
DISAGREEMENT = 0.10

_LAUNCHED_CONTEXT = re.compile(r"(?:^|\s)-c\s+(\d+)")
_LAUNCHED_SLOTS = re.compile(r"(?:^|\s)-np\s+(\d+)")


def campaign(evidence: Path | None = None) -> Path:
    """The newest calibration campaign's evidence directory.

    The directory name is the contract: a campaign lands under
    ``records/evidence/calibration-<ISO date>/``, so the newest sorts last.

    The root is read at call time rather than bound as a default, so a sweep
    can point every check below at a mutated copy of the evidence and watch it
    turn. A check that cannot be shown to reject is the MARKERS table again.
    """
    root = EVIDENCE if evidence is None else evidence
    directories = sorted(p for p in root.glob("calibration-*") if p.is_dir())
    assert directories, f"no calibration campaign under {root}"
    return directories[-1]


def _payload(raw: Any) -> Any:
    """A capture the survey stored as a JSON string, or already parsed."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return raw


class Cell(NamedTuple):
    """One measured (host, model) unit of the survey."""

    host: str
    model: str
    body: dict[str, Any]


def _cells(directory: Path) -> list[Cell]:
    survey = _survey(directory)
    return [
        Cell(host, model, body)
        for host, host_body in survey["hosts"].items()
        for model, body in (host_body.get("measured") or {}).items()
    ]


def _survey(directory: Path) -> dict[str, Any]:
    """The campaign's survey document, found by shape rather than by name."""
    surveys = []
    for path in sorted(directory.glob("*.json")):
        document = _payload(path.read_text(encoding="utf-8"))
        if isinstance(document, dict) and isinstance(document.get("hosts"), dict):
            surveys.append(document)
    assert len(surveys) == 1, (
        f"expected exactly one survey document (a JSON file carrying a host "
        f"map) under {directory}, found {len(surveys)}"
    )
    return surveys[0]


class Served(NamedTuple):
    """One llama-server child, beside the digest that claims to pin it."""

    host: str
    model: str
    port: Any
    command_line: str
    props: dict[str, Any]
    slots: list[dict[str, Any]]
    semantic: dict[str, Any]


def _served(directory: Path) -> list[Served]:
    """Every served child in the campaign, with its cell's semantic pin.

    The pin is per CELL and the children are per instance: a coresident cell
    serves two and digests one configuration for both. Holding every child of a
    cell to that cell's pin is the point — a digest that does not describe one
    of them is the defect, not a mismatched population.
    """
    served = []
    for cell in _cells(directory):
        description = cell.body.get("description") or {}
        semantic = (description.get("serving_config") or {}).get("semantic")
        if not isinstance(semantic, dict):
            continue  # a refused config pins nothing and describes no child
        for instance in (description.get("server") or {}).get("instances") or []:
            props = _payload(instance.get("props"))
            slots = _payload(instance.get("slots"))
            served.append(
                Served(
                    host=cell.host,
                    model=cell.model,
                    port=instance.get("port"),
                    command_line=instance.get("command_line") or "",
                    props=props if isinstance(props, dict) else {},
                    slots=slots if isinstance(slots, list) else [],
                    semantic=semantic,
                )
            )
    return served


class Figure(NamedTuple):
    """One ramp row that carries a speedup — a figure a record can quote."""

    journal: str
    host: str
    engine: str
    model: str
    speedup: float
    row: dict[str, Any]


def _figures(directory: Path) -> list[Figure]:
    """Every figure-bearing ramp row in the campaign's journals.

    A ramp row that raised carries an ``error`` and no ``max_speedup_vs_n1``;
    it is not a figure and no record quotes it.
    """
    figures = []
    for journal in sorted(directory.glob("*.jsonl")):
        for line in journal.read_text(encoding="utf-8").splitlines():
            row = _payload(line.strip()) if line.strip() else None
            if not isinstance(row, dict) or row.get("phase") != "ramp":
                continue
            speedup = row.get("max_speedup_vs_n1")
            if not isinstance(speedup, int | float) or isinstance(speedup, bool):
                continue
            figures.append(
                Figure(
                    journal=journal.name,
                    host=str(row.get("host")),
                    engine=str(row.get("engine")),
                    model=str(row.get("model")),
                    speedup=float(speedup),
                    row=row,
                )
            )
    return figures


# --------------------------------------------------------------------------
# K1 — the sampler pin
# --------------------------------------------------------------------------


def _sampler_disagreements(directory: Path) -> list[tuple[str, str, Any, list[str]]]:
    """Served slots whose params differ from the digest that pins them."""
    disagreeing = []
    for child in _served(directory):
        for slot in child.slots:
            params = slot.get("params")
            if not isinstance(params, dict):
                continue  # a slot the child answered without its sampler
            differ = [
                field
                for field in SAMPLER_FIELDS
                if field in params
                and field in child.semantic
                and abs(float(params[field]) - float(child.semantic[field])) > TOLERANCE
            ]
            if differ:
                disagreeing.append((child.host, child.model, slot.get("id"), differ))
    return disagreeing


def _served_slots(directory: Path) -> int:
    return sum(
        1
        for child in _served(directory)
        for slot in child.slots
        if isinstance(slot.get("params"), dict)
    )


@pytest.mark.xfail(
    strict=True,
    reason="2026-08-21: owed — which layer is serving_semantic_sha256 a pin "
    "of: llama-server's defaults, or the params a request ran under (where a "
    "Modelfile's parameters enter)?",
)
def test_the_sampler_pin_is_the_layer_the_request_ran_under() -> None:
    """K1 — the pinned sampler is not the sampler any request ran under.

    ``serving_config`` digests ``/props``'s ``default_generation_settings``,
    which is llama-server's own default set. Every request this project
    dispatches goes through ollama, whose per-request parameters (and a model's
    ``Modelfile``) decide the values the slot actually holds. On 2026-08-19 the
    two layers disagreed on every served slot: ``top_p``, ``min_p`` and
    ``repeat_penalty`` on 17 of 17, ``temperature`` on 4, ``top_k`` on 1 --
    while the digest was quoted as the pin that made the cells comparable.
    """
    slots = _served_slots(campaign())
    assert slots, "no served slot carries its sampler params; nothing to compare"
    disagreeing = _sampler_disagreements(campaign())
    assert not disagreeing, (
        f"{len(disagreeing)} of {slots} served slots ran under a sampler the "
        f"semantic digest does not describe: {disagreeing}"
    )


# --------------------------------------------------------------------------
# K2 — the launched context total
# --------------------------------------------------------------------------


class Context(NamedTuple):
    host: str
    model: str
    launched: int
    n_ctx: Any
    n_parallel: Any
    total: Any


def _contexts(directory: Path) -> list[Context]:
    """Every child's launched ``-c``, beside what its digest recorded."""
    contexts = []
    for child in _served(directory):
        launched = _LAUNCHED_CONTEXT.search(child.command_line)
        if launched is None:
            continue  # a child launched without an explicit window
        contexts.append(
            Context(
                host=child.host,
                model=child.model,
                launched=int(launched.group(1)),
                n_ctx=child.semantic.get("n_ctx"),
                n_parallel=child.semantic.get("n_parallel"),
                total=child.semantic.get(CONTEXT_TOTAL_KEY),
            )
        )
    return contexts


@pytest.mark.xfail(
    strict=True,
    reason="2026-08-21: owed — is the width split inherited or intended, and "
    "does a cross-host figure refuse it, carry it, or equalise the hosts "
    "first?",
)
def test_the_launched_context_total_has_a_name_in_the_semantic_block() -> None:
    """K2 — the launched window is recoverable by arithmetic and unnamed.

    ``-c`` is the total context the child was launched with and ``-np`` splits
    it into slots. ``serving_config`` parses both off the command line and then
    overwrites ``n_ctx`` with the per-slot window off ``/props``, so the total
    survives only as a product. On 2026-08-19 that product held on 19 of 19
    children and six of them were launched at 8192 rather than 4096 --
    ``OLLAMA_NUM_PARALLEL=2`` in srv1's unit and nothing in srv2's — which is
    a host-configuration difference under a figure the record reads as
    hardware, and the README still calls context "uniform at 4096".
    """
    contexts = _contexts(campaign())
    assert contexts, "no served child records the window it was launched with"
    unsplit = [
        c
        for c in contexts
        if not isinstance(c.n_ctx, int)
        or not isinstance(c.n_parallel, int)
        or c.n_ctx * c.n_parallel != c.launched
    ]
    assert not unsplit, (
        f"{len(unsplit)} of {len(contexts)} children were launched with a "
        f"window their digest cannot reproduce as n_ctx x n_parallel: {unsplit}"
    )
    unnamed = [c for c in contexts if c.total != c.launched]
    assert not unnamed, (
        f"{len(unnamed)} of {len(contexts)} semantic blocks carry no "
        f"{CONTEXT_TOTAL_KEY!r}: the total the child was launched with is "
        f"recoverable only by multiplying two other fields: {unnamed}"
    )


# --------------------------------------------------------------------------
# K3 — the yield that found the card held
# --------------------------------------------------------------------------


class Yielded(NamedTuple):
    host: str
    model: str
    engine: str
    reading: dict[str, Any]


def _yields(directory: Path) -> list[Yielded]:
    """Every release reading that found the card was NOT idle."""
    held = []
    for cell in _cells(directory):
        for engine, reading in (cell.body.get("yielded") or {}).items():
            if isinstance(reading, dict) and reading.get("card_idle") is False:
                held.append(Yielded(cell.host, cell.model, engine, reading))
    return held


@pytest.mark.xfail(
    strict=True,
    reason="2026-08-21: owed — does the yield row name what holds the card?",
)
def test_a_yield_row_that_finds_the_card_held_names_the_holder() -> None:
    """K3 — a yield reads the card, records a stranger, and does not say who.

    ``release()`` stops this engine's own processes and then reads the whole
    card, deliberately keeping "I released mine" separate from "the card is
    empty". On 2026-08-19 the vLLM yield ran before ollama evicted its previous
    model, so 15 of 17 cells recorded ``card_idle: false`` against a residue
    that matched the PREVIOUS cell's post-load reading to within 14 MiB. The
    reading is correct and unattributable: nothing in the row says whose
    memory it is, though the same ``release()`` call could name it from
    ``/api/ps`` or ``nvidia-smi --query-compute-apps``.
    """
    held = _yields(campaign())
    assert held, "no yield found the card held; nothing to attribute"
    anonymous = [
        (y.host, y.model, y.engine, y.reading.get("card_used_mib"))
        for y in held
        if not y.reading.get("holder")
    ]
    assert not anonymous, (
        f"{len(anonymous)} of {len(held)} yields found the card held and named "
        f"no holder: {anonymous}"
    )


# --------------------------------------------------------------------------
# K4 — endpoint_props (dissolves)
# --------------------------------------------------------------------------


def test_a_false_endpoint_props_beside_a_captured_props_payload_is_the_write_flag() -> (
    None
):
    """K4 — ``endpoint_props: false`` is not a failed capture. Dissolves.

    It was filed as a contradiction: a payload fetched FROM ``/props`` that
    says the props endpoint is off. It is llama.cpp's WRITE flag. Its server
    README (``tools/server/README.md``, fetched 2026-08-21) documents
    ``--props`` as "enable changing global properties via POST /props (default:
    disabled)" and says of ``GET /props`` that "By default, it is read-only".
    The harness only ever issues that GET
    (``backends/ollama.py``: ``curl -s -m 8 .../props``; a search of
    ``tools/bench/serving`` for a POST or a ``curl -d`` to ``/props`` on
    2026-08-21 found none), so the flag is a statement about writes nobody
    makes, and ``fingerprint`` classing it operational is correct.

    The check that keeps it from being re-filed: wherever the flag is false,
    the payload beside it is nonetheless complete — the read path answered.
    """
    children = _served(campaign())
    read_only = [c for c in children if c.props.get("endpoint_props") is False]
    assert read_only, (
        f"no child of the {len(children)} captured reports endpoint_props "
        "false; this check has no population and proves nothing"
    )
    incomplete = [
        (c.host, c.model, c.port)
        for c in read_only
        if not ((c.props.get("default_generation_settings") or {}).get("params"))
        or "total_slots" not in c.props
    ]
    assert not incomplete, (
        f"{len(incomplete)} of {len(read_only)} children answered a GET /props "
        f"that is missing the settings the write flag has nothing to do with: "
        f"{incomplete}"
    )


# --------------------------------------------------------------------------
# K5 — two ramp figures that disagree (dissolves)
# --------------------------------------------------------------------------


def _disagreeing_pairs(directory: Path) -> tuple[int, list[tuple[Any, ...]]]:
    """Ramp figures that disagree, and those that disagree unattributably."""
    grouped: dict[tuple[str, str, str], list[Figure]] = {}
    for figure in _figures(directory):
        grouped.setdefault((figure.host, figure.engine, figure.model), []).append(
            figure
        )
    disagreeing = 0
    unattributable = []
    for figures in grouped.values():
        for one, other in itertools.combinations(figures, 2):
            smaller = min(one.speedup, other.speedup)
            if smaller <= 0:
                continue
            if abs(one.speedup - other.speedup) / smaller <= DISAGREEMENT:
                continue
            disagreeing += 1
            if all(
                one.row.get(condition) == other.row.get(condition)
                for condition in DECLARED_CONDITIONS
            ):
                unattributable.append(
                    (
                        one.host,
                        one.engine,
                        one.model,
                        (one.journal, one.speedup),
                        (other.journal, other.speedup),
                        {c: one.row.get(c) for c in DECLARED_CONDITIONS},
                    )
                )
    return disagreeing, unattributable


def test_two_ramp_rows_that_disagree_differ_in_a_declared_condition() -> None:
    """K5 — 2.52x and 1.45x are the same server. Dissolves.

    Filed as a contradiction between a knee of 12 at 2.52x and a
    ``saturation_n`` of 2 at 1.45x for one host and model. They were measured
    at 32 and at 475 completion tokens, and the README already explains why a
    32-token ramp reads a knee on a one-slot server (D3 retired that token
    count for exactly this reason). Same for the vLLM matrix, which quotes 1.0
    against 3.76 for one model at one token count: ``configured_width``
    separates them.

    The check that keeps it from being re-filed is the general form of the
    lesson: every pair of figures for one host, engine and model that disagrees
    by more than 10% differs in a condition the harness declared. A figure that
    cannot be told apart from its neighbour is the defect — whatever the
    numbers are.
    """
    figures = _figures(campaign())
    assert figures, "the campaign's journals carry no ramp figure"
    disagreeing, unattributable = _disagreeing_pairs(campaign())
    assert disagreeing, (
        f"no two of {len(figures)} ramp figures disagree by more than "
        f"{DISAGREEMENT:.0%}; this check has no population and proves nothing"
    )
    assert not unattributable, (
        f"{len(unattributable)} of {disagreeing} disagreeing pairs of ramp "
        f"figures differ in no declared condition {DECLARED_CONDITIONS}: "
        f"{unattributable}"
    )


# --------------------------------------------------------------------------
# K6 — the engine version behind a cross-host figure
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="2026-08-21: owed — what moved between ollama 0.32.4 and 0.32.5 in "
    "scheduling or placement, and does a cross-host row carry the version or "
    "refuse the split?",
)
def test_a_cross_host_figure_carries_the_engine_version_on_each_host() -> None:
    """K6 — the hosts ran different ollama builds and no figure says so.

    srv1 ran ollama 0.32.4 and srv2 ran 0.32.5 on 2026-08-19; the survey read
    both, the difference was known before launch, and the README quotes the two
    ollama arms side by side. Not one ramp row carries a version, so the
    version is recoverable only by joining a figure to the survey document that
    happens to sit beside it — and not at all once the figure is quoted.
    """
    figures = _figures(campaign())
    assert figures, "the campaign's journals carry no ramp figure"
    hosts = {figure.host for figure in figures}
    assert len(hosts) > 1, (
        f"every ramp figure was measured on one host {hosts}; a cross-host "
        "figure is what this check is about"
    )
    unversioned = [
        (figure.journal, figure.host, figure.engine, figure.model)
        for figure in figures
        if not figure.row.get("engine_version")
    ]
    assert not unversioned, (
        f"{len(unversioned)} of {len(figures)} ramp figures across "
        f"{sorted(hosts)} carry no engine_version: {unversioned}"
    )
