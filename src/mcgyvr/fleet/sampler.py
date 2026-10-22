"""Samples a staged setup, so a fleet is locked on what it did, not on a claim.

:func:`lay_out` writes the one `own` fleet a staged setup holds into its
`fleet.yaml`: every unit on a read rig is put in its rig's slots, awake or, for
a unit whose role is `sleeps-until-needed`, asleep, with the room the setup
sized for it, the default request timeout when it names none, and the unit id
its lock pins it by. :func:`run` then reads every rig through the door, probes
each awake unit with its `width x window` load, swaps each sleeper in through
the card switches, probes it the same way and swaps it back (:func:`swap`),
sizes each unit's output ceiling from its measured warm decode
(:func:`_reply_ceilings`), runs the policy's use case task and any opted-in
Jev's choice (:func:`task`), and reads every rig once more. The
:class:`~mcgyvr.fleet.sample.Sample` it answers with carries the read ids, the
swaps' moves, the outcomes and the door reads that failed, which
:func:`mcgyvr.fleet.stamp.stamp` judges.

The use case decides the task. `coding` runs the bundled bug fix through
`mcgyvr run` and passes when the deterministic gate accepts it on any rung.
`agent` puts the bundled grounded question straight to one awake unit and
passes when its reply cites its source and states every fact. `chat` asks every
awake unit for one word and reads back the window and slots it serves. A sample
reaches a machine only through the door subprocess or a dispatched request.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from mcgyvr.config import (
    CHAT,
    CONFIG_PATH_ENV,
    DEFAULT_REQUEST_TIMEOUT_S,
    ROLE_SLEEPER,
)
from mcgyvr.fleet import ids
from mcgyvr.fleet.files import FleetFileError, load_fleet, load_policy
from mcgyvr.fleet.layout import ASLEEP, AWAKE
from mcgyvr.fleet.lock import OWN_FLEET
from mcgyvr.fleet.sample import (
    AGENT,
    CODING_USE_CASE,
    DEFAULT_USE_CASE,
    TASK_CHOICE,
    TASK_COMPLETION,
    TASK_GATE,
    TASK_GROUNDED,
    WAY_BACK,
    WAY_IN,
    Move,
    Outcome,
    Sample,
    sleeper,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.ladder_manager import Switches

#: The one fleet a staged setup holds, laid out, sampled and journaled under.
FLEET = OWN_FLEET
#: The bundled sample each use case's task is taken from, in the package's folder.
SAMPLES = {CODING_USE_CASE: "coding.yaml", AGENT: "agent.yaml"}
#: Who the sample's own `mcgyvr run` is journaled as, so its rows are told apart
#: from the rows of whatever orchestrator is running setup.
ORCHESTRATOR = "mcgyvr-setup"
#: The one-word ask a chat sample puts to each awake unit, and its reply cap.
CHAT_PROMPT = "Reply with the single word: ready."
CHAT_TOKENS = 16
#: The typed choice the Jev unit answers, and what each of its labels means.
JEV_INSTRUCTIONS = "Is a fleet whose every unit answered ready to serve?"
JEV_OPTIONS = {"ready": "every unit answered", "not_ready": "a unit did not"}


class SamplerError(Exception):
    """The staged setup cannot be read, laid out or asked, so no sample is taken."""


@dataclass(frozen=True)
class Ran:
    """What one sample run produced: the sample to judge, and the reads that failed.

    `failed` names each door read that exited non-zero, so a sample taken across
    a flaky rig still says on its face where it was read and what did not answer.
    """

    sample: Sample
    failed: tuple[str, ...] = field(default_factory=tuple)


def unit_id(unit: Mapping[str, Any]) -> str:
    """The id a laid-out unit is pinned by: a digest of what places and runs it.

    The engine, image, container, launch spec, model and address are digested
    under the unit prefix, a missing engine read as llama.cpp, so the id changes
    exactly when what the unit is or where it answers changes.
    """
    return ids.digest(
        "unt-",
        {
            "engine": str(unit.get("engine") or "llama.cpp"),
            "image": str(unit.get("image") or ""),
            "container": str(unit.get("container") or ""),
            "launch": unit.get("launch") or {},
            "model": str(unit.get("model") or ""),
            "address": str(unit.get("address") or ""),
        },
    )


def _read(setup: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        fleet = load_fleet((setup / "fleet.yaml").read_text(encoding="utf-8"))
        policy = load_policy((setup / "policy.yaml").read_text(encoding="utf-8"))
    except (OSError, FleetFileError) as exc:
        raise SamplerError(f"the staged setup {setup} cannot be read: {exc}") from exc
    return fleet, policy


def lay_out(setup: Path, rigs: Mapping[str, str], rooms: Mapping[str, int]) -> None:
    """Write the `own` fleet's layout into the staged setup's `fleet.yaml`.

    Every unit on a rig goes into its rig's slot list, asleep when its role is
    `sleeps-until-needed` (its launch spec leaves it down) and awake otherwise,
    with the room the setup sized for it, the default request timeout where it
    names none, and the unit id its lock pins it by. Rigs are recorded with the
    id each was read by,
    and the fleet's `next` list starts empty. A unit on a rig that was not read,
    or one with no room sized for it, refuses the layout: the lock would have no
    card to hold the unit to, so none is written.
    """
    fleet, _policy = _read(setup)
    units: dict[str, Any] = fleet.get("units") or {}
    on_rigs = {name: body for name, body in units.items() if "rig" in body}
    unread = sorted(
        f"{name} (on {body['rig']})"
        for name, body in on_rigs.items()
        if str(body["rig"]) not in rigs
    )
    if unread:
        raise SamplerError(
            f"{', '.join(unread)} sits on a rig that was not read, so it cannot "
            "be laid out"
        )
    roomless = sorted(
        name
        for name, body in on_rigs.items()
        if "room_mib" not in body and name not in rooms
    )
    if roomless:
        raise SamplerError(
            f"{', '.join(roomless)}: no card room was sized for it, so the lock "
            "has nothing to hold its card to"
        )
    layout: dict[str, list[list[str]]] = {}
    for name, body in on_rigs.items():
        body.setdefault("room_mib", int(rooms[name]) if name in rooms else None)
        body.setdefault("request_timeout_s", DEFAULT_REQUEST_TIMEOUT_S)
        body["unit_id"] = unit_id(body)
        state = ASLEEP if body.get("role") == ROLE_SLEEPER else AWAKE
        layout.setdefault(str(body["rig"]), []).append([name, state])
    fleet["rigs"] = {rig: {"rig_id": rigs[rig]} for rig in layout}
    fleet["fleets"] = {FLEET: {"layout": layout, "next": []}}
    (setup / "fleet.yaml").write_text(
        yaml.safe_dump(fleet, sort_keys=False), encoding="utf-8"
    )


def _reply_ceilings(setup: Path, reads: Sequence[str]) -> None:
    """Give each read unit an output ceiling from the warm decode it measured.

    The ceiling is the warm decode rate times the unit's request timeout, clipped
    to its window, so a reply is capped at what the unit can finish inside the
    timeout it is held to. A unit off every rig, one that already names an
    `output_tokens`, and one whose reads measured no warm decode all keep what
    they have, and `fleet.yaml` is written only when some unit changed.
    """
    from mcgyvr.fleet.probe import ProbeError, journal_dir
    from mcgyvr.fleet.sample import _Reads

    fleet, _policy = _read(setup)
    try:
        journal = journal_dir(setup)
    except ProbeError:
        return
    rows = _Reads(Sample(setup=setup, fleet=FLEET, reads=tuple(reads)), journal)
    changed = False
    for body in (fleet.get("units") or {}).values():
        if "rig" not in body or body.get("output_tokens") is not None:
            continue
        warm = rows.of_unit(str(body.get("unit_id"))).figures.get("warm_decode_tok_s")
        if not warm:
            continue
        timeout = float(body.get("request_timeout_s") or DEFAULT_REQUEST_TIMEOUT_S)
        ceiling = int(warm * timeout)
        window = body.get("window")
        if isinstance(window, int) and not isinstance(window, bool) and window > 0:
            ceiling = min(ceiling, window)
        if ceiling > 0:
            body["output_tokens"] = ceiling
            changed = True
    if changed:
        (setup / "fleet.yaml").write_text(
            yaml.safe_dump(fleet, sort_keys=False), encoding="utf-8"
        )


def _door_read(
    setup: Path,
    rig: str,
    run_id: str,
    probe: Sequence[str] = (),
    load: str | None = None,
) -> int:
    """Run the door's `read` on one rig under a fresh run id, and answer with its code.

    The argv is this interpreter and the door module, the verb, the rig's host,
    the `own` fleet and the run id the rows are filed under, plus the unit to
    probe and the `width x window` load to place on the card when either is
    given. The configuration path is the staged setup, so the door journals the
    read into the setup being sampled.
    """
    from mcgyvr import wake
    from mcgyvr.serving.gatelib import DOOR_MODULE

    argv = [sys.executable, "-m", DOOR_MODULE, "read", "--host", rig]
    argv += ["--fleet", FLEET, "--run-id", run_id]
    if probe:
        argv += ["--probe", *probe]
    if load:
        argv += ["--load", load]
    # The door answers with its exit code, so a door that could not read the rig
    # is a code this side records rather than an exception it raises.
    return wake.spawn_door(argv, env={**os.environ, CONFIG_PATH_ENV: str(setup)})


def _bundled(use_case: str) -> dict[str, Any]:
    text = (resources.files("mcgyvr") / "samples" / SAMPLES[use_case]).read_text(
        encoding="utf-8"
    )
    loaded: dict[str, Any] = yaml.safe_load(text)
    return loaded


def _repository(where: Path, files: Mapping[str, str]) -> Path:
    """Write the sample's starting files into a fresh git repository and commit them.

    The `repo` folder under `where` is created, each named file written with its
    body, and the tree committed as `sample` under an identity of this module's
    own with global and system git config switched off, so the sample's run sees
    history it did not have to trust a developer's settings for.
    """
    repo = where / "repo"
    repo.mkdir(parents=True)
    for name, body in files.items():
        (repo / name).write_text(body, encoding="utf-8")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    who = ["-c", "user.name=mcgyvr", "-c", "user.email=setup@mcgyvr.invalid"]
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "sample"]):
        subprocess.run(
            ["git", *who, *args],
            cwd=repo,
            env=env,
            check=True,
            capture_output=True,
        )
    return repo


#: One `mcgyvr run`, reached by the argv to run and answered with its exit code.
RunContract = Callable[[list[str]], int]


def _contract_run(
    setup: Path, use_case: str, where: Path, run_contract: RunContract
) -> dict[str, Any]:
    """Run the use case's bundled contract on the staged setup and read its result.

    The bundled contract is dumped to `contract.yaml` and its files committed into
    a repository under `where`, and the contract runner is handed the `run` argv
    naming the contract, that repository, the staged setup, this sample's
    orchestrator id and where the result goes. Whatever the runner wrote there is
    returned as a dict; a result that is missing, unreadable or not an object
    becomes an `error` outcome rather than passing for a run that never happened.
    """
    sample = _bundled(use_case)
    where.mkdir(parents=True, exist_ok=True)
    repo = _repository(where, sample.get("files") or {})
    contract = where / "contract.yaml"
    contract.write_text(yaml.safe_dump(sample["contract"]), encoding="utf-8")
    result = where / "result.json"
    run_contract(
        [
            "run",
            str(contract),
            "--repo",
            str(repo),
            "--config",
            str(setup),
            "--orchestrator",
            ORCHESTRATOR,
            "--result",
            str(result),
        ]
    )
    try:
        loaded = json.loads(result.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"outcome": "error", "detail": f"no result file was written ({exc})"}
    return loaded if isinstance(loaded, dict) else {"outcome": "error"}


def grounded(answer: str, citation: str, facts: Sequence[str]) -> str | None:
    """Why the reply is not grounded in its source, or None when it is.

    The reply is split into sentences and every one of them must end with the
    citation, then every fact must appear in the reply, case aside. The answer is
    the first reason it fails, naming the sentences that do not cite or the facts
    the reply leaves out, and an empty reply is a reason of its own.
    """
    sentences = [s.strip() for s in answer.replace("\n", " ").split(".") if s.strip()]
    if not sentences:
        return "the reply is empty"
    uncited = [s for s in sentences if not s.endswith(citation)]
    if uncited:
        return f"{len(uncited)} sentence(s) do not cite the source {citation}"
    missing = [fact for fact in facts if fact.lower() not in answer.lower()]
    if missing:
        return f"the reply does not state {', '.join(missing)}"
    return None


def complete(setup: Path, unit: str) -> str:
    """Ask one unit of the staged setup for the single word `ready` and answer its text.

    The request is dispatched at the unit through the setup's source map with the
    chat reply cap as its output ceiling, and the reply text is returned as it
    was sent, so a caller can tell an empty answer from an absent one.
    """
    from mcgyvr.config import load
    from mcgyvr.local_pool import source_map
    from mcgyvr.runner import Request, dispatch

    answer = dispatch(
        source_map(load(setup)),
        unit,
        Request(prompt=CHAT_PROMPT, max_output_tokens=CHAT_TOKENS),
    )
    return str(answer.text)


def ground(setup: Path, unit: str) -> str:
    """Put the bundled agent question to one unit of the staged setup, raw.

    The sample's files are rendered as numbered sources, the way a worker is
    shown them, under its task, and the request is dispatched at the unit
    through the setup's source map with no output cap: the agent use case is
    the served model used directly. The reply text is returned as it was sent.
    """
    from mcgyvr.config import load
    from mcgyvr.local_pool import source_map
    from mcgyvr.runner import Request, dispatch
    from mcgyvr.worker.prompt import _render_sources

    sample = _bundled(AGENT)
    sources = _render_sources(
        [
            {"path": path, "content": content}
            for path, content in (sample.get("files") or {}).items()
        ]
    )
    answer = dispatch(
        source_map(load(setup)),
        unit,
        Request(
            prompt=f"{sample['task']}\nSOURCES:\n{sources}\n",
            max_output_tokens=None,
        ),
    )
    return str(answer.text)


def served(unit: Mapping[str, Any]) -> dict[str, int]:
    """The window and slots a unit reports serving, as its own engine reports them.

    A vLLM unit's window is read from its models listing's `max_model_len`; a
    llama.cpp unit's window from its props' `n_ctx` and its slots from
    `total_slots`, after the address's `/v1` suffix is dropped. A figure the
    endpoint does not state, or does not answer at all, is left out.
    """
    from mcgyvr.detect import _get_json, _window_from

    base = str(unit.get("address") or "").rstrip("/").removesuffix("/v1")
    out: dict[str, int] = {}
    if str(unit.get("engine") or "llama.cpp") == "vllm":
        window = _window_from(
            _get_json(f"{base}/v1/models", 5.0), ("data", "max_model_len")
        )
        if window is not None:
            out["window"] = window
        return out
    props = _get_json(f"{base}/props", 5.0)
    window = _window_from(props, ("default_generation_settings", "n_ctx"))
    slots = _window_from(props, ("total_slots",))
    if window is not None:
        out["window"] = window
    if slots is not None:
        out["slots"] = slots
    return out


def choose(setup: Path) -> tuple[str, float]:
    """Ask the Jev unit whether the sampled fleet is ready, and answer its
    choice and odds.

    The question is the fleet-level one, put to the unit the staged policy binds
    to the Jev role. The answer is the label it picked and the probability its
    answer gave that label, -1.0 when the answer carries none. A policy that
    binds no Jev unit, or an answer that is not a typed choice, refuses the
    sample rather than inventing one.
    """
    from mcgyvr.config import load
    from mcgyvr.decision import JEV_ROLE, Choice, ChoiceAnswer, classify_role
    from mcgyvr.local_pool import source_map

    decided = classify_role(
        source_map(load(setup)),
        JEV_ROLE,
        {"sample": "every unit of the staged fleet answered its sample"},
        {"sample": Choice(instructions=JEV_INSTRUCTIONS, options=JEV_OPTIONS)},
    )
    if decided is None:
        raise SamplerError("jev.unit binds no unit")
    answer = decided.answers["sample"]
    if not isinstance(answer, ChoiceAnswer):
        raise SamplerError("the Jev unit's answer is not a choice")
    return answer.choice, float(answer.probabilities.get(answer.choice, -1.0))


def _guarded(check: str, unit: str | None, call: Callable[[], Outcome]) -> Outcome:
    """Run one check, turning whatever it raised into an outcome it failed.

    The outcome names the check and the unit it was meant to judge, and carries
    the exception's type and message as its reason, so one check that broke on an
    unreachable machine or a malformed reply leaves the other checks to run.
    """
    try:
        return call()
    except Exception as exc:
        return Outcome(
            check=check, unit=unit, passed=False, why=f"{type(exc).__name__}: {exc}"
        )


def task(
    setup: Path, awake: Sequence[str], where: Path, run_contract: RunContract
) -> list[Outcome]:
    """Run the policy's use case task and the Jev choice, one outcome per check.

    `coding` runs the bundled bug fix through the contract runner and passes when
    the gate accepts it, naming the rung it was accepted on. `agent` asks the
    first awake unit but the Jev unit the bundled grounded question, and checks
    its reply for the citations and facts the bundled sample names. `chat` asks
    each awake unit but the Jev unit for one word, passing with the window and slots the
    unit reports and failing when it answers nothing. A policy that opts a unit in
    to Jev gets one typed choice from it, checked last. Every check is guarded, so
    a raise is one failed outcome rather than a lost sample.
    """
    fleet, policy = _read(setup)
    use_case = str(policy.get("use_case") or DEFAULT_USE_CASE)
    jev_block = policy.get("jev")
    jev = jev_block.get("unit") if isinstance(jev_block, Mapping) else None
    units = fleet.get("units") or {}
    outcomes: list[Outcome] = []

    if use_case == CODING_USE_CASE:

        def gate() -> Outcome:
            done = _contract_run(setup, use_case, where / use_case, run_contract)
            outcome = str(done.get("outcome"))
            return Outcome(
                check=TASK_GATE,
                unit=done.get("rung"),
                passed=outcome == "accepted",
                why=""
                if outcome == "accepted"
                else f"{outcome}: {done.get('detail', '')}",
            )

        outcomes.append(_guarded(TASK_GATE, None, gate))
    elif use_case == AGENT:
        sample = _bundled(use_case)
        asked = next((name for name in awake if name != jev), None)

        def answer() -> Outcome:
            if asked is None:
                return Outcome(check=TASK_GROUNDED, unit=None, why="no awake unit")
            not_grounded = grounded(
                ground(setup, asked),
                str(sample.get("citation") or "[1]"),
                sample.get("facts") or (),
            )
            return Outcome(
                check=TASK_GROUNDED,
                unit=asked,
                passed=not_grounded is None,
                why=not_grounded or "",
            )

        outcomes.append(_guarded(TASK_GROUNDED, asked, answer))
    elif use_case == CHAT:
        for name in awake:
            if name == jev:
                continue

            def one(name: str = name) -> Outcome:
                said = complete(setup, name).strip()
                if not said:
                    return Outcome(
                        check=TASK_COMPLETION, unit=name, why="answered nothing"
                    )
                return Outcome(
                    check=TASK_COMPLETION,
                    unit=name,
                    passed=True,
                    served=served(units[name]),
                )

            outcomes.append(_guarded(TASK_COMPLETION, name, one))

    if jev is not None:

        def pick() -> Outcome:
            label, probability = choose(setup)
            return Outcome(
                check=TASK_CHOICE,
                unit=str(jev),
                passed=True,
                label=label,
                probability=probability,
            )

        outcomes.append(_guarded(TASK_CHOICE, str(jev), pick))
    return outcomes


@dataclass(frozen=True)
class _Call:
    """One switch call: its verb, the unit, whether it worked, and when it ran."""

    verb: str
    unit: str
    ok: bool
    started: float
    ended: float


class _Timed:
    """The card switches, each sleep and wake timed on `clock`.

    The calls are kept in the order they ran until :meth:`move` turns them into
    one way of a swap and starts the next way afresh.
    """

    def __init__(self, switches: Switches, clock: Callable[[], float]) -> None:
        self._switches = switches
        self._clock = clock
        self._calls: list[_Call] = []

    def _timed(self, verb: str, unit: str, call: Callable[[str], bool]) -> bool:
        started = self._clock()
        ok = bool(call(unit))
        self._calls.append(_Call(verb, unit, ok, started, self._clock()))
        return ok

    def wake(self, rung: str) -> bool:
        return self._timed("wake", rung, self._switches.wake)

    def sleep(self, rung: str) -> bool:
        return self._timed("sleep", rung, self._switches.sleep)

    def why_failed(self, rung: str) -> str | None:
        return self._switches.why_failed(rung)

    def room_for(self, rung: str) -> tuple[str, ...]:
        return tuple(self._switches.room_for(rung))

    def card_of(self, rung: str) -> tuple[str, ...]:
        return tuple(self._switches.card_of(rung))

    def move(
        self, rig: str, unit: str, way: str, room: tuple[str, ...], lines: list[str]
    ) -> Move:
        """The way the calls since the last move made, one line per call.

        It passed when there was a call and every call worked; its reason is the
        line of the first call that did not. Its downtime runs from the start of
        its first call to the end of its last, and each unit a wake that worked
        woke is timed by that wake.
        """
        calls, self._calls = self._calls, []
        failed = [line for call, line in zip(calls, lines, strict=True) if not call.ok]
        return Move(
            rig=rig,
            unit=unit,
            way=way,
            room=room,
            passed=bool(calls) and not failed,
            downtime_s=(
                round(calls[-1].ended - calls[0].started, 3) if calls else None
            ),
            wake_s={
                call.unit: round(call.ended - call.started, 3)
                for call in calls
                if call.verb == "wake" and call.ok
            },
            why=failed[0] if failed else "",
        )


def swap(
    rig: str,
    unit: str,
    switches: Switches,
    probe: Callable[[], object],
    *,
    clock: Callable[[], float] = time.monotonic,
) -> list[Move]:
    """Swap one sleeper in through the card switches, probe it, and swap it
    back; one :class:`~mcgyvr.fleet.sample.Move` per way it went.

    In is a wake making room: the units the switches name as the sleeper's
    `room_for` are put down and the sleeper is woken into their memory
    (:func:`mcgyvr.ladder_manager.wake_making_room`), the room woken back when
    either fails. Only a sleeper that went in is probed, and then put down with
    its room woken back (:func:`mcgyvr.ladder_manager.give_back`); a sleeper that
    would not go down keeps its room. Each switch call is timed on `clock`.
    """
    from mcgyvr.ladder_manager import give_back, wake_making_room

    timed = _Timed(switches, clock)
    room = timed.room_for(unit)
    lines, slept = wake_making_room(timed, unit, room)
    went_in = timed.move(rig, unit, WAY_IN, room, lines)
    if slept is None:
        return [went_in]
    probe()
    down = timed.sleep(unit)
    lines = [f"sleep {unit}: {'done' if down else 'failed'}"]
    if down:
        lines += give_back(timed, slept)
    return [went_in, timed.move(rig, unit, WAY_BACK, slept, lines)]


def switches_for(setup: Path, rigs: Sequence[str]) -> Switches:
    """The card switches over the staged setup's cards.

    Built from the setup's config and its capacity, with each rig's card
    memory read from the rig file its read saved. A config that cannot be
    loaded, or that does not let mcgyvr sleep and wake a unit itself
    (`serving.enable_sleep_wake` and `serving.compose_dir`), is a
    :class:`SamplerError` saying so.
    """
    from mcgyvr import wake
    from mcgyvr.capacity import Capacity, CapacityError
    from mcgyvr.config import ConfigError, load

    try:
        config = load(setup)
        capacity = Capacity.of(config)
    except (ConfigError, CapacityError, OSError) as exc:
        raise SamplerError(
            f"the card switches cannot be built for {setup}: {exc}"
        ) from exc
    if wake.for_config(config) is None:
        raise SamplerError(
            f"{setup} does not let mcgyvr sleep and wake a unit itself "
            "(serving.enable_sleep_wake with serving.compose_dir), so the "
            "card switches cannot wake it"
        )
    return wake.CardSwitches(config, capacity, card_mib=wake.saved_card_mib(rigs))


def run(
    setup: Path,
    *,
    run_contract: RunContract,
    mint: Callable[[], str] | None = None,
    switches: Switches | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> Ran:
    """Sample the staged setup, reading every rig around the task it runs.

    Each rig in the `own` layout is read, and each of its awake slots is read
    again with that unit probed and its `width x window` load placed, so the
    journal holds both the rig and what sits in it. Each sleeper is then swapped
    in through `switches` (by default the card switches over the setup's
    cards, :func:`switches_for`), read the same way while it is in, and swapped
    back (:func:`swap`); switches that cannot be built are a move in that did
    not pass. Those reads size the units' output ceilings, the task and the Jev
    choice then run against the setup's `sample` folder, and every rig is read
    once more to bracket the work. `mint` names each read and defaults to a
    fresh read id. A layout that names no `own` fleet refuses; a door that exits
    non-zero is kept in `failed` instead, so a sample taken through a flaky rig
    still says what did not answer.
    """
    from mcgyvr.serving.run import mint_read_id

    name = mint or mint_read_id
    fleet, _policy = _read(setup)
    layout = (fleet.get("fleets") or {}).get(FLEET, {}).get("layout")
    if not isinstance(layout, Mapping):
        raise SamplerError(f"{setup / 'fleet.yaml'} lays out no fleet {FLEET}")
    units = fleet.get("units") or {}
    reads: list[str] = []
    failed: list[str] = []

    def read(rig: str, probe: Sequence[str] = (), load: str | None = None) -> None:
        run_id = name()
        code = _door_read(setup, rig, run_id, probe, load)
        what = f"read --host {rig}" + (f" --probe {' '.join(probe)}" if probe else "")
        if code == 0:
            reads.append(run_id)
        else:
            failed.append(f"{what} exited {code}")

    def probe(rig: str, held: str) -> None:
        unit = units[held]
        width, window = unit.get("width"), unit.get("window")
        load = f"{width}x{window}" if width and window else None
        read(rig, (held,), load)

    awake: list[str] = []
    sleepers: list[tuple[str, str]] = []
    for rig, slots in layout.items():
        read(rig)
        for slot in slots or ():
            if slot is None:
                continue
            held = str(slot[0])
            if sleeper(units[held], str(slot[1])):
                sleepers.append((str(rig), held))
            elif slot[1] == AWAKE:
                awake.append(held)
                probe(rig, held)
    moves: list[Move] = []
    if sleepers:
        try:
            made = (
                switches
                if switches is not None
                else switches_for(setup, [str(rig) for rig in layout])
            )
        except SamplerError as exc:
            moves = [Move(rig, held, WAY_IN, why=str(exc)) for rig, held in sleepers]
        else:
            for rig, held in sleepers:

                def probed(rig: str = rig, held: str = held) -> None:
                    probe(rig, held)

                moves += swap(rig, held, made, probed, clock=clock)
    _reply_ceilings(setup, reads)
    outcomes = task(setup, awake, setup / "sample", run_contract)
    for rig in layout:
        read(rig)
    return Ran(
        sample=Sample(
            setup=setup,
            fleet=FLEET,
            reads=tuple(reads),
            outcomes=outcomes,
            moves=tuple(moves),
        ),
        failed=tuple(failed),
    )
