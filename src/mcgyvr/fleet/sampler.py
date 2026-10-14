"""The sampler: a staged setup's sample, run through the door and the task.

Owner, Round 4 (2026-10-07): the owner's confirm is approval to run the
SAMPLE -- start the servers and run the sample check task. ``mcgyvr setup``
stages a setup (:func:`mcgyvr.fleet.roots.staging_dir`), starts its units
through the door, and hands the staged setup here. This module builds the
:class:`~mcgyvr.fleet.sample.Sample` :func:`~mcgyvr.fleet.stamp.stamp` judges:

* :func:`lay_out` makes the staged setup one fleet, :data:`FLEET`, laid out
  with every unit on a rig awake on its rig: each rig pinned to the rig id its
  read named, and each unit given the id the lock pins (:func:`unit_id`), the
  card room it was sized at, and the request timeout it runs under.
* :func:`run` takes the door's reads of it -- through
  :func:`mcgyvr.wake.spawn_door`, the one seam a product caller opens the door
  by -- ``read --fleet F`` of every rig, then ``read --fleet F --probe U --load
  WxN`` of every awake unit, and a last plain read of every rig, its steady
  state; and between them runs the use case's sample task (:func:`task`):
  ``coding`` the bundled bug fix (``samples/coding.yaml``) through ``mcgyvr
  run``, where the deterministic gate passes on any rung; ``agent`` the bundled
  grounded contract (``samples/agent.yaml``) through ``mcgyvr run``, its reply
  checked grounded and by the safety check; ``chat`` one completion per awake
  unit, and the window and slots it serves read back off it. An opted-in Jev
  unit (``jev.unit``) is asked one typed choice. ``media-gen`` has no sample
  task (:data:`~mcgyvr.fleet.sample.MEDIA_NOT_BUILT`), and the judge says so.

Nothing here locks, promotes or names a fleet live, and nothing reaches a
machine but through the door and the units' own endpoints. Every reach is a
module-level function a test replaces: :func:`run_contract`,
:func:`complete`, :func:`served`, :func:`choose`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from mcgyvr.config import CHAT, CONFIG_PATH_ENV, DEFAULT_REQUEST_TIMEOUT_S
from mcgyvr.fleet import ids
from mcgyvr.fleet.files import FleetFileError, load_fleet, load_policy
from mcgyvr.fleet.layout import AWAKE
from mcgyvr.fleet.lock import OWN_FLEET
from mcgyvr.fleet.sample import (
    AGENT,
    CODING_USE_CASE,
    DEFAULT_USE_CASE,
    TASK_CHOICE,
    TASK_COMPLETION,
    TASK_GATE,
    TASK_GROUNDED,
    TASK_SAFETY,
    Outcome,
    Sample,
)

#: The fleet a staged setup is laid out as: the user's own.
FLEET = OWN_FLEET
#: The bundled sample tasks, by use case.
SAMPLES = {CODING_USE_CASE: "coding.yaml", AGENT: "agent.yaml"}
#: Who ``mcgyvr run`` files the sample task's rows under.
ORCHESTRATOR = "mcgyvr-setup"
#: The one completion a chat sample asks of each unit.
CHAT_PROMPT = "Reply with the single word: ready."
CHAT_TOKENS = 16
#: The one typed choice a Jev sample asks.
JEV_INSTRUCTIONS = "Is a fleet whose every unit answered ready to serve?"
JEV_OPTIONS = {"ready": "every unit answered", "not_ready": "a unit did not"}


class SamplerError(Exception):
    """The staged setup cannot be laid out or sampled; the message says why."""


@dataclass(frozen=True)
class Ran:
    """What :func:`run` did: the sample, and each door read that failed."""

    sample: Sample
    failed: tuple[str, ...] = field(default_factory=tuple)


def unit_id(unit: Mapping[str, Any]) -> str:
    """``unt-`` for a unit setup launched, over what it launches as: its engine,
    image, container, launch, the model it serves and where it answers."""
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
    """Lay the staged setup at ``setup`` out as :data:`FLEET`, every rig unit awake.

    ``rigs`` maps each rig a unit sits on to the rig id its read named;
    ``rooms`` each unit to the card room, MiB, it was sized at. A unit keeps
    what it already states. Refused, with nothing written, when a unit sits on
    a rig that was not read, or a rig unit has no room to state.
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
        layout.setdefault(str(body["rig"]), []).append([name, AWAKE])
    fleet["rigs"] = {rig: {"rig_id": rigs[rig]} for rig in layout}
    fleet["fleets"] = {FLEET: {"layout": layout, "next": []}}
    (setup / "fleet.yaml").write_text(
        yaml.safe_dump(fleet, sort_keys=False), encoding="utf-8"
    )


def _reply_ceilings(setup: Path, reads: Sequence[str]) -> None:
    """State each probed rig unit's ``output_tokens``: the longest reply its
    measured warm decode finishes inside its ``request_timeout_s``, no longer
    than its ``window``. A unit that states one keeps it; one whose rate was
    not read is left as it is, and the lock then names it."""
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
    """One door read of ``rig``'s :data:`FLEET` of the staged setup."""
    from mcgyvr import wake
    from mcgyvr.serving.gatelib import DOOR_MODULE

    argv = [sys.executable, "-m", DOOR_MODULE, "read", "--host", rig]
    argv += ["--fleet", FLEET, "--run-id", run_id]
    if probe:
        argv += ["--probe", *probe]
    if load:
        argv += ["--load", load]
    # The staged folder, not its fleet.yaml: the door reads both files from it.
    return wake.spawn_door(argv, env={**os.environ, CONFIG_PATH_ENV: str(setup)})


def _bundled(use_case: str) -> dict[str, Any]:
    text = (resources.files("mcgyvr") / "samples" / SAMPLES[use_case]).read_text(
        encoding="utf-8"
    )
    loaded: dict[str, Any] = yaml.safe_load(text)
    return loaded


def _repository(where: Path, files: Mapping[str, str]) -> Path:
    """A throwaway git repository holding ``files``, committed once."""
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


def run_contract(argv: list[str]) -> int:
    """``mcgyvr run`` with ``argv``, in this process: the sample task's seam."""
    from mcgyvr import cli

    return cli.main(argv)


def _contract_run(setup: Path, use_case: str, where: Path) -> dict[str, Any]:
    """Run the bundled sample contract on the staged setup; its result file."""
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
    """Why ``answer`` is not grounded, or ``None``: every sentence ends with
    ``citation``, and the reply states every fact."""
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


def safe(answer: str) -> str | None:
    """Why ``answer`` does not clear the safety check, or ``None``."""
    from mcgyvr.gate.adapter import ToolFailedError, ToolUnavailableError
    from mcgyvr.gate.output import safety_pass

    with tempfile.TemporaryDirectory(prefix="mcgyvr-sample-") as scratch:
        reply = Path(scratch) / "answer.txt"
        reply.write_text(answer, encoding="utf-8")
        try:
            findings = safety_pass(reply, "answer")
        except ToolUnavailableError as exc:
            return f"the safety check could not run: {exc}"
        except ToolFailedError as exc:
            return f"the safety check gave no answer to trust: {exc}"
    return "; ".join(finding.message for finding in findings) or None


def complete(setup: Path, unit: str) -> str:
    """One completion from ``unit`` of the staged setup: its text."""
    from mcgyvr.config import load
    from mcgyvr.local_pool import source_map
    from mcgyvr.runner import Request, dispatch

    answer = dispatch(
        source_map(load(setup)),
        unit,
        Request(prompt=CHAT_PROMPT, max_output_tokens=CHAT_TOKENS),
    )
    return str(answer.text)


def served(unit: Mapping[str, Any]) -> dict[str, int]:
    """The window per slot and the slots ``unit`` says it serves; what it states.

    llama.cpp's ``/props`` states both; vLLM's ``/v1/models`` the window only.
    A figure the unit does not state is left out, and the judge says so.
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
    """The Jev unit's one typed choice: its label and that label's probability."""
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
    """``call``'s outcome, or a failed one naming what it raised."""
    try:
        return call()
    except Exception as exc:
        return Outcome(
            check=check, unit=unit, passed=False, why=f"{type(exc).__name__}: {exc}"
        )


def task(setup: Path, awake: Sequence[str], where: Path) -> list[Outcome]:
    """The use case's sample task on the staged setup, and the Jev choice."""
    fleet, policy = _read(setup)
    use_case = str(policy.get("use_case") or DEFAULT_USE_CASE)
    jev_block = policy.get("jev")
    jev = jev_block.get("unit") if isinstance(jev_block, Mapping) else None
    units = fleet.get("units") or {}
    outcomes: list[Outcome] = []

    if use_case == CODING_USE_CASE:

        def gate() -> Outcome:
            done = _contract_run(setup, use_case, where / use_case)
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
        done: dict[str, Any] = {}
        try:
            done = _contract_run(setup, use_case, where / use_case)
        except Exception as exc:
            done = {"outcome": "error", "detail": f"{type(exc).__name__}: {exc}"}
        answer = str(done.get("answer") or "")
        rung = done.get("rung")
        if done.get("outcome") != "accepted":
            why = f"{done.get('outcome')}: {done.get('detail', '')}"
            outcomes += [
                Outcome(check=TASK_GROUNDED, unit=rung, why=why),
                Outcome(check=TASK_SAFETY, unit=rung, why=why),
            ]
        else:
            not_grounded = grounded(
                answer, str(sample.get("citation") or "[1]"), sample.get("facts") or ()
            )
            unsafe = safe(answer)
            outcomes += [
                Outcome(
                    check=TASK_GROUNDED,
                    unit=rung,
                    passed=not_grounded is None,
                    why=not_grounded or "",
                ),
                Outcome(
                    check=TASK_SAFETY,
                    unit=rung,
                    passed=unsafe is None,
                    why=unsafe or "",
                ),
            ]
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


def run(setup: Path, *, mint: Callable[[], str] | None = None) -> Ran:
    """Sample the laid-out staged setup at ``setup``: the door's reads of every
    rig and awake unit, and the use case's task between them.

    ``mint`` names each read (``run-YYYYMMDDTHHMMSS-xxxxxxxx``); the door's
    own minting by default. A read the door refused is kept out of the sample
    and named in :attr:`Ran.failed`; the judge then says what was not read.
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

    awake: list[str] = []
    for rig, slots in layout.items():
        read(rig)
        for slot in slots or ():
            if slot is None or slot[1] != AWAKE:
                continue
            unit = units[slot[0]]
            awake.append(str(slot[0]))
            width, window = unit.get("width"), unit.get("window")
            load = f"{width}x{window}" if width and window else None
            read(rig, (str(slot[0]),), load)
    _reply_ceilings(setup, reads)
    outcomes = task(setup, awake, setup / "sample")
    for rig in layout:
        read(rig)
    return Ran(
        sample=Sample(setup=setup, fleet=FLEET, reads=tuple(reads), outcomes=outcomes),
        failed=tuple(failed),
    )
