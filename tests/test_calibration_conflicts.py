"""Ten recorded conflicts, and the check each one becomes.

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
  ``decided — <the decision>`` once they have. **All eight are decided as of
  2026-08-22** — the owner ruled the whole set in one pass, so #328's closing
  grep for the owed grammar prints 0 against this file and every marker here
  now records a decision rather than a question. (That grep is a literal
  string search, so this paragraph states the pattern rather than quoting it:
  a docstring that spelled it out would be its own counter-example.)
  ``strict`` is what keeps them live: a campaign that fixes one turns XPASS and
  fails the suite until the marker comes off. **Seven of the eight** can only be
  turned green by a run — they resolve against the newest campaign directory.
  K10 is the exception: it reads ``tools/bench/serving/configs/``, so a prose
  edit alone flips the check while the measurement its ruling calls for is
  still owed on #337. The check and the finding are not the same thing there,
  and that gap is K10's own defect rather than the ruling's.
* Rule 3 — the append-only record names its check. The block ``## Conflicts
  recorded 2026-08-21`` in the campaign README carries K1-K6, ``## Conflicts
  recorded 2026-08-22`` carries K7-K9, ``## Conflict recorded 2026-08-22
  (second)`` carries K10 alone, and ``## Rulings recorded 2026-08-22`` carries
  the owner's eight decisions — each naming the test below that reads it. Two
  of the ten checks (K7, K8) were rewritten by their own ruling and K6 was
  repointed; the rulings block says so, and the earlier blocks are not edited.

The two that dissolve stay as green checks rather than as a deleted paragraph:
their job is to keep a re-derived non-finding from being re-filed, and to go
red if a later campaign turns either into a real one.

**The population is the newest campaign, not this one.** Every check but K10
resolves its evidence through :func:`campaign` — the newest ``calibration-*``
directory under ``records/evidence/``. (K10 reads the repository's own serving
configs instead, because the constant it is about lives there and not in any
run. Corrected 2026-08-22: this paragraph said "every check" from the day K10
landed, and K10 never called :func:`campaign`.)

The 2026-08-19 files are frozen history and can
never turn green, so a check pinned to them would be an ``xfail`` that outlives
its own finding and can never XPASS. Pointed at the newest campaign, each of
these is a question put to the NEXT run, which is what every "owed" reason
asks, and the run that answers it flips the marker.

**K7-K9 were added on 2026-08-22 and were not part of #328's six.** They are
the honest limits of a live verification run that day: with
``OLLAMA_NUM_PARALLEL`` declared as ``1`` on both rigs, srv1 (ollama 0.32.4)
and srv2 (ollama 0.32.5) launched ``qwen2.5-coder:1.5b`` at an identical
``-c 4096 -np 1`` and held a byte-identical ``size_vram``. That is one model,
one context, one width, and it says nothing about throughput -- so rather than
record the limits as a caveat in prose, each became the check that would catch
it: K7 asks the geometry question of every model served on both hosts, K8 asks
how wide the cross-host population is before an engine is called equivalent,
and K9 asks whether both hosts declare the settings that decide residency
instead of inheriting them from two different engine versions.

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

#: The name the tree writes for the engine build a row ran on. K6 was filed
#: against ``engine_version``, which appears nowhere in ``tools/`` or ``src/``
#: and never did; ``calibrate.py`` builds an ``identity`` block carrying this
#: name instead (with a sibling ``refusals`` entry when the host will not
#: answer). Repointed 2026-08-22 on the owner's ruling — a check that a correct
#: run cannot satisfy is a typo with a marker on it, not a finding.
BUILD_KEY = "serving_build"

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
    reason="2026-08-22: decided — the pin is the sampler the request ran "
    "under; llama-server's /props defaults are recorded beside it and not "
    "digested (owner). Code owed on #336.",
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
    reason="2026-08-22: decided — record, never equalise: the launched total "
    "gets its own name and a cross-host contrast carries the difference, "
    "rather than the hosts being pinned to match (owner). Code owed on #336.",
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
    reason="2026-08-22: decided — yes; release() names the holder from "
    "/api/ps and the card's process list, and vLLM's want of an equivalent is "
    "a stated refusal rather than a null (owner). Code owed on #336.",
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
    reason="2026-08-22: decided — the row carries the build; it does not "
    "refuse the split. Repointed from engine_version, which nothing in the "
    "tree writes, to serving_build (owner). NOT code: calibrate.emit() has "
    "merged the identity block into every hosted row since #326; the "
    "2026-08-19 journals predate it, so what is owed is a post-#326 campaign.",
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
        if not (figure.row.get("identity") or {}).get(BUILD_KEY)
    ]
    assert not unversioned, (
        f"{len(unversioned)} of {len(figures)} ramp figures across "
        f"{sorted(hosts)} carry no identity.{BUILD_KEY}: {unversioned}"
    )


# --------------------------------------------------------------------------
# K7 — the geometry a model was launched with, across hosts
# --------------------------------------------------------------------------


class Geometry(NamedTuple):
    """One served child's launch geometry, as its own command line states it."""

    host: str
    model: str
    context: int
    slots: int


def _geometries(directory: Path) -> list[Geometry]:
    """Every served child whose command line states both ``-c`` and ``-np``.

    A child that states neither is not a geometry and is not a counter-example:
    the population is what the campaign can be held to, not what it omitted.
    """
    found = []
    for child in _served(directory):
        context = _LAUNCHED_CONTEXT.search(child.command_line)
        slots = _LAUNCHED_SLOTS.search(child.command_line)
        if context and slots:
            found.append(
                Geometry(
                    host=child.host,
                    model=child.model,
                    context=int(context.group(1)),
                    slots=int(slots.group(1)),
                )
            )
    return found


def _geometry_by_model(directory: Path) -> dict[str, dict[str, tuple[int, int]]]:
    """``model -> host -> (context, slots)``, for models served on any host."""
    table: dict[str, dict[str, tuple[int, int]]] = {}
    for entry in _geometries(directory):
        table.setdefault(entry.model, {})[entry.host] = (entry.context, entry.slots)
    return table


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-22: decided — yes, provided the difference is recorded and "
        "declared on the contrast that reads the two rows; equalising the "
        "hosts was rejected (owner). Code owed on #336, the contrast on #335"
    ),
)
def test_a_model_served_on_both_hosts_was_launched_with_the_same_geometry() -> None:
    """K7 — a cross-host figure may rest on children launched differently.

    Filed as an equality check. **Ruled 2026-08-22 (owner): record, never
    equalise.** A cross-host figure MAY rest on children the two hosts launched
    differently, provided the difference is recorded and declared on the
    contrast that reads the two rows. Pinning the rigs to match was rejected —
    it fights the no-caps rule (the hardware is the limit) and would still
    leave the launched total unnamed.

    So this no longer asks for equality; asking for it after that ruling would
    make the check unpassable by construction. It asks instead that both hosts'
    geometry is ON THE RECORD for every model a cross-host figure could rest
    on: the launched total under its own name, not recoverable only by
    multiplying two other fields.

    That is K2's obligation narrowed to the population that actually bears a
    cross-host claim. It is **not** independent of K2 and does not pretend to
    be: K7's children are a subset of K2's and its predicate is K2's second
    assertion restricted to them, so K7 cannot be red while K2 is green. What
    it adds is the population — when K2 goes green partially, the message here
    names the (model, host) children a cross-host figure would have rested on,
    which K2's whole-campaign count does not. The independence claim first
    written here was wrong and is corrected in the campaign README's rulings
    block.

    The ruling's second clause — the difference is declared on the contrast's
    ignore list — is ADR-0038 D4's contrast record and is checked in
    ``tests/test_run_contract.py``, not here. An ignore is a property of the
    claim, and the claim is built at reading time, so it cannot be a property
    of either cell.

    The test's name is kept because #328's definition of done quotes it.
    """
    directory = campaign()
    table = _geometry_by_model(directory)
    shared = {model: hosts for model, hosts in table.items() if len(hosts) > 1}
    assert shared, (
        "no model was served on more than one host, so nothing in this "
        "campaign supports a cross-host comparison at all"
    )
    recorded: dict[tuple[str, str], bool] = {}
    for context in _contexts(directory):
        key = (context.host, context.model)
        # AND, not last-wins: one (host, model) can have several served
        # children — a co-resident cell has two — and a later one carrying the
        # total must not mask an earlier one that does not.
        recorded[key] = recorded.get(key, True) and (context.total == context.launched)
    unrecorded = sorted(
        (model, host, geometry)
        for model, hosts in shared.items()
        for host, geometry in hosts.items()
        if not recorded.get((host, model))
    )
    assert not unrecorded, (
        f"{len(unrecorded)} of {sum(len(h) for h in shared.values())} "
        f"(model, host) children bearing a cross-host figure carry no "
        f"{CONTEXT_TOTAL_KEY!r}: the window each host launched is recoverable "
        f"only by multiplying two other fields, so a reader comparing the two "
        f"cannot see that they differ: {unrecorded}"
    )


# --------------------------------------------------------------------------
# K8 — two hosts are two one-armed cells (filed as: how wide is the evidence)
# --------------------------------------------------------------------------

#: Retired 2026-08-22 by the owner's ruling on K8. A floor on models-per-engine
#: presumes there is a count at which two hosts become one instrument. There is
#: not: cross-host equivalence is never claimed, so no number was the answer and
#: the question was the defect. What replaces it is the storage shape below.


def _cross_host_models(directory: Path) -> dict[str, set[str]]:
    """``engine -> the models carrying a figure on more than one host``."""
    seen: dict[str, dict[str, set[str]]] = {}
    for figure in _figures(directory):
        seen.setdefault(figure.engine, {}).setdefault(figure.model, set()).add(
            figure.host
        )
    return {
        engine: {model for model, hosts in models.items() if len(hosts) > 1}
        for engine, models in seen.items()
    }


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-22: decided — there is no such number. Cross-host equivalence "
        "is never claimed and ollama and vLLM are never equivalent; a "
        "capability cell is one-armed, and its comparison is a second arm on "
        "the SAME machine differing in exactly one declared parameter (owner). "
        "The cell shape is owed on #335"
    ),
)
def test_a_cross_host_agreement_rests_on_more_than_one_model_per_engine() -> None:
    """K8 — two hosts are two one-armed cells, not one contrast.

    Filed as "how wide is the cross-host evidence", on the true observation
    that ``size_vram`` agreeing to the byte says the engines allocated the same
    thing and nothing about what they then did with it, and that on 2026-08-19
    exactly one model per engine carried a figure on both hosts.

    **Ruled 2026-08-22 (owner): the question has no number.** Cross-host
    EQUIVALENCE is never claimed — srv1 and srv2 are not one instrument at any
    population — and ollama and vLLM are never equivalent either.

    Read the scope exactly. This does not forbid a cross-machine comparison:
    ADR-0038 D1 withdrew the rigs' roles and D2 says a cross-machine question
    authorises its own run ("which machine serves the 1.5B faster"), and both
    were Accepted the same day as this ruling. What is denied is the claim that
    the two hosts are interchangeable instruments, which is the claim a
    models-per-engine floor was quietly building toward. A cross-machine
    contrast stays available and carries what it ignored, on D4's record —
    which is also K7's ruling.

    What the ruling adds is the shape underneath. Two hosts produce two
    **one-armed cells**: "how many 1.5B models fit on this card" answers itself
    on each machine and needs no second arm to be a record. A *capability*
    cell's comparison is then built by adding a second arm against it —
    typically on the same machine, differing in exactly one declared parameter,
    the same count of models at a different context. That is what makes a
    capability measurement reusable as a contrast nobody planned, and it is why
    the storage shape matters more than the population size.

    So the check is not a floor. It asks that every (host, model) reading this
    campaign took for a model seen on more than one host is stored as a
    standalone cell, in the one-directory-per-cell shape ADR-0038 D5 defines,
    so a later contrast can take one up as an arm. Red today because the
    campaign writes journals and not cells — the same absence
    ``tests/test_run_contract.py`` names for D5, asked here of the specific
    readings a cross-host claim was read off.

    Cell **naming** is deliberately not asserted: #335 has not defined the
    convention, so the cell is matched on the ``host`` and ``model`` inside its
    own ``run.json`` (the contract makes that file "the terminal record — the
    row, provenance, identity, pre-state, post-state",
    ``docs/run-contract-2026-08-22.md:26``). If #335 nests the row under a key,
    this reader moves with it; if #335 also moves ramp rows out of the
    campaign's top level, :func:`_figures` stops finding them and this check
    must be repointed rather than left to refuse.

    The test's name is kept because #328's definition of done quotes it.
    """
    directory = campaign()
    per_engine = _cross_host_models(directory)
    assert per_engine, "no ramp figures at all, so no cross-host evidence exists"
    cross_host = {
        (figure.host, figure.model)
        for figure in _figures(directory)
        if figure.model in per_engine.get(figure.engine, set())
    }
    assert cross_host, (
        f"no model in {directory.name} carries a figure on more than one host, "
        "so this campaign produced no reading to store as a standalone cell"
    )
    stored = set()
    for path in sorted(directory.glob("*/run.json")):
        try:
            cell = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue  # an unreadable cell is not a cell; K-checks do not repair
        if isinstance(cell, dict):
            stored.add((str(cell.get("host")), str(cell.get("model"))))
    missing = sorted(cross_host - stored)
    assert not missing, (
        f"{len(missing)} of {len(cross_host)} (host, model) readings bearing a "
        f"cross-host claim in {directory.name} have no standalone cell naming "
        "them: the campaign holds journals, not the one-directory-per-cell "
        "records ADR-0038 D5 makes a contrast's arms out of, so nothing here "
        f"can be taken up as an arm later: {missing}"
    )


# --------------------------------------------------------------------------
# K9 — the co-residency settings, declared on one host and defaulted on the other
# --------------------------------------------------------------------------

#: The ollama settings that decide whether a model stays resident and whether a
#: second one may join it — which is what the co-residency cells measure. A
#: value the engine chose is not a value the run declared: it moves with the
#: engine version, and the two hosts do not run the same version.
CORESIDENCY_SETTINGS = (
    "OLLAMA_NUM_PARALLEL",
    "OLLAMA_MAX_LOADED_MODELS",
    "OLLAMA_KEEP_ALIVE",
)

_ENVIRONMENT_SETTING = re.compile(r"(OLLAMA_[A-Z_]+)=(\S+)")


def _declared_settings(directory: Path) -> dict[str, set[str]]:
    """``host -> the OLLAMA_* settings its unit declares``, as captured."""
    declared = {}
    for host, body in _survey(directory)["hosts"].items():
        readings = ((body.get("present") or {}).get("ollama") or {}).get(
            "readings"
        ) or {}
        stdout = (readings.get("service_environment") or {}).get("stdout") or ""
        declared[host] = {name for name, _ in _ENVIRONMENT_SETTING.findall(stdout)}
    return declared


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-22: decided — every host declares them; an engine default "
        "inherited in silence is not a declaration (owner). Both rigs were "
        "declared live on 2026-08-22, so this goes green on the next "
        "campaign's survey. The regression risk this reason first named — "
        "nothing in the repo stating or asserting the values — is closed by "
        "tools/bench/serving/configs/hosts.json and "
        "tests/test_declared_host_state.py, which check the VALUE where this "
        "checks the name"
    ),
)
def test_both_hosts_declare_the_settings_that_decide_residency() -> None:
    """K9 — one host declares residency, the other inherits it.

    ``OLLAMA_MAX_LOADED_MODELS`` and ``OLLAMA_KEEP_ALIVE`` decide whether a
    model stays on the card and whether a second may join it, which is exactly
    what the co-residency cells measure. On 2026-08-19 srv1 declared all three
    of :data:`CORESIDENCY_SETTINGS` and srv2 declared none.

    An undeclared setting is not a known one. The engine picks it, the engines
    are not the same version on the two hosts (K6), and the value it picks is
    not recorded anywhere in the evidence — so "both hosts ran the default"
    is an assumption the campaign cannot check against its own files. Declaring
    it costs one line per host and turns the assumption into a reading.
    """
    declared = _declared_settings(campaign())
    assert declared, "no host captured its ollama service environment"
    wanted = set(CORESIDENCY_SETTINGS)
    incomplete = {
        host: sorted(wanted - names)
        for host, names in declared.items()
        if wanted - names
    }
    assert not incomplete, (
        f"{len(incomplete)} of {len(declared)} hosts leave a residency setting "
        f"to the engine's default, unrecorded: {incomplete}"
    )


# --------------------------------------------------------------------------
# K10 — a constant this project did not choose
# --------------------------------------------------------------------------

#: The serving knobs whose value changes what a measurement means, and which
#: therefore have to be this project's choice or say whose they are. Kept
#: deliberately short: the rule is expensive to satisfy and is worth paying
#: only where an inherited number would silently move a figure.
ACCOUNTABLE_KNOBS = ("gpu_memory_utilization", "kv_cache_memory_bytes")

#: Substrings that make a note a PROVENANCE note rather than a description.
#: A note saying what the knob does is not a note saying where its value came
#: from, and only the second one answers "did we choose this?".
_PROVENANCE_MARKERS = ("chosen", "origin", "inherited", "read off", "because", "source")

CONFIGS = REPO / "tools" / "bench" / "serving" / "configs"


def _knob_sites(directory: Path = CONFIGS) -> list[tuple[str, str, Any, str]]:
    """``(file, label, value, the entry's prose)`` for every accountable knob."""
    sites = []
    for path in sorted(directory.glob("*.json")):
        document = _payload(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        for entry in document.get("models") or []:
            if not isinstance(entry, dict):
                continue
            serve = entry.get("serve")
            if not isinstance(serve, dict):
                continue
            prose = " ".join(
                str(value)
                for key, value in entry.items()
                if key.startswith("_") or key == "notes"
            )
            for knob in ACCOUNTABLE_KNOBS:
                if knob in serve:
                    sites.append(
                        (path.name, str(entry.get("label")), serve[knob], prose)
                    )
    return sites


def test_a_serving_constant_this_project_did_not_choose_names_its_source() -> None:
    """K10 — ``gpu_memory_utilization = 0.85`` was copied, not decided.

    Traced on 2026-08-22. The value was read off a **running** srv1 on
    2026-08-18 (``tests/test_bench_observed.py:172``, a fixture captured from
    a server this repo did not start) roughly seven hours before it entered
    any config here, and it existed in the local-ai repo by 2026-08-10. The
    three commits that wrote it into the five sites -- ``d07d45c5``,
    ``ccae4424``, ``e8ea2648`` -- never mention it. ``backends/vllm.py:10``
    records it as an observation: "allocates a fraction of VRAM at startup --
    0.85 or 0.90 on these rigs -- and holds it".

    The reason exists, in the other repo: local-ai reduced 0.90 to 0.85 to
    stop a CUDA OOM on **srv2's 12 GB RTX 3060**, bundled with two other
    changes (context 16384 to 8192, width 16 to 8), so the OOM is not
    attributed to this knob alone. srv1 has a **6 GB** card and the same
    value is applied there, unexamined.

    vLLM 0.26.0's own default is 0.92 on both builds, so this is a deliberate
    7-point reduction that no document here defends.

    The rule this check states is narrow: a knob that moves what a
    measurement MEANS is either this project's choice or says whose it is.
    An entry may satisfy it by naming the origin in its prose; it may not
    satisfy it by describing what the knob does.

    **Repointed 2026-08-22 (owner sign-off, ADR-0037's amendment).** ADR-0039
    withdrew ``gpu_memory_utilization`` from every config in this tree, so the
    field this check named stopped existing and the check began failing on its
    own vacuity guard — asserting nothing about any value, which the amendment
    calls a typo with a marker on it rather than a live finding. The successor
    field is ``kv_cache_memory_bytes`` and the rule above is unchanged: it is
    the *accountability* of a serving constant that is being checked, not the
    spelling of one knob. The guard is why this was visible at all; it fired
    the moment the field disappeared, which is the fifth instance on this lane
    of a check whose result came from where it was run rather than what it
    asserts, and the first that an existing guard caught rather than a person.

    **The finding is closed by measurement, not by the rename.** #337's
    question — did we choose this number? — is answered: the declared bytes
    follow from the entry's own ``max_num_seqs * max_model_len *
    bytes_per_token``, and the footprint each declaration produces was measured
    on both cards on 2026-08-22 (ADR-0039). The three copies this check could
    not see are down to two: ``vllm.py``'s fallback is deleted, and
    ``calibrate.py``'s two inline serve blocks are held by
    ``tests/test_serving_memory_declaration.py::test_the_calibration_probes_declare_bytes_too``,
    parked there against #329 rather than invisible here.
    """
    sites = _knob_sites()
    assert sites, (
        f"no config under {CONFIGS} declares any of {ACCOUNTABLE_KNOBS}, so "
        "this check reads nothing and would pass vacuously"
    )
    unattributed = [
        (file, label, value)
        for file, label, value, prose in sites
        if not any(marker in prose.lower() for marker in _PROVENANCE_MARKERS)
    ]
    assert not unattributed, (
        f"{len(unattributed)} of {len(sites)} serving constants carry no note "
        f"naming where the value came from: {unattributed}"
    )
