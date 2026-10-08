"""The sample: what a staged fleet showed when it ran, and whether that is green.

Owner, Round 4 (2026-10-07), FLEET FLOW TWEAK: the owner's confirm is
approval to run the SAMPLE -- start the servers and run the sample check task.
A green sample is the fleet STAMPED (:mod:`mcgyvr.fleet.stamp`); a red one is
no stamp, and the sample says why.

A :class:`Sample` is what ran: the staged setup (``fleet.yaml`` and
``policy.yaml``, the fleet not yet locked), the door reads taken of it
(``python -m mcgyvr.serving.run read --fleet F --probe U [--load WxN]``, each
filed under the setup's journal by :func:`mcgyvr.fleet.read.record`), and the
outcome of the use case's task (:class:`Outcome`). :func:`judge` reads it all
back and says, plan section 8.2:

* **every awake unit** was probed by the lock's own harness: warm decode and
  prefill read, restarts read and none, its card read, and nothing alerted
  against its ``room_mib``;
* **the use case's task** passed: ``coding`` the deterministic gate on any
  rung; ``chat`` one completion per unit, served at the planned window per
  slot (``window``) and slots (``width``); ``agent`` the grounded and the
  safety checks; ``media-gen`` is not sampled yet (P11);
* **an opted-in Jev** (``policy.yaml`` ``jev.unit``) gave one typed choice: a
  label and a probability;
* **every sleeper swaps** (owner, Round 8, after P10): a unit whose
  ``units.<u>.role`` is ``sleeps-until-needed`` is woken by a fleet F lists
  in ``next`` -- F-strong, which lists F back -- and the sample measured the
  move each way (:class:`Move`): passed, with its downtime and wake seconds.
  F-strong is judged as F is: every awake unit probed. An ``asleep`` slot is
  no reason by itself.

What the reads measured becomes the dev-run evidence ``mcgyvr fleet lock``
already reads (:mod:`mcgyvr.fleet.lock`): the rig file the user's scan saved
(:mod:`mcgyvr.serving.rigfile`) gives each card's MiB, the last read's
snapshot names the rig and gives the card's reserve as the combination's
overhead, and each unit's card peak is the highest card reading around the
sample (its card and its load's peak), its steady card the last read's. The
evidence carries ``passed`` as the sample's verdict, and the swap's moves as
``moves``. Nothing here reads a rig or writes a file.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeGuard

from mcgyvr.config import CHAT, ROLE_SLEEPER
from mcgyvr.fleet.files import FleetFileError, load_fleet, load_policy
from mcgyvr.fleet.layout import AWAKE
from mcgyvr.fleet.read import RIG_ROWS

#: The use cases and the task outcome each is judged by (plan section 8.2).
#: ``chat`` is the config's own constant.
CODING_USE_CASE = "coding"
AGENT = "agent"
MEDIA_GEN = "media-gen"
#: The use case a policy that names none runs, as the config's default.
DEFAULT_USE_CASE = CODING_USE_CASE
#: The checks an :class:`Outcome` reports.
TASK_GATE = "gate"
TASK_COMPLETION = "completion"
TASK_GROUNDED = "grounded"
TASK_SAFETY = "safety"
TASK_CHOICE = "choice"
CHECKS = (TASK_GATE, TASK_COMPLETION, TASK_GROUNDED, TASK_SAFETY, TASK_CHOICE)
#: The arrow a switch between two fleets is named by.
TO = "→"
#: Why a media-gen fleet is not stamped yet.
MEDIA_NOT_BUILT = "the media sample isn't built yet (P11)"
#: The figures every awake unit's probe must read.
PROBE_FIELDS = ("warm_decode_tok_s", "prefill_tok_s")
#: The snapshot reading the combination's overhead is taken from.
RESERVE_FIELD = "gpu_reserve_mib"


class SampleError(Exception):
    """The sample cannot be judged at all: its setup cannot be read."""


@dataclass(frozen=True)
class Outcome:
    """One check of the use case's task, as the sample's runner saw it.

    ``check`` is one of :data:`CHECKS`. ``unit`` is the unit it ran on (the
    rung, for the coding gate). ``served`` is what a ``completion`` read back
    from the unit: ``window`` (tokens per slot) and ``slots``. ``label`` and
    ``probability`` are a Jev ``choice``'s answer.
    """

    check: str
    unit: str | None = None
    passed: bool = False
    why: str = ""
    served: Mapping[str, int] = field(default_factory=dict)
    label: str | None = None
    probability: float | None = None


@dataclass(frozen=True)
class Move:
    """One rig's switch between two fleets, as the sample's swap made it.

    ``downtime_s`` runs from the first unit stopped to the last unit started
    answering; ``wake_s`` is the start alone. ``why`` is what failed.
    """

    rig: str
    from_fleet: str
    to_fleet: str
    passed: bool = False
    downtime_s: float | None = None
    wake_s: float | None = None
    why: str = ""


@dataclass(frozen=True)
class Sample:
    """What ran: the staged setup, the reads of it, and the task's outcomes.

    ``reads`` are the door read ids of the sample, in the order taken; the last
    one that read a rig is its steady state. ``journal`` is where those reads
    filed, by default the setup's own (``journal.dir`` of its ``policy.yaml``).
    ``validated_at`` is by default the moment of the sample's last read.
    ``envelope`` is the door run's envelope, when it filed one. ``moves`` are
    the swap's moves, between ``fleet`` and the fleets its ``next`` lists.
    """

    setup: Path
    fleet: str
    reads: Sequence[str]
    outcomes: Sequence[Outcome] = ()
    journal: Path | None = None
    validated_at: str | None = None
    envelope: str | None = None
    moves: Sequence[Move] = ()


@dataclass(frozen=True)
class Verdict:
    """The sample judged: green, or each reason it is not.

    ``evidence`` is the dev-run evidence the reads support, its ``passed``
    the verdict, or ``None`` when a rig has no read or no rig file to build it
    from.
    """

    green: bool
    why: tuple[str, ...]
    evidence: dict[str, Any] | None


@dataclass
class _UnitRead:
    """One unit's rows across the sample's reads."""

    card: list[int] = field(default_factory=list)
    peaks: list[int] = field(default_factory=list)
    restarts: list[int] = field(default_factory=list)
    figures: dict[str, float] = field(default_factory=dict)
    backend: str | None = None
    alerts: list[str] = field(default_factory=list)


def _rows(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _same(left: Any, right: Path) -> bool:
    try:
        return Path(str(left)).resolve() == right.resolve()
    except (OSError, RuntimeError):
        return False


def _number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, int | float) and not isinstance(value, bool)


class _Reads:
    """The rows the sample's reads filed for its fleets, from its setup, in order.

    Keyed by fleet: a unit awake in F and in F-strong is read in each.
    """

    def __init__(self, sample: Sample, journal: Path, fleets: Sequence[str]) -> None:
        order = {run_id: index for index, run_id in enumerate(sample.reads)}
        self.rig: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.unit: dict[tuple[str, str], list[dict[str, Any]]] = {}
        if not journal.is_dir():
            return
        for path in sorted(journal.glob("*/*.jsonl")):
            for row in _rows(path):
                if (
                    row.get("run_id") not in order
                    or row.get("fleet") not in fleets
                    or not _same(row.get("setup"), sample.setup)
                ):
                    continue
                fleet = str(row["fleet"])
                if path.name == RIG_ROWS:
                    key = (fleet, str(row.get("rig")))
                    self.rig.setdefault(key, []).append(row)
                else:
                    key = (fleet, str(row.get("unit_id")))
                    self.unit.setdefault(key, []).append(row)
        for rows in (*self.rig.values(), *self.unit.values()):
            rows.sort(key=lambda row: order[row["run_id"]])

    def of_unit(self, fleet: str, unit_id: str) -> _UnitRead:
        read = _UnitRead()
        for row in self.unit.get((fleet, unit_id), []):
            name, value = row.get("field"), row.get("observed")
            if row.get("alert") is True and name != "restarts":
                read.alerts.append(str(name))
            if name == "card_mib" and _number(value):
                read.card.append(int(value))
            elif name == "load_peak_mib" and _number(value):
                read.peaks.append(int(value))
            elif name == "restarts" and _number(value):
                read.restarts.append(int(value))
            elif name in PROBE_FIELDS and _number(value) and not row.get("contended"):
                read.figures[str(name)] = float(value)
            elif name == "attention_backend" and isinstance(value, str):
                read.backend = value
        return read


def _setup(sample: Sample) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        fleet = load_fleet((sample.setup / "fleet.yaml").read_text(encoding="utf-8"))
        policy = load_policy((sample.setup / "policy.yaml").read_text(encoding="utf-8"))
    except (OSError, FleetFileError) as exc:
        raise SampleError(
            f"the staged setup {sample.setup} cannot be read: {exc}"
        ) from exc
    if sample.fleet not in (fleet.get("fleets") or {}):
        raise SampleError(
            f"{sample.setup / 'fleet.yaml'} declares no fleet {sample.fleet}"
        )
    return fleet, policy


def _why_unprobed(rows: Sequence[Mapping[str, Any]], name: str) -> str:
    """What the reads said of a unit whose figures are missing, last read first."""
    for row in reversed(rows):
        failed = row.get("failed") or {}
        if name in failed:
            return str(failed[name])
        busy = row.get("busy") or {}
        if name in busy:
            return f"it had {busy[name]} in flight when probed"
        if name in (row.get("contended") or []):
            return "it took other work during its probe"
    return "no read probed it"


def _probe_reasons(
    name: str,
    unit: Mapping[str, Any],
    read: _UnitRead,
    rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    out: list[str] = []
    missing = [f for f in PROBE_FIELDS if f not in read.figures]
    if missing:
        out.append(
            f"probe: {name}: {', '.join(missing)} not read: {_why_unprobed(rows, name)}"
        )
    if not read.restarts:
        out.append(f"probe: {name}: its restarts were not read")
    elif max(read.restarts) > 0:
        out.append(
            f"probe: {name}: it restarted {max(read.restarts)} time(s) in the sample"
        )
    if not read.card and not read.peaks:
        out.append(f"probe: {name}: its card was not read")
    for alerted in sorted(set(read.alerts)):
        out.append(
            f"probe: {name}: {alerted} went over its room_mib {unit.get('room_mib')}"
        )
    return out


def _ran(
    outcomes: Sequence[Outcome], check: str, unit: str | None = None
) -> list[Outcome]:
    return [
        one
        for one in outcomes
        if one.check == check and (unit is None or one.unit == unit)
    ]


def _failed(check: str, ran: Sequence[Outcome], what: str) -> list[str]:
    """Reasons for a check that must pass at least once: did not run, or each why."""
    if not ran:
        return [f"{check}: {what} did not run"]
    if any(one.passed for one in ran):
        return []
    return [
        f"{check}: {one.unit or 'the fleet'}: {one.why or 'did not pass'}"
        for one in ran
    ]


def _completion(
    name: str, unit: Mapping[str, Any], ran: Sequence[Outcome]
) -> list[str]:
    if not ran:
        return [f"{TASK_COMPLETION}: {name}: did not run"]
    one = ran[-1]
    if not one.passed:
        return [f"{TASK_COMPLETION}: {name}: {one.why or 'did not answer'}"]
    out: list[str] = []
    for key, planned_key in (("window", "window"), ("slots", "width")):
        planned = unit.get(planned_key)
        served = one.served.get(key)
        if served is None:
            out.append(f"{TASK_COMPLETION}: {name}: its {key} was not read back")
        elif planned is None or int(served) != int(planned):
            out.append(
                f"{TASK_COMPLETION}: {name}: served {key} {served}, planned {planned}"
            )
    return out


def _choice(jev: str, ran: Sequence[Outcome]) -> list[str]:
    if not ran:
        return [f"{TASK_CHOICE}: the Jev unit {jev}: its typed choice did not run"]
    one = ran[-1]
    if not one.passed:
        return [f"{TASK_CHOICE}: the Jev unit {jev}: {one.why or 'gave no choice'}"]
    out: list[str] = []
    if not one.label:
        out.append(f"{TASK_CHOICE}: the Jev unit {jev}: named no label")
    p = one.probability
    if not _number(p) or not 0.0 <= float(p or 0.0) <= 1.0:
        out.append(f"{TASK_CHOICE}: the Jev unit {jev}: gave no probability ({p!r})")
    return out


def _task_reasons(
    use_case: str,
    fleet: Mapping[str, Any],
    awake: Sequence[str],
    jev: str | None,
    outcomes: Sequence[Outcome],
) -> list[str]:
    units = fleet.get("units") or {}
    if use_case == CODING_USE_CASE:
        return _failed(TASK_GATE, _ran(outcomes, TASK_GATE), "the coding task")
    if use_case == CHAT:
        return [
            reason
            for name in awake
            if name != jev
            for reason in _completion(
                name, units[name], _ran(outcomes, TASK_COMPLETION, name)
            )
        ]
    if use_case == AGENT:
        return [
            *_failed(
                TASK_GROUNDED, _ran(outcomes, TASK_GROUNDED), "the grounded contract"
            ),
            *_failed(TASK_SAFETY, _ran(outcomes, TASK_SAFETY), "the safety check"),
        ]
    if use_case == MEDIA_GEN:
        return [f"{MEDIA_GEN}: {MEDIA_NOT_BUILT}"]
    return [f"use case: {use_case!r} has no sample"]


def _rig_block(saved: Any, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """``card_mib`` for a one-card rig, else ``cards`` held card by card."""
    block: dict[str, Any] = {}
    if len(saved.cards) == 1:
        block["card_mib"] = saved.cards[0].total_mib
    else:
        block["cards"] = {str(card.index): card.total_mib for card in saved.cards}
    block["snapshot"] = dict(snapshot)
    return block


def _slots(slots: Any) -> list[Any]:
    return [list(slot) if slot is not None else None for slot in slots or ()]


def _partners(
    fleets: Mapping[str, Any], name: str
) -> tuple[list[str], list[str]]:
    """The fleets ``name`` switches to, and a reason for each switch that is not a
    fleet of the file or does not list ``name`` back."""
    found: list[str] = []
    why: list[str] = []
    for target in fleets[name].get("next") or ():
        block = fleets.get(target)
        if block is None:
            why.append(f"swap: {name} {TO} {target}: {target} is not a fleet here")
        elif name not in (block.get("next") or ()):
            why.append(f"swap: {target} does not list {name} back in its next")
        elif target not in found:
            found.append(target)
    return found, why


def _sleeper_reasons(
    units: Mapping[str, Any],
    fleets: Mapping[str, Any],
    name: str,
    partners: Sequence[str],
) -> list[str]:
    """A sleeper no fleet ``name`` switches to holds awake, by its name."""
    out: list[str] = []
    for unit_name, unit in units.items():
        if not isinstance(unit, Mapping) or unit.get("role") != ROLE_SLEEPER:
            continue
        woken = any(
            slot is not None and slot[0] == unit_name and slot[1] == AWAKE
            for target in partners
            for slots in (fleets[target].get("layout") or {}).values()
            for slot in slots or ()
        )
        if not woken:
            out.append(
                f"swap: {unit_name} sleeps until needed, and no fleet {name} "
                "switches to wakes it"
            )
    return out


def _move_reasons(
    fleets: Mapping[str, Any],
    name: str,
    partners: Sequence[str],
    moves: Sequence[Move],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Each switch between ``name`` and its partners, both ways and rig by rig:
    a reason per move that did not run, failed or was not timed, and the
    evidence's ``moves``."""
    why: list[str] = []
    evidence: list[dict[str, Any]] = []
    for there in partners:
        for source, target in ((name, there), (there, name)):
            before = fleets[source].get("layout") or {}
            after = fleets[target].get("layout") or {}
            for rig in sorted(set(before) | set(after)):
                if before.get(rig) == after.get(rig):
                    continue
                switch = f"swap: {source} {TO} {target} on {rig}"
                made = [
                    one
                    for one in moves
                    if (one.rig, one.from_fleet, one.to_fleet) == (rig, source, target)
                ]
                if not made:
                    why.append(f"{switch}: the move did not run")
                    continue
                one = made[-1]
                if not one.passed:
                    why.append(f"{switch}: {one.why or 'the move did not pass'}")
                elif one.downtime_s is None or one.wake_s is None:
                    why.append(f"{switch}: its downtime and wake were not timed")
                record: dict[str, Any] = {
                    "rig": rig,
                    "from": _slots(before.get(rig)),
                    "to": _slots(after.get(rig)),
                    "passed": one.passed,
                }
                if one.downtime_s is not None:
                    record["downtime_s"] = one.downtime_s
                if one.wake_s is not None:
                    record["wake_s"] = one.wake_s
                evidence.append(record)
    return why, evidence


def judge(sample: Sample) -> Verdict:
    """The sample judged against plan section 8.2, with its evidence.

    :class:`SampleError` only when the staged setup cannot be read; everything
    a sample can fail on is a reason in the verdict.
    """
    from mcgyvr.fleet.probe import ProbeError, journal_dir
    from mcgyvr.serving import rigfile

    fleet, policy = _setup(sample)
    try:
        journal = sample.journal or journal_dir(sample.setup)
    except ProbeError as exc:
        raise SampleError(str(exc)) from exc
    units = fleet.get("units") or {}
    fleets = fleet["fleets"]
    use_case = str(policy.get("use_case") or DEFAULT_USE_CASE)
    jev_block = policy.get("jev")
    jev = jev_block.get("unit") if isinstance(jev_block, Mapping) else None

    partners, why = _partners(fleets, sample.fleet)
    why.extend(_sleeper_reasons(units, fleets, sample.fleet, partners))
    judged = [sample.fleet, *partners]
    reads = _Reads(sample, journal, judged)

    awake: list[str] = []
    rigs: dict[str, Any] = {}
    saved_rigs: dict[str, Any] = {}
    combinations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    whole = True
    last_at: list[str] = []
    for name in judged:
        layout = fleets[name].get("layout") or {}
        for rig, slots in layout.items():
            key = (rig, json.dumps(_slots(slots)))
            if key in seen:
                continue
            seen.add(key)
            named = [slot for slot in slots or () if slot is not None]
            if name == sample.fleet:
                awake.extend(unit for unit, state in named if state == AWAKE)
            if rig not in saved_rigs:
                try:
                    saved_rigs[rig] = rigfile.read(rig)
                except rigfile.RigFileError as exc:
                    why.append(f"rig file: {rig}: {exc}")
                    saved_rigs[rig] = None
                else:
                    if saved_rigs[rig] is None:
                        why.append(
                            f"rig file: {rig} has no rig file ({rigfile.path(rig)}); "
                            f"`{rigfile.MAKE.format(rig=rig)}` writes it"
                        )
            saved = saved_rigs[rig]
            rows = reads.rig.get((name, rig), [])
            if not rows:
                why.append(
                    f"read: {rig} has no read of {name} from {sample.setup} "
                    f"among the sample's reads ({', '.join(sample.reads) or 'none'})"
                )
            if saved is None or not rows:
                whole = False
                continue
            snapshot = rows[-1].get("snapshot") or {}
            last_at.append(str(rows[-1].get("at") or ""))
            reserves = [
                int(str((row.get("snapshot") or {}).get(RESERVE_FIELD)))
                for row in rows
                if str((row.get("snapshot") or {}).get(RESERVE_FIELD, "")).isdigit()
            ]
            if not reserves:
                why.append(
                    f"read: {rig}: the snapshot of {name} did not read {RESERVE_FIELD}"
                )

            comb: dict[str, Any] = {
                "rig": rig,
                "slots": _slots(slots),
                "restarts": {},
                "warm_decode_tok_s": {},
                "prefill_tok_s": {},
                "baseline_tok_s": {},
                "card_peak_mib": {},
                "card_steady_mib": {},
            }
            if reserves:
                comb["overhead_mib"] = max(reserves)
            backends: dict[str, str] = {}
            for unit_name, state in named:
                unit = units[unit_name]
                read = reads.of_unit(name, str(unit.get("unit_id")))
                if state == AWAKE:
                    why.extend(_probe_reasons(unit_name, unit, read, rows))
                if read.restarts:
                    comb["restarts"][unit_name] = max(read.restarts)
                for field_name in PROBE_FIELDS:
                    if field_name in read.figures:
                        comb[field_name][unit_name] = read.figures[field_name]
                if read.card or read.peaks:
                    comb["card_peak_mib"][unit_name] = max([*read.card, *read.peaks])
                if read.card:
                    comb["card_steady_mib"][unit_name] = read.card[-1]
                if read.backend is not None:
                    backends[unit_name] = read.backend
            if backends:
                comb["attention_backend"] = backends
            comb["envelope"] = sample.envelope
            rigs[rig] = _rig_block(saved, snapshot)
            combinations.append(comb)

    moved, moves = _move_reasons(fleets, sample.fleet, partners, sample.moves)
    why.extend(moved)
    why.extend(_task_reasons(use_case, fleet, awake, jev, sample.outcomes))
    if jev is not None:
        why.extend(_choice(str(jev), _ran(sample.outcomes, TASK_CHOICE, str(jev))))

    green = not why
    evidence: dict[str, Any] | None = None
    if whole:
        validated_at = sample.validated_at or (
            f"{max(last_at)}Z" if last_at and all(last_at) else None
        )
        for comb in combinations:
            comb["passed"] = green
            comb["validated_at"] = validated_at
        evidence = {"rigs": rigs, "combinations": combinations, "moves": moves}
    return Verdict(green=green, why=tuple(why), evidence=evidence)
