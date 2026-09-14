"""A live unit is judged by a solo probe that repeats its lock's own measurement.

Owner, 2026-09-15 (F2): every dispatch row keeps its decode, prefill and
in-flight figures as data, and only a probe judges. A solo srv2_3b dispatch of
1206 tokens in and 503 out decoded 114.1 tok/s against a locked 126.7. The
lock measured a short prompt and 256 tokens out, so a dispatch is not the
lock's quantity, and the probe asks the lock's own question instead:

* a vLLM unit gets :data:`VLLM_HARNESS`: one 64-token warm-up, five 256-token
  decodes with ``ignore_eos`` (``completion_tokens`` over wall seconds) and
  three 16-token requests of the long prompt (``prompt_tokens`` over wall
  seconds, which that harness calls its TTFT);
* a llama.cpp unit gets :data:`LLAMA_HARNESS`: ``/completion`` with a 64-token
  warm-up, five 256-token decodes read from ``timings.predicted_per_second``
  and three 16-token long prompts read from ``timings.prompt_per_second``,
  with ``cache_prompt`` off.

Both take the median, as the lock's numbers were taken
(``fleet-setup/REPORT-srv1.md``, ``fleet-setup/REPORT-srv2.md``). Unlike the
harnesses, the probe does not run on the rig: it asks the unit at its address,
so a vLLM wall time carries a network round trip the on-rig measurement did
not.

**Only an idle unit is probed.** The unit's own in-flight count
(:func:`mcgyvr.runner.unit_in_flight`) is read before and after. A unit busy
before is not probed. A unit busy after — or whose count cannot be read after —
took work during the probe: its figures are filed as ``contended`` and not
judged.

**Card memory and restarts are not read here.** Both are rig reads, and a rig
is reached only behind the door (``python -m mcgyvr.serving.run``,
``tests/test_one_door.py``). The judge holds their rules — card at most the
unit's ``room_mib``, restarts exactly 0 (:mod:`mcgyvr.fleet.alerts`) — and the
report names both as not read until a door step reads them.

Every judged figure is stamped with the live fleet, rig, rig id, combination id
and unit id, and filed through :func:`mcgyvr.fleet.alerts.check` under
``<journal.dir>/fleet/``, against the unit's plain locked value and its class
tolerance (:func:`mcgyvr.derived.class_tolerances`).
"""

from __future__ import annotations

import json
import secrets
import statistics
import time
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from mcgyvr.config import JOURNAL_DIR_DEFAULT
from mcgyvr.derived import DerivedNumbersError, class_tolerances
from mcgyvr.fleet import alerts
from mcgyvr.fleet.admit import layout_ids
from mcgyvr.fleet.files import FleetFileError, load_fleet, load_policy
from mcgyvr.fleet.roots import (
    LIVE_FILE_SHOWN,
    LiveFleetError,
    live_fleet,
    live_fleet_dir,
)
from mcgyvr.fleet.tolerance import CLASS_VLLM, tolerance_class

#: Where the probe files, under the config's ``journal.dir``.
JOURNAL_SUBDIR = "fleet"

#: The two harnesses the lock's numbers were measured with.
VLLM_HARNESS = "records/measurements/fleet-setup-2026-09-13/srv2/measure_vllm.py"
LLAMA_HARNESS = "records/measurements/fleet-setup-2026-09-13/srv1/harness_llama.py"

_SHORT_TEXT = "Write a Python function that reverses a singly linked list in place.\n"
_LONG_BLOCK = (
    "You are a precise software engineer. Explain step by step how to compute "
    "the size in bytes of every expert weight in a GGUF file, then write a "
    "Python function that opens the file, walks the metadata, and prints a "
    "table of tensor name, shape, and byte size for every tensor that has an "
    "expert dimension. Be complete and correct.\n\n"
)
#: ``measure_vllm.py``'s ``SHORT`` and ``LONG``, as written there.
VLLM_SHORT: list[dict[str, str]] = [{"role": "user", "content": _SHORT_TEXT}]
VLLM_LONG = _LONG_BLOCK * 28
#: ``harness_llama.py``'s ``SHORT_PROMPT`` and ``LONG_PROMPT``, as written there.
LLAMA_SHORT_PROMPT = _SHORT_TEXT
LLAMA_LONG_PROMPT = (_LONG_BLOCK * 28).strip()

WARMUP_TOKENS = 64
DECODE_TOKENS = 256
PREFILL_TOKENS = 16
DECODE_SAMPLES = 5
PREFILL_SAMPLES = 3
#: The harnesses' own request timeouts: 10 s for the model list, 900 s a sample.
MODELS_TIMEOUT_S = 10.0
REQUEST_TIMEOUT_S = 900.0

#: The figures a probe cannot read from a unit's HTTP face.
NOT_READ_ON_THE_RIG: tuple[str, ...] = ("card_mib", "restarts")
NOT_READ_REASON = (
    "read on the rig, and a rig is reached only behind the door "
    "(python -m mcgyvr.serving.run; tests/test_one_door.py)"
)

InFlight = Callable[[str, Mapping[str, Any]], int | None]


class ProbeError(Exception):
    """The probe cannot run at all: no fleet is live, or its folder is unreadable."""


class _UnitError(Exception):
    """One unit's probe could not run."""


class Transport(Protocol):
    """JSON over HTTP to a unit's address."""

    def get(self, url: str, timeout: float) -> Any:
        """The JSON document at ``url``."""

    def post(self, url: str, payload: dict[str, Any], timeout: float) -> Any:
        """The JSON answer to ``payload`` posted at ``url``."""


class HttpTransport:
    """The harnesses' own requests, sent to a unit's address with ``urllib``."""

    def get(self, url: str, timeout: float) -> Any:
        """The JSON document at ``url``."""
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def post(self, url: str, payload: dict[str, Any], timeout: float) -> Any:
        """The JSON answer to ``payload`` posted at ``url``."""
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))


@dataclass
class Report:
    """What one probe did, unit by unit."""

    #: unit name -> the medians measured, by lock field.
    probed: dict[str, dict[str, float]] = field(default_factory=dict)
    #: unit name -> what it had in flight, for a unit not probed because busy.
    busy: dict[str, int] = field(default_factory=dict)
    #: units that took work during their probe: filed, not judged.
    contended: list[str] = field(default_factory=list)
    #: unit name -> why its probe could not run.
    failed: dict[str, str] = field(default_factory=dict)
    #: unit name -> (the figures not read, why).
    not_read: dict[str, tuple[tuple[str, ...], str]] = field(default_factory=dict)
    #: the alerts the judge raised.
    alerts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        """1 when any unit's probe could not run, else 0."""
        return 1 if self.failed else 0


def journal_dir(folder: Path | None) -> Path:
    """``<journal.dir>/fleet`` for a live fleet folder, where the probe files.

    ``journal.dir`` is read from the folder's ``policy.yaml``; with no folder, or
    none stated, it is the config's default.
    """
    configured: Any = None
    policy_path = None if folder is None else folder / "policy.yaml"
    if policy_path is not None and policy_path.is_file():
        try:
            policy = load_policy(policy_path.read_text(encoding="utf-8"))
        except (OSError, FleetFileError) as exc:
            raise ProbeError(f"{policy_path} cannot be read: {exc}") from exc
        block = policy.get("journal")
        if isinstance(block, Mapping):
            configured = block.get("dir")
    base = str(configured) if configured else JOURNAL_DIR_DEFAULT
    return Path(base).expanduser() / JOURNAL_SUBDIR


def unit_in_flight(name: str, unit: Mapping[str, Any]) -> int | None:
    """The unit's own in-flight count, from ``/slots`` or vLLM's ``/metrics``."""
    from mcgyvr.runner import unit_in_flight as read

    width = unit.get("width")
    engine = unit.get("engine")
    return read(
        name,
        str(unit["address"]),
        engine if isinstance(engine, str) else None,
        width if isinstance(width, int) and width > 0 else 1,
    )


def _median(samples: list[float], what: str) -> float:
    if not samples:
        raise _UnitError(f"no {what} sample could be read")
    return float(statistics.median(samples))


def _count(body: Any, key: str) -> int | None:
    usage = body.get("usage") if isinstance(body, Mapping) else None
    value = usage.get(key) if isinstance(usage, Mapping) else None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _timing(body: Any, key: str) -> float | None:
    timings = body.get("timings") if isinstance(body, Mapping) else None
    value = timings.get(key) if isinstance(timings, Mapping) else None
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        return None
    return float(value)


def measure_vllm(
    address: str, transport: Transport, clock: Callable[[], float]
) -> dict[str, float]:
    """``measure_vllm.py``'s decode and prefill, asked of the unit at ``address``."""
    base = address.rstrip("/")
    listing = transport.get(f"{base}/v1/models", MODELS_TIMEOUT_S)
    try:
        model = listing["data"][0]["id"]
    except (KeyError, IndexError, TypeError) as exc:
        raise _UnitError(f"{base}/v1/models names no model") from exc
    url = f"{base}/v1/chat/completions"
    warmup = {"max_tokens": WARMUP_TOKENS, "temperature": 0, "ignore_eos": False}
    transport.post(
        url, {"model": model, "messages": VLLM_SHORT, **warmup}, REQUEST_TIMEOUT_S
    )

    decode: list[float] = []
    for _ in range(DECODE_SAMPLES):
        payload = {
            "model": model,
            "messages": VLLM_SHORT,
            "max_tokens": DECODE_TOKENS,
            "temperature": 0,
            "ignore_eos": True,
        }
        started = clock()
        body = transport.post(url, payload, REQUEST_TIMEOUT_S)
        seconds = clock() - started
        tokens = _count(body, "completion_tokens")
        if tokens is not None and seconds > 0:
            decode.append(tokens / seconds)

    prefill: list[float] = []
    for _ in range(PREFILL_SAMPLES):
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": VLLM_LONG}],
            "max_tokens": PREFILL_TOKENS,
            "temperature": 0,
            "ignore_eos": False,
        }
        started = clock()
        body = transport.post(url, payload, REQUEST_TIMEOUT_S)
        seconds = clock() - started
        tokens = _count(body, "prompt_tokens")
        if tokens is not None and seconds > 0:
            prefill.append(tokens / seconds)

    return {
        "warm_decode_tok_s": _median(decode, "decode"),
        "prefill_tok_s": _median(prefill, "prefill"),
    }


def measure_llamacpp(address: str, transport: Transport) -> dict[str, float]:
    """``harness_llama.py``'s decode and prefill, asked of the unit at ``address``."""
    url = f"{address.rstrip('/')}/completion"
    transport.post(
        url,
        {"prompt": LLAMA_SHORT_PROMPT, "n_predict": WARMUP_TOKENS, "temperature": 0},
        REQUEST_TIMEOUT_S,
    )
    decode: list[float] = []
    for _ in range(DECODE_SAMPLES):
        body = transport.post(
            url,
            {
                "prompt": LLAMA_SHORT_PROMPT,
                "n_predict": DECODE_TOKENS,
                "temperature": 0,
                "cache_prompt": False,
            },
            REQUEST_TIMEOUT_S,
        )
        rate = _timing(body, "predicted_per_second")
        if rate is not None:
            decode.append(rate)
    prefill: list[float] = []
    for _ in range(PREFILL_SAMPLES):
        body = transport.post(
            url,
            {
                "prompt": LLAMA_LONG_PROMPT,
                "n_predict": PREFILL_TOKENS,
                "temperature": 0,
                "cache_prompt": False,
            },
            REQUEST_TIMEOUT_S,
        )
        rate = _timing(body, "prompt_per_second")
        if rate is not None:
            prefill.append(rate)
    return {
        "warm_decode_tok_s": _median(decode, "decode"),
        "prefill_tok_s": _median(prefill, "prefill"),
    }


def _approved(
    folder: Path,
    rig_id: str,
    combination: str,
    unit_name: str,
    unit: Mapping[str, Any],
    tolerances: Mapping[str, float],
) -> dict[str, dict[str, Any]]:
    """The judge's view of one unit: its locked values, class percent and room."""
    path = folder / "records" / "fleet" / "rigs" / rig_id / f"{combination}.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        entry = record["approved"][unit_name]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise _UnitError(f"its lock record {path} cannot be read: {exc}") from exc
    values: dict[str, Any] = {
        name: entry[name]
        for name in ("warm_decode_tok_s", "prefill_tok_s")
        if name in entry
    }
    values["tolerance_pct"] = tolerances[tolerance_class(unit)]
    if unit.get("room_mib") is not None:
        values["room_mib"] = unit["room_mib"]
    return {str(unit["unit_id"]): values}


def _live(units: Sequence[str] | None) -> tuple[str, Path, dict[str, Any]]:
    try:
        name = live_fleet()
        folder = live_fleet_dir()
    except LiveFleetError as exc:
        raise ProbeError(str(exc)) from exc
    if name is None or folder is None:
        raise ProbeError(
            f"no fleet is live: {LIVE_FILE_SHOWN} names none (`mcgyvr fleet use`)"
        )
    try:
        fleet = load_fleet((folder / "fleet.yaml").read_text(encoding="utf-8"))
    except (OSError, FleetFileError) as exc:
        raise ProbeError(f"{folder / 'fleet.yaml'} cannot be read: {exc}") from exc
    if name not in fleet.get("fleets", {}):
        raise ProbeError(f"{folder / 'fleet.yaml'} holds no fleet {name!r}")
    return name, folder, fleet


def run(
    *,
    transport: Transport | None = None,
    in_flight: InFlight | None = None,
    clock: Callable[[], float] = time.perf_counter,
    units: Sequence[str] | None = None,
    now: datetime | None = None,
) -> Report:
    """Probe the live fleet's awake units, file every figure, judge the solo ones.

    Raises :class:`ProbeError` when nothing can be probed at all (no live
    fleet, an unreadable folder, a unit named that is not awake in it); a unit
    whose own probe cannot run is in :attr:`Report.failed`.
    """
    name, folder, fleet = _live(units)
    transport = transport if transport is not None else HttpTransport()
    in_flight = in_flight if in_flight is not None else unit_in_flight
    try:
        tolerances = class_tolerances()
    except DerivedNumbersError as exc:
        raise ProbeError(str(exc)) from exc

    layout = fleet["fleets"][name].get("layout", {})
    rig_ids = {rig: block["rig_id"] for rig, block in fleet.get("rigs", {}).items()}
    combinations = layout_ids(fleet, layout)
    awake = [
        (rig, slot[0])
        for rig, slots in layout.items()
        for slot in slots
        if slot is not None and slot[1] == "awake"
    ]
    if units:
        unknown = sorted(set(units) - {unit for _, unit in awake})
        if unknown:
            raise ProbeError(f"not an awake unit of {name}: {', '.join(unknown)}")
        awake = [(rig, unit) for rig, unit in awake if unit in units]

    moment = now if now is not None else datetime.now(UTC)
    token = secrets.token_hex(4)
    run_id = f"run-{moment:%Y%m%dT%H%M%S}-{token}"
    lease_id = f"probe-{token}"
    at = f"{moment:%Y-%m-%dT%H:%M:%S}"
    journal = journal_dir(folder)
    profile = str(fleet.get("profile", "live"))
    report = Report()

    for rig, unit_name in awake:
        unit = fleet["units"][unit_name]
        report.not_read[unit_name] = (NOT_READ_ON_THE_RIG, NOT_READ_REASON)
        before = in_flight(unit_name, unit)
        if before is None:
            report.failed[unit_name] = (
                "its in-flight count could not be read (/slots or /metrics)"
            )
            continue
        if before > 0:
            report.busy[unit_name] = before
            continue
        rig_id = rig_ids[rig]
        combination = combinations[rig_id]
        try:
            approved = _approved(
                folder, rig_id, combination, unit_name, unit, tolerances
            )
            if tolerance_class(unit) == CLASS_VLLM:
                figures = measure_vllm(str(unit["address"]), transport, clock)
            else:
                figures = measure_llamacpp(str(unit["address"]), transport)
        except (_UnitError, OSError, ValueError) as exc:
            report.failed[unit_name] = str(exc)
            continue
        report.probed[unit_name] = figures
        after = in_flight(unit_name, unit)
        stamp = {
            "fleet": name,
            "rig": rig,
            "rig_id": rig_id,
            "combination_id": combination,
            "unit_id": str(unit["unit_id"]),
        }
        if after is None or after > 0:
            report.contended.append(unit_name)
            for field_name, value in figures.items():
                alerts.record(
                    journal,
                    stamp,
                    {
                        "field": field_name,
                        "observed": value,
                        "run_id": run_id,
                        "lease_id": lease_id,
                        "at": at,
                        "contended": True,
                        "in_flight_after": after,
                    },
                )
            continue
        observations = [
            {"unit_id": stamp["unit_id"], "field": field_name, "observed": value}
            for field_name, value in figures.items()
        ]
        report.alerts.extend(
            alerts.check(
                observations,
                approved=approved,
                profile=profile,
                journal_dir=journal,
                stamp=stamp,
                run_id=run_id,
                lease_id=lease_id,
            )
        )
    return report
