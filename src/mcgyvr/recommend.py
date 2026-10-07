"""Read-only planner behind ``mcgyvr recommend``: a plan of units per rig.

``mcgyvr recommend`` re-reads the rigs it is pointed at and answers one
question: for a use case, which units should each rig run, sized from the
measurements it just took. It writes nothing, wakes nothing and sleeps
nothing — the plan it prints is a plan, version 2 (:mod:`mcgyvr.planner`).

The one property this module holds, the same property :mod:`mcgyvr.compose`
holds for setup: **a model's answer can never invent a number.** Every unit is
sized per rig by the product's serving sizer (:func:`mcgyvr.serving.unit_for`,
:func:`mcgyvr.serving.split_unit`) before any decision is consulted, from the
numbers the rig and the file's header just measured, and the decision is
asked only to name one of the shortlisted candidates on each rig. What the
decision returns that can reach the plan is a choice among what was already
assembled, never a figure.

Jev is opt-in. The decision is asked through
:func:`mcgyvr.decision.classify_for` of the unit the config's ``jev.unit``
binds, and of no other: one question per rig, each of at most
:data:`mcgyvr.planner.SHORTLIST` options. With no config, no ``jev.unit``, or
a Jev unit that does not answer, each rig's first-ranked candidate is the
pick (:func:`mcgyvr.planner.rule`), and the plan's ``decision`` says so, and
why.

Models to place come from exactly one of two places, and the plan says which
(``models_from``):

* ``--model-store <dir>`` — checkpoint files are discovered (``*.gguf`` in that
  directory, over the same read-only ssh seam :func:`mcgyvr.scan._ssh` uses)
  and each header is read ON the rig, over the same seam, by shipping
  :mod:`mcgyvr.serving.ggufscan` to the rig as ``python3 -`` (the blob never
  comes back). When a discovered checkpoint fits, the plan places **only**
  from that store.
* no store, or nothing local fits — the plan places from the model knowledge
  read offline (:func:`load_models`: the user's cache, then the shipped
  catalog, each file with its header row), after refreshing that cache online
  unless ``--offline`` or ``HF_HUB_OFFLINE`` says not to
  (:func:`mcgyvr.knowledge.online.refresh`); those units are downloads, and
  the plan says the bytes, the sha256 and where each goes.

The use case is one of the catalog's four (``chat``, ``agent``, ``coding``,
``media-gen``), the same names ``mcgyvr init --use-case`` takes. ``chat``,
``agent`` and ``coding`` are planned; ``media-gen`` is accepted and its rigs
are read, but no unit is planned yet. The old ``--profile`` spellings map
through :data:`OLD_PROFILES`; ``other`` maps to no use case and plans nothing.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from mcgyvr import availability, decision, planner
from mcgyvr import scan as scan_module
from mcgyvr.config import DEFAULT_REQUEST_TIMEOUT_S, Config
from mcgyvr.decision import JEV_ROLE, Choice, ChoiceAnswer
from mcgyvr.knowledge import online as knowledge_online
from mcgyvr.knowledge import store as knowledge_store
from mcgyvr.knowledge.record import KnowledgeError
from mcgyvr.pool import SourceUnavailableError, source_map
from mcgyvr.runner import RunnerError
from mcgyvr.scan import (
    Reach,
    Scan,
    ScanFailed,
    ScannerMissing,
    Unreachable,
)
from mcgyvr.serving import gatelib

#: The deprecated ``--profile`` spellings, read for one release, and the use
#: case each one means. ``other`` names no use case, so nothing is planned.
OLD_PROFILES: dict[str, str | None] = {
    "coding": "coding",
    "chatting": "chat",
    "media_gen": "media-gen",
    "other": None,
}

#: The read-only remote line that discovers ``*.gguf`` one level under a
#: directory on the rig. The directory is always single-quoted by
#: :func:`discover_command`, which the read-only ssh sanction requires.
_DISCOVER_SUFFIX = " -maxdepth 1 -name '*.gguf' -print"

#: What ``models_from`` says: the rig's own store, or the model knowledge.
LOCAL_STORE = "local-store"
KNOWLEDGE = "knowledge"


class CatalogError(Exception):
    """The model knowledge is missing, malformed, or internally inconsistent."""


class RecommendError(Exception):
    """``mcgyvr recommend`` was asked something it cannot honestly answer."""


def discover_command(directory: str) -> str:
    """The one read-only remote line that lists ``*.gguf`` under ``directory``.

    The directory travels as one single-quoted token, so a metacharacter in it
    reaches the rig as a filename character and never as a command. The
    read-only ssh sanction admits a discovery line only when the directory is
    quoted exactly that way, so a directory with an embedded single quote is
    refused rather than shipped in a shape the sanction cannot prove.
    """
    if "'" in directory:
        raise RecommendError(
            "a model-store directory with an embedded single quote cannot be "
            "read read-only"
        )
    return f"find '{directory}'{_DISCOVER_SUFFIX}"


def load_models() -> planner.Library:
    """The models the plan may place from the model knowledge, read offline:
    the user's cache first and then the shipped catalog, each file with its
    header row (:func:`mcgyvr.planner.library`). The command reads it as data,
    so a test can substitute a library through this seam."""
    try:
        return planner.library()
    except KnowledgeError as exc:
        raise CatalogError(str(exc)) from exc


def _refresh_knowledge(use_case: str | None, offline: bool) -> dict[str, Any]:
    """Refresh the models the knowledge holds, online unless asked not to.

    Never raises for the network: what could not be read is named in the
    answer, and the cache and the shipped catalog still answer
    :func:`load_catalog`.
    """
    try:
        known = knowledge_store.offline().records
    except KnowledgeError as exc:
        raise CatalogError(str(exc)) from exc
    done = knowledge_online.refresh(known, use_case=use_case, offline=offline)
    return done.as_json()


def _read_header(host: str, path: str) -> Mapping[str, Any]:
    """Read one checkpoint's header ON ``host``, over the read-only ssh seam.

    The reader (:mod:`mcgyvr.serving.ggufscan`) ships to the rig as ``python3
    -`` through :func:`mcgyvr.serving.gatelib.header_read_command` and reads
    the header there; the blob never comes back and nothing lands on the
    rig's disk. ``mcgyvr.scan._ssh`` is the same read-only ssh seam the scan
    and the discovery use, so a test substitutes the transport once and all
    three answer through it.
    """
    try:
        command = gatelib.header_read_command(path)
    except ValueError as exc:
        raise RecommendError(str(exc)) from exc
    listing = scan_module._ssh(host, command)
    try:
        rows = json.loads(listing)
    except json.JSONDecodeError as exc:
        raise RecommendError(
            f"the rig's header reader printed no JSON for {path}: {exc}"
        ) from exc
    if not isinstance(rows, list) or not rows:
        raise RecommendError(f"the rig's header reader reported no header for {path}")
    header = rows[0]
    if not isinstance(header, dict):
        raise RecommendError(
            f"the rig's header reader reported a non-object header for {path}"
        )
    if "error" in header:
        raise RecommendError(
            f"the rig's header reader refused {path}: {header['error']}"
        )
    return header


def _discover(host: str, directory: str) -> tuple[str, ...]:
    """The ``*.gguf`` paths directly under ``directory`` on ``host``.

    Read over the same ssh seam the scan uses, so a test substitutes the
    transport once and both the scan and the discovery answer through it.
    A directory that does not exist on the rig makes ``find`` exit non-zero,
    which the seam reports as :class:`ScannerMissing`; that is absence — this
    store holds zero checkpoints — and never a failure. A rig that stops
    answering ssh still raises :class:`Unreachable` here, so a lost connection
    is never read as an empty store.
    """
    try:
        listing = scan_module._ssh(host, discover_command(directory))
    except ScannerMissing:
        return ()
    return tuple(
        line for line in (part.strip() for part in listing.splitlines()) if line
    )


def _scan_host(host: str) -> Scan:
    """Re-read one rig at this moment. Never a stored spec."""
    return scan_module.scan_over(Reach.ssh(host))


def _local_models(
    scans: Mapping[str, Scan], model_stores: Sequence[str]
) -> dict[str, list[planner.Model]]:
    """Every checkpoint discovered in the stores on each rig, header read there."""
    found: dict[str, list[planner.Model]] = {}
    for host in scans:
        for directory in dict.fromkeys(model_stores):
            for checkpoint in _discover(host, str(directory)):
                header = _read_header(host, checkpoint)
                try:
                    model = planner.model_from_header(host, checkpoint, header)
                except planner.PlanError as exc:
                    raise RecommendError(str(exc)) from exc
                found.setdefault(host, []).append(model)
    return found


@dataclass(frozen=True)
class _Decided:
    """Each rig's pick, and who picked: ``{by, why}`` as the plan says it."""

    picks: Mapping[str, planner.Sized]
    by: str
    why: str


def _question(use_case: str, choices: planner.Choices) -> Choice:
    role = "strong unit" if use_case in planner.STRONG_USE_CASES else "top rung"
    return Choice(
        instructions=(
            f"For the {use_case} use case, pick the model of the {role} on "
            f"{choices.rig}. Every option already fits the measured machine."
        ),
        options={one.option: one.description for one in choices.shortlist},
    )


def _decide(
    use_case: str,
    assembled: Mapping[str, planner.Choices],
    state: Mapping[str, Any],
    config: Config | None,
) -> _Decided:
    """Name each rig's pick, and say who named it.

    Only the unit ``jev.unit`` binds is asked, through
    :func:`mcgyvr.decision.classify_for`, one question per rig of at most
    :data:`mcgyvr.planner.SHORTLIST` options, and only once it answers the
    reachability probe, so a dead Jev unit costs a probe and not a request
    timeout. With no config, no ``jev.unit``, a Jev unit that cannot run or
    does not answer, the first-ranked candidate of each rig is the pick, and
    ``why`` says which of those it was. A rig whose question the unit answers
    with no candidate is picked by the rule, and ``why`` names it.
    """
    placed = {rig: one for rig, one in assembled.items() if one.ranked}
    first = {rig: one.ranked[0] for rig, one in placed.items()}
    ranked_by = planner.rule(use_case)

    def by_rule(why: str) -> _Decided:
        return _Decided(first, "deterministic", f"{why}; {ranked_by}")

    if config is None:
        return by_rule("no config was found, so no jev.unit is bound")
    unit = config.get("jev.unit")
    if unit is None:
        return by_rule("the config binds no jev.unit")
    unit = str(unit)
    pool = source_map(config)
    try:
        binding = pool.role(JEV_ROLE)
    except SourceUnavailableError as exc:
        return by_rule(f"the jev unit {unit!r} cannot run: {exc}")
    if binding is None:  # pragma: no cover - jev.unit is bound above
        return by_rule("the config binds no jev.unit")
    verdict = availability.probe_endpoint(binding.endpoint)
    if not verdict.live:
        return by_rule(f"the jev unit {unit!r} did not answer: {verdict.reason}")
    questions = {
        f"unit@{rig}": _question(use_case, choices) for rig, choices in placed.items()
    }
    try:
        answered = decision.classify_for(
            pool,
            dict(state),
            questions,
            role=JEV_ROLE,
            timeout_s=DEFAULT_REQUEST_TIMEOUT_S,
        )
    except (RunnerError, decision.DecisionError) as exc:
        return by_rule(f"the jev unit {unit!r} gave no readable answer: {exc}")
    picks: dict[str, planner.Sized] = {}
    unnamed: list[str] = []
    for rig, choices in placed.items():
        answer = answered.answers.get(f"unit@{rig}")
        by_option = {one.option: one for one in choices.shortlist}
        if isinstance(answer, ChoiceAnswer) and answer.choice in by_option:
            picks[rig] = by_option[answer.choice]
        else:
            picks[rig] = first[rig]
            unnamed.append(rig)
    if len(unnamed) == len(placed):
        return by_rule(f"the jev unit {unit!r} named no candidate")
    why = (
        f"the jev unit {unit!r} named each pick among at most "
        f"{planner.SHORTLIST} shortlisted candidates per rig"
    )
    if unnamed:
        why += (
            f"; on {', '.join(unnamed)} it named none, so the first-ranked "
            f"was taken ({ranked_by})"
        )
    return _Decided(picks, "jev", why)


def _state(
    use_case: str,
    users: int,
    priority: str | None,
    scans: Mapping[str, Scan],
    read_at: str,
    assembled: Mapping[str, planner.Choices],
) -> dict[str, Any]:
    """What the Jev unit is shown: the measured rigs and the shortlists."""
    return {
        "use_case": use_case,
        "users": users,
        "priority": priority,
        "measured": {
            rig: planner.measured(scan, read_at) for rig, scan in scans.items()
        },
        "candidates": {
            rig: [
                {
                    "name": one.option,
                    "model": one.model.model_id,
                    "size_bytes": one.model.size_bytes,
                    "ctx_per_slot": one.ctx_per_slot,
                    "slots": one.unit.width.value,
                    "scores": {
                        score.board: score.value.value for score in one.model.scores
                    },
                }
                for one in choices.shortlist
            ]
            for rig, choices in assembled.items()
        },
    }


def _knowledge(
    refreshed: Mapping[str, Any], library: planner.Library
) -> dict[str, Any]:
    """The plan's ``knowledge``: whether it was read online, what was filed,
    what could not be read, which cache files were skipped and which known
    models cannot be sized, each with why."""
    return {
        **refreshed,
        "oldest_read_at": (
            None
            if library.oldest_read_at is None
            else library.oldest_read_at.isoformat()
        ),
        "skipped": [{"file": str(path), "why": why} for path, why in library.skipped],
        "unsized": [{"model": label, "why": why} for label, why in library.unsized],
    }


def plan(
    *,
    use_case: str | None,
    users: int,
    hosts: Sequence[str],
    model_stores: Sequence[str] = (),
    offline: bool = False,
    config: Config | None = None,
    priority: str | None = None,
    ctx_per_slot: int | None = None,
    first_port: int = planner.FIRST_PORT,
) -> dict[str, Any]:
    """Compose the one JSON plan ``mcgyvr recommend`` prints (version 2).

    ``use_case`` is one of the catalog's use cases, or ``None`` for the old
    ``--profile other``, which names none. ``hosts`` are re-read over ssh at
    this moment; ``model_stores``, when any is given, are the directories on
    those rigs to discover ``*.gguf`` in. Before the knowledge is read, it is
    refreshed online (:func:`mcgyvr.knowledge.online.refresh`) unless
    ``offline`` or ``HF_HUB_OFFLINE`` says not to; the plan's ``knowledge``
    says which, and names what could not be read. ``config`` is read for its
    ``jev.unit`` alone: the unit asked to name the picks. ``priority`` is said
    in the plan and to that unit. ``ctx_per_slot``, when given, is every
    unit's context per slot instead of the use case's. ``first_port`` is the
    port each rig's first unit answers on.
    """
    unreachable: list[dict[str, str]] = []
    scans: dict[str, Scan] = {}
    for host in dict.fromkeys(str(h) for h in hosts):
        try:
            scans[host] = _scan_host(host)
        except ScannerMissing:
            unreachable.append({"host": host, "why": "no python3 to run the scan"})
        except ScanFailed as exc:
            unreachable.append({"host": host, "why": f"the scan failed: {exc}"})
        except Unreachable as exc:
            unreachable.append({"host": host, "why": f"ssh did not answer: {exc}"})
    read_at = datetime.now(UTC).isoformat(timespec="seconds")

    def done(
        laid: Mapping[str, Sequence[planner.Sized]],
        decided: Mapping[str, str],
        knowledge: Mapping[str, Any] | None,
        models_from: str | None,
        dropped: Sequence[Mapping[str, str]],
    ) -> dict[str, Any]:
        return planner.document(
            use_case=use_case,
            users=users,
            priority=priority,
            hosts=list(dict.fromkeys(str(h) for h in hosts)),
            scans=scans,
            read_at=read_at,
            laid=laid,
            decision=decided,
            knowledge=knowledge,
            models_from=models_from,
            dropped=dropped,
            unreachable=unreachable,
        )

    if use_case not in planner.PLANNED_USE_CASES:
        said = f"{use_case} is not planned yet" if use_case else "no use case was named"
        return done({}, {"by": "none", "why": said}, None, None, [])

    assembled: dict[str, planner.Choices] = {}
    knowledge: dict[str, Any] | None = None
    models_from = LOCAL_STORE
    if model_stores:
        local = _local_models(scans, model_stores)
        assembled = planner.assemble(
            use_case, users, scans, local, ctx_per_slot=ctx_per_slot
        )
    if not any(one.ranked for one in assembled.values()):
        refreshed = _refresh_knowledge(use_case, offline)
        library = load_models()
        knowledge = _knowledge(refreshed, library)
        assembled = planner.assemble(
            use_case,
            users,
            scans,
            {rig: library.models for rig in scans},
            ctx_per_slot=ctx_per_slot,
        )
        models_from = KNOWLEDGE
    dropped = [
        {"rig": rig, "model": label, "why": why}
        for rig, choices in assembled.items()
        for label, why in choices.dropped
    ]
    if not any(one.ranked for one in assembled.values()):
        reasons = "; ".join(f"{d['rig']}: {d['why']}" for d in dropped)
        down = "; ".join(f"{d['host']}: {d['why']}" for d in unreachable)
        raise RecommendError(
            "nothing to recommend: no model fits any rig that was read"
            + (f" ({reasons})" if reasons else "")
            + (f"; not read: {down}" if down else "")
        )
    state = _state(use_case, users, priority, scans, read_at, assembled)
    decided = _decide(use_case, assembled, state, config)
    laid = planner.lay_out(
        {rig: (one,) for rig, one in decided.picks.items()}, first_port=first_port
    )
    return done(
        laid,
        {"by": decided.by, "why": decided.why},
        knowledge,
        models_from,
        dropped,
    )
