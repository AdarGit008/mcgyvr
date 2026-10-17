"""Judging one staged sample: green stamps the fleet, red says why not.

:func:`judge` reads the sample's own read rows out of the journal and the rig
files the reads saved, holds every rig of the fleet's layout to a card reserve
and every awake unit to its probe, then reads the use case's task outcomes
(``coding``'s gate, ``chat``'s completion, ``agent``'s grounded contract and
safety check) and, when the policy names one, the Jev unit's typed choice. Any
reason at all makes the sample red; with none, and with a rig file and a read
for every rig, the verdict carries the ``rigs``/``combinations``/``moves``
evidence a stamp writes and the lock is written from.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeGuard

from mcgyvr.config import CHAT
from mcgyvr.fleet.files import FleetFileError, load_fleet, load_policy
from mcgyvr.fleet.layout import ASLEEP, AWAKE
from mcgyvr.fleet.read import RIG_ROWS

#: The use cases a sample can judge: a policy's `use_case` names one of them,
#: and each is held to its own task in `_task_reasons`.
CODING_USE_CASE = "coding"
AGENT = "agent"
MEDIA_GEN = "media-gen"
#: A policy that names no use case is judged as a coding fleet.
DEFAULT_USE_CASE = CODING_USE_CASE
#: The checks `mcgyvr.fleet.sampler` runs, as `Outcome.check` names them.
TASK_GATE = "gate"
TASK_COMPLETION = "completion"
TASK_GROUNDED = "grounded"
TASK_SAFETY = "safety"
TASK_CHOICE = "choice"
CHECKS = (TASK_GATE, TASK_COMPLETION, TASK_GROUNDED, TASK_SAFETY, TASK_CHOICE)
#: Why a unit laid out asleep makes the sample red: it cannot be woken yet.
SWAP_NOT_BUILT = "the swap isn't built yet (P10)"
#: Why the media-gen use case samples red: it has no sample to run yet.
MEDIA_NOT_BUILT = "the media sample isn't built yet (P11)"
#: The probe figures every awake unit is measured on and read back into evidence.
PROBE_FIELDS = ("warm_decode_tok_s", "prefill_tok_s")
#: The snapshot field that carries the card's reserve, the combination's overhead.
RESERVE_FIELD = "gpu_reserve_mib"


class SampleError(Exception):
    """The sample cannot be judged: its setup or its journal cannot be read."""


@dataclass(frozen=True)
class Outcome:
    """One check's answer, as `mcgyvr.fleet.sampler` ran it.

    `check` is one of `CHECKS`, `unit` the unit it ran on (None for the fleet as
    a whole), `passed` whether it passed, `why` the reason when it did not, and
    `served` what the unit answered back (`window`, `slots`); a typed choice
    also carries its `label` and `probability`.
    """

    check: str
    unit: str | None = None
    passed: bool = False
    why: str = ""
    served: Mapping[str, int] = field(default_factory=dict)
    label: str | None = None
    probability: float | None = None


@dataclass(frozen=True)
class Sample:
    """One sample to judge.

    `setup` is the staged folder its `fleet.yaml` and `policy.yaml` are read
    from and that its reads were filed against, `fleet` the fleet of that setup
    that was laid out, and `reads` the run ids of its reads in the order they
    ran, which is the order their rows are read back in. `journal` overrides the
    folder the rows are filed in, and `validated_at` and `envelope` are carried
    into the evidence when the caller pins them.
    """

    setup: Path
    fleet: str
    reads: Sequence[str]
    outcomes: Sequence[Outcome] = ()
    journal: Path | None = None
    validated_at: str | None = None
    envelope: str | None = None


@dataclass(frozen=True)
class Verdict:
    """What `judge` decided.

    `green` is true only when `why` is empty; `why` holds one line per thing
    that failed, and `evidence` is the dev-run evidence when every rig was read,
    else None.
    """

    green: bool
    why: tuple[str, ...]
    evidence: dict[str, Any] | None


@dataclass
class _UnitRead:
    """One unit's readings, gathered from its read rows.

    `card` and `peaks` are its card readings over the sample and the load peaks
    about it, `restarts` its restart counts, `figures` the probe figures that
    were measured uncontended, `backend` its attention backend, and `alerts` the
    fields that went over the room it was given.
    """

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
    """The sample's read rows, filed by rig and by unit.

    Rows come from the journal's `<run id>/<file>.jsonl`, and are kept only when
    their run id is one of the sample's reads, their fleet is the sample's fleet
    and their setup is the sample's setup. Rows whose file is `RIG_ROWS` are the
    rig's, keyed by rig; the rest are a unit's, keyed by unit id. Each list is
    sorted into the sample's read order, so its last row is the newest read.
    """

    def __init__(self, sample: Sample, journal: Path) -> None:
        order = {run_id: index for index, run_id in enumerate(sample.reads)}
        self.rig: dict[str, list[dict[str, Any]]] = {}
        self.unit: dict[str, list[dict[str, Any]]] = {}
        if not journal.is_dir():
            return
        for path in sorted(journal.glob("*/*.jsonl")):
            for row in _rows(path):
                if (
                    row.get("run_id") not in order
                    or row.get("fleet") != sample.fleet
                    or not _same(row.get("setup"), sample.setup)
                ):
                    continue
                if path.name == RIG_ROWS:
                    self.rig.setdefault(str(row.get("rig")), []).append(row)
                else:
                    self.unit.setdefault(str(row.get("unit_id")), []).append(row)
        for rows in (*self.rig.values(), *self.unit.values()):
            rows.sort(key=lambda row: order[row["run_id"]])

    def of_unit(self, unit_id: str) -> _UnitRead:
        read = _UnitRead()
        for row in self.unit.get(unit_id, []):
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
    """Why no read probed the unit, asked of the newest row first.

    A read that failed on the unit gives its own reason, else the work it had in
    flight, else that it took other work during the probe; a sample whose reads
    never named the unit at all says so.
    """
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
    """One reason per failed outcome of a check, or one saying it never ran.

    Nothing when any of the check's outcomes passed: a check that passed on one
    rung of the fleet is not a red reason.
    """
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


def _rig_block(
    saved: Any, snapshot: Mapping[str, Any], rig_id: object
) -> dict[str, Any]:
    """The evidence for one rig.

    Its rig id when the read observed one, the card size from the rig file the
    scan saved (one `card_mib`, or `cards` by index when the rig has several),
    and the snapshot the sample's last read of it filed.
    """
    block: dict[str, Any] = {}
    if isinstance(rig_id, str) and rig_id:
        block["rig_id"] = rig_id
    if len(saved.cards) == 1:
        block["card_mib"] = saved.cards[0].total_mib
    else:
        block["cards"] = {str(card.index): card.total_mib for card in saved.cards}
    block["snapshot"] = dict(snapshot)
    return block


def judge(sample: Sample) -> Verdict:
    """Judge the sample: green with no reason left, else red with all of them.

    Each rig of the fleet's layout is held to its rig file, to a read of this
    fleet and setup among the sample's reads, and to a card reserve in the
    snapshot; a unit laid out asleep is red because the swap is not built, and
    every awake unit must have its probe figures, restarts, card and room. Then
    the use case's task outcomes are read, and the Jev unit's typed choice when
    the policy names one. The evidence is built only when every rig had both a
    rig file and a read, and is dated the sample's `validated_at`, else the
    newest read's moment.
    """
    from mcgyvr.fleet.probe import ProbeError, journal_dir
    from mcgyvr.serving import rigfile

    fleet, policy = _setup(sample)
    try:
        journal = sample.journal or journal_dir(sample.setup)
    except ProbeError as exc:
        raise SampleError(str(exc)) from exc
    reads = _Reads(sample, journal)
    units = fleet.get("units") or {}
    layout = fleet["fleets"][sample.fleet].get("layout") or {}
    use_case = str(policy.get("use_case") or DEFAULT_USE_CASE)
    jev_block = policy.get("jev")
    jev = jev_block.get("unit") if isinstance(jev_block, Mapping) else None

    why: list[str] = []
    awake: list[str] = []
    rigs: dict[str, Any] = {}
    combinations: list[dict[str, Any]] = []
    whole = True
    last_at: list[str] = []
    for rig, slots in layout.items():
        named = [slot for slot in slots or () if slot is not None]
        for name, state in named:
            if state == ASLEEP:
                why.append(f"swap: {name} sleeps until needed, and {SWAP_NOT_BUILT}")
            elif state == AWAKE:
                awake.append(name)
        try:
            saved = rigfile.read(rig)
        except rigfile.RigFileError as exc:
            why.append(f"rig file: {rig}: {exc}")
            saved = None
        else:
            if saved is None:
                why.append(
                    f"rig file: {rig} has no rig file ({rigfile.path(rig)}); "
                    f"`{rigfile.MAKE.format(rig=rig)}` writes it"
                )
        rows = reads.rig.get(rig, [])
        if not rows:
            why.append(
                f"read: {rig} has no read of {sample.fleet} from {sample.setup} "
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
            why.append(f"read: {rig}: the snapshot did not read {RESERVE_FIELD}")

        comb: dict[str, Any] = {
            "rig": rig,
            "slots": [list(slot) if slot is not None else None for slot in slots],
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
        for name, state in named:
            unit = units[name]
            read = reads.of_unit(str(unit.get("unit_id")))
            if state == AWAKE:
                why.extend(_probe_reasons(name, unit, read, rows))
            if read.restarts:
                comb["restarts"][name] = max(read.restarts)
            for key in PROBE_FIELDS:
                if key in read.figures:
                    comb[key][name] = read.figures[key]
            if read.card or read.peaks:
                comb["card_peak_mib"][name] = max([*read.card, *read.peaks])
            if read.card:
                comb["card_steady_mib"][name] = read.card[-1]
            if read.backend is not None:
                backends[name] = read.backend
        if backends:
            comb["attention_backend"] = backends
        comb["envelope"] = sample.envelope
        rigs[rig] = _rig_block(saved, snapshot, rows[-1].get("observed_rig_id"))
        combinations.append(comb)

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
        evidence = {"rigs": rigs, "combinations": combinations, "moves": []}
    return Verdict(green=green, why=tuple(why), evidence=evidence)
