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
* **no unit sleeps**: until P10 builds the llama.cpp swap, a fleet with an
  asleep slot is red (owner, Round 8).

What the reads measured becomes the dev-run evidence ``mcgyvr fleet lock``
already reads (:mod:`mcgyvr.fleet.lock`): the rig file the user's scan saved
(:mod:`mcgyvr.serving.rigfile`) gives each card's MiB, the last read's
snapshot names the rig and gives the card's reserve as the combination's
overhead, and each unit's card peak is the highest card reading around the
sample (its card and its load's peak), its steady card the last read's. The
evidence carries ``passed`` as the sample's verdict. Nothing here reads a rig
or writes a file.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeGuard

from mcgyvr.fleet.files import FleetFileError, load_fleet, load_policy
from mcgyvr.fleet.layout import ASLEEP, AWAKE
from mcgyvr.fleet.read import RIG_ROWS

#: The use cases and the task outcome each is judged by (plan section 8.2).
CODING = "coding"
CHAT = "chat"
AGENT = "agent"
MEDIA_GEN = "media-gen"
#: The use case a policy that names none runs, as the config's default.
DEFAULT_USE_CASE = CODING
#: The checks an :class:`Outcome` reports.
GATE = "gate"
COMPLETION = "completion"
GROUNDED = "grounded"
SAFETY = "safety"
CHOICE = "choice"
CHECKS = (GATE, COMPLETION, GROUNDED, SAFETY, CHOICE)
#: Why a fleet with a sleeper is not stamped yet (owner, Round 8).
SWAP_NOT_BUILT = "the swap isn't built yet (P10)"
#: Why a media-gen fleet is not stamped yet.
MEDIA_NOT_BUILT = "the media sample isn't built yet (P11)"
#: The figures every awake unit's probe must read.
PROBE_FIELDS = ("warm_decode_tok_s", "prefill_tok_s")
#: The snapshot reading the combination's overhead is taken from.
RESERVE = "gpu_reserve_mib"


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
class Sample:
    """What ran: the staged setup, the reads of it, and the task's outcomes.

    ``reads`` are the door read ids of the sample, in the order taken; the last
    one that read a rig is its steady state. ``journal`` is where those reads
    filed, by default the setup's own (``journal.dir`` of its ``policy.yaml``).
    ``validated_at`` is by default the moment of the sample's last read.
    ``envelope`` is the door run's envelope, when it filed one.
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
    """The rows the sample's reads filed for its fleet, from its setup, in order."""

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
        return [f"{COMPLETION}: {name}: did not run"]
    one = ran[-1]
    if not one.passed:
        return [f"{COMPLETION}: {name}: {one.why or 'did not answer'}"]
    out: list[str] = []
    for key, planned_key in (("window", "window"), ("slots", "width")):
        planned = unit.get(planned_key)
        served = one.served.get(key)
        if served is None:
            out.append(f"{COMPLETION}: {name}: its {key} was not read back")
        elif planned is None or int(served) != int(planned):
            out.append(
                f"{COMPLETION}: {name}: served {key} {served}, planned {planned}"
            )
    return out


def _choice(jev: str, ran: Sequence[Outcome]) -> list[str]:
    if not ran:
        return [f"{CHOICE}: the Jev unit {jev}: its typed choice did not run"]
    one = ran[-1]
    if not one.passed:
        return [f"{CHOICE}: the Jev unit {jev}: {one.why or 'gave no choice'}"]
    out: list[str] = []
    if not one.label:
        out.append(f"{CHOICE}: the Jev unit {jev}: named no label")
    p = one.probability
    if not _number(p) or not 0.0 <= float(p or 0.0) <= 1.0:
        out.append(f"{CHOICE}: the Jev unit {jev}: gave no probability ({p!r})")
    return out


def _task_reasons(
    use_case: str,
    fleet: Mapping[str, Any],
    awake: Sequence[str],
    jev: str | None,
    outcomes: Sequence[Outcome],
) -> list[str]:
    units = fleet.get("units") or {}
    if use_case == CODING:
        return _failed(GATE, _ran(outcomes, GATE), "the coding task")
    if use_case == CHAT:
        return [
            reason
            for name in awake
            if name != jev
            for reason in _completion(
                name, units[name], _ran(outcomes, COMPLETION, name)
            )
        ]
    if use_case == AGENT:
        return [
            *_failed(GROUNDED, _ran(outcomes, GROUNDED), "the grounded contract"),
            *_failed(SAFETY, _ran(outcomes, SAFETY), "the safety check"),
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
            int(str((row.get("snapshot") or {}).get(RESERVE)))
            for row in rows
            if str((row.get("snapshot") or {}).get(RESERVE, "")).isdigit()
        ]
        if not reserves:
            why.append(f"read: {rig}: the snapshot did not read {RESERVE}")

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
        rigs[rig] = _rig_block(saved, snapshot)
        combinations.append(comb)

    why.extend(_task_reasons(use_case, fleet, awake, jev, sample.outcomes))
    if jev is not None:
        why.extend(_choice(str(jev), _ran(sample.outcomes, CHOICE, str(jev))))

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
