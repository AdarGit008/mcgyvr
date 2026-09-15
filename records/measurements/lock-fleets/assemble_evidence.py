#!/usr/bin/env python3
"""lock-fleets assembler: the stop-and-ask list, the lock's evidence, a class tolerance.

    uv run --no-sync python records/measurements/lock-fleets/assemble_evidence.py \\
        check --use USE --host RIG --entry E [--run-id R] [--journal DIR]
    ... assemble --use USE [--journal DIR]
    ... tolerance --use USE --class C --unit U [--journal DIR]

* ``check`` is the stop-and-ask list for one entry of a frozen order, and it is
  defined here and nowhere else (:func:`stops`). ``drive.sh`` runs it after every
  entry and stops at the first non-zero. A logged entry that failed and has its
  one retry (``plan.py retry``, owner ruling 2026-09-15) is said to have failed,
  retried by that retry, and does not stop.
* ``assemble`` reads every entry back, refuses by name what does not prove what
  the lock needs, and writes ``fleet-setup/evidence.json`` in the shape
  ``mcgyvr.fleet.lock`` reads, for every combination and move the fleets need;
  ``<use>/runs.json`` with every run whole; and prints the fleet.yaml edits (rig
  ids, room_mib). It never writes fleet.yaml. A failed entry with its retry is
  kept in runs.json with its reasons, and the retry counts in its place.
* ``tolerance`` writes ``<use>/prefill-tolerance-<class>.json`` for one unit.

A read's rows are in the journal the door's ``read`` files under: the live fleet's
``<journal.dir>/fleet`` (``mcgyvr.fleet.probe.journal_dir``), or ``--journal``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

from mcgyvr.fleet.files import load_fleet
from mcgyvr.fleet.harness import LOAD_LIMIT_S, PREFILL_SAMPLES
from mcgyvr.fleet.ids import rig_id
from mcgyvr.fleet.read import parse

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
GATE_SCRIPTS = REPO / "src" / "mcgyvr" / "serving" / "gate-scripts"
#: A run median and the median of its own samples may differ by float noise only.
MEDIAN_EPSILON = 1e-9
#: What the door prints when it refused, before or around the step.
DOOR_REFUSED = re.compile(r"^run\.py: REFUSED.*$|^.*\b(?:ssh|docker) refused:.*$", re.M)
DATA30_REFUSED = "REFUSED at data-30-placement.py"
PREFILL_RULE = (
    "tol = max(1, ceil(max_i (L - s_i) / L x 100)), over the unit's K x "
    "PREFILL_SAMPLES prefill samples s_i, where L is the locked prefill (the median "
    "of the K run medians) and a sample above L counts as 0 (owner ruling, "
    "2026-09-15)"
)
PREFILL_NOTE = (
    "The 2026-09-12 M1 wording took the worst single-sample shortfall from the "
    "unit median over 15 samples "
    "(records/measurements/fleet-identity-prefill-2026-09-12/README.md:36-37); "
    "this rule takes it from the locked value over K x PREFILL_SAMPLES samples."
)


class AssemblyRefusedError(Exception):
    """The runs do not prove what the lock needs, and nothing is written."""


class MissingError(Exception):
    """An entry's log row, artifact or rows are not there."""


def _by_path(name: str, path: Path) -> ModuleType:
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


plan = _by_path("lockfleets_plan", HERE / "plan.py")
lf = plan.lockfleets()


def reserve_tolerance_mib() -> int:
    """Gate 2's own tolerance on ``gpu_reserve_mib`` (02-rig.py:62-66)."""
    gate2 = _by_path("_lockfleets_gate02", GATE_SCRIPTS / "02-rig.py")
    return int(gate2.RESERVE_TOLERANCE_MIB)


@dataclass
class Context:
    root: Path
    use: Any
    runs: Any
    fleet: dict[str, Any]
    hosts: dict[str, Any]
    journal_arg: str | None = None
    _journal: Path | None = None
    _rows: dict[str, list[dict[str, Any]]] | None = None

    @classmethod
    def load(cls, root: Path, use: str, journal: str | None = None) -> Context:
        try:
            runs = plan.read_runs(root, use)
            fleet = load_fleet((root / "fleet-setup" / "fleet.yaml").read_text("utf-8"))
            hosts = json.loads((root / "tools" / "runs" / "hosts.json").read_text("utf-8"))
            return cls(root, plan.load_use(root, use), runs, fleet, hosts, journal)
        except (plan.PlanRefusedError, OSError, ValueError) as exc:
            raise AssemblyRefusedError(str(exc)) from exc

    def journal(self) -> Path:
        if self._journal is None:
            if self.journal_arg:
                self._journal = Path(self.journal_arg)
            else:
                from mcgyvr.fleet.probe import ProbeError, journal_dir
                from mcgyvr.fleet.read import ReadError, live

                try:
                    self._journal = journal_dir(live().folder)
                except (ReadError, ProbeError) as exc:
                    raise MissingError(
                        f"the live fleet's journal cannot be found ({exc}); name it "
                        "with --journal"
                    ) from exc
        return self._journal

    def rows(self, run_id: str) -> list[dict[str, Any]]:
        """Every journal row one read filed."""
        if self._rows is None:
            self._rows = {}
            journal = self.journal()
            for path in sorted(journal.rglob("*.jsonl")) if journal.is_dir() else []:
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(row, dict) and isinstance(row.get("run_id"), str):
                        self._rows.setdefault(row["run_id"], []).append(row)
        return self._rows.get(run_id, [])

    def unit(self, name: str) -> dict[str, Any]:
        return dict((self.fleet.get("units") or {})[name])


def _digits(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value if value is not None else "").strip()
    return int(text) if text.isdigit() else None


def peak_of(samples: Sequence[Any], container: str | None) -> int | None:
    """The largest card MiB the container held in any sample, as a read reads it."""
    peaks: list[int] = []
    for sample in samples:
        if not isinstance(sample, str) or not container:
            continue
        try:
            held = [h for h in parse(sample).holders if h.container == container]
        except Exception:  # noqa: BLE001 - a sample the parser refuses shows nothing
            continue
        if held and all(h.mib is not None for h in held):
            peaks.append(sum(h.mib or 0 for h in held))
    return max(peaks) if peaks else None


def _load_from_body(body: Mapping[str, Any], container: str | None, unit: Mapping[str, Any]) -> dict[str, Any]:
    """A campaign run's load, as the harness returned it, read the way a read files it."""
    from mcgyvr.fleet.read import _pace

    samples = [s for s in body.get("samples") or [] if isinstance(s, str)]
    # Owner ruling, 2026-09-15: "Sample the card until idle". The peak is over
    # every sample; a body filed before the ruling has no close index, so all its
    # samples came before the close and its peak is a lower bound.
    index = body.get("samples_before_close")
    cut = index if isinstance(index, int) and 0 <= index <= len(samples) else len(samples)
    until_idle = body.get("sampled_until_idle") is True
    pace, source = _pace(unit, body)
    return {
        "peak_mib": peak_of(samples, container),
        "peak_before_close_mib": peak_of(samples[:cut], container),
        "samples": len(samples),
        "samples_before_close": cut,
        "sampled_until_idle": until_idle,
        "peak_is_lower_bound": not until_idle,
        "limit_s": body.get("limit_s"),
        "completed": body.get("completed"),
        "closed_unfinished": body.get("closed_unfinished"),
        "errors": [str(e) for e in body.get("errors") or []],
        "idle_error": body.get("idle_error"),
        "idle_after_close": body.get("idle_after_close"),
        "idle_after_s": body.get("idle_after_s"),
        "pace_prompt_tok_s": pace,
        "pace_source": source,
        "restarts_before": _digits(body.get("restarts_before")),
        "restarts_after": _digits(body.get("restarts_after")),
    }


def _load_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """A read's load row, as ``mcgyvr.fleet.read`` filed it."""
    return {
        "peak_mib": row.get("peak_mib"),
        "peak_before_close_mib": row.get("peak_before_close_mib"),
        "samples": row.get("samples"),
        "samples_before_close": row.get("samples_before_close"),
        "sampled_until_idle": row.get("sampled_until_idle") is True,
        "peak_is_lower_bound": row.get("sampled_until_idle") is not True,
        "limit_s": row.get("limit_s"),
        "completed": row.get("completed"),
        "closed_unfinished": row.get("closed_unfinished"),
        "errors": [str(e) for e in row.get("errors") or []],
        "idle_error": row.get("idle_error"),
        "idle_after_close": row.get("idle_after_close"),
        "idle_after_s": row.get("idle_after_s"),
        "pace_prompt_tok_s": row.get("pace_prompt_tok_s"),
        "pace_source": row.get("pace_source"),
        "restarts_before": row.get("restarts_before"),
        "restarts_after": row.get("restarts_after"),
    }


def load_refusal(load: Mapping[str, Any]) -> list[str]:
    """Why a load proves no card peak (owner, 2026-09-15). Unfinished requests,
    pace, completions and ``idle_after_close`` are filed, never refused on."""
    out: list[str] = []
    if load.get("limit_s") != LOAD_LIMIT_S:
        out.append(f"its limit_s is {load.get('limit_s')!r}, not {LOAD_LIMIT_S}")
    if load.get("errors"):
        out.append(f"errors other than the {LOAD_LIMIT_S}-s close: {load['errors'][:3]}")
    if load.get("idle_error"):
        out.append(f"a status-page error during the idle wait: {load['idle_error']}")
    if load.get("peak_mib") is None:
        out.append("no card sample shows the unit's container")
    return out


def _read_json(path: Path, what: str) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MissingError(f"{what}: {path} cannot be read ({exc})") from exc
    if not isinstance(doc, dict):
        raise MissingError(f"{what}: {path} is not a JSON object")
    return doc


def gather(ctx: Context, entry: Any) -> dict[str, Any]:
    """One entry's run, read back and put in one shape, or :class:`MissingError`."""
    row = ctx.runs.logged(entry.id)
    if row is None:
        raise MissingError(f"{entry.id} has no log row")
    run: dict[str, Any] = {
        "entry": entry.id,
        "kind": entry.kind,
        "rig": entry.rig,
        "fleet": entry.fleet,
        "to": entry.to,
        "run": entry.run,
        "units": list(entry.units),
        "run_id": row["run id"],
        "log": row,
        "snapshots": [],
        "figures": {},
        "loads": {},
        "restarts": {},
        "backend": {},
    }
    if entry.retry_of:
        run["retry_of"] = entry.retry_of
    if entry.rerun_of:
        run["rerun_of"] = entry.rerun_of
    output = ctx.root / row["output"] if row.get("output") else None
    said = output.read_text(encoding="utf-8", errors="replace") if output and output.is_file() else ""
    refused = [line.strip() for line in DOOR_REFUSED.findall(said)]
    data30 = [line for line in refused if DATA30_REFUSED in line]
    if data30:
        run["door"] = f"data-30 refused: {data30[0]}"
    elif refused:
        run["door"] = refused[0]
    try:
        _gather_kind(ctx, entry, row, run)
    except MissingError:
        if run.get("door"):
            return run
        raise
    return run


def _gather_kind(ctx: Context, entry: Any, row: Mapping[str, str], run: dict[str, Any]) -> None:
    if entry.kind in ("unit", "move"):
        path = ctx.root / row["envelope"] / entry.artifact
        doc = _read_json(path, entry.id)
        run["data"] = doc
        run["failure"] = doc.get("failure")
        snaps = doc.get("snapshots") or {}
        run["snapshots"] = [s for s in (snaps.get("start"), snaps.get("end")) if isinstance(s, dict)]
        markers = doc.get("markers") or {}
        if markers.get("start") and markers.get("end"):
            run["markers"] = [lf.key_values(markers["start"]), lf.key_values(markers["end"])]
        vm = doc.get("vmstat") or {}
        run["vmstat"] = [vm.get("start"), vm.get("end")]
        before, after = (vm.get("start") or {}).get("pswpout"), (vm.get("end") or {}).get("pswpout")
        if isinstance(before, int) and isinstance(after, int):
            run["pswpout"] = {"start": before, "end": after, "delta": after - before}
        run["sidecar"] = path.with_name(path.name + ".RIGMOVED").is_file()
        run["ended_at"] = doc.get("ended_at")
        if entry.kind == "unit":
            name = entry.units[0]
            harness = doc.get("harness")
            figures = harness.get("figures") if isinstance(harness, dict) else None
            if isinstance(figures, dict):
                run["figures"][name] = figures
            else:
                why = harness.get("error") or harness.get("raw") if isinstance(harness, dict) else harness
                run["harness_error"] = str(why)[:300]
            load = doc.get("load")
            body = load.get("load") if isinstance(load, dict) else None
            if isinstance(body, dict):
                run["loads"][name] = _load_from_body(body, doc.get("container_id"), ctx.unit(name))
            else:
                why = load.get("error") or load.get("raw") if isinstance(load, dict) else load
                run["load_error"] = str(why)[:300]
            run["restarts"][name] = _digits(doc.get("restarts"))
        else:
            source, target = lf.move_sides(ctx.fleet, entry.rig, entry.fleet, entry.to)
            groups = [s for s in (source, target) if s.compose]
            run["compose_group"] = groups[0].fleet if groups else None
            run["compose_sha256"] = doc.get("compose_sha256")
            run["target"] = [u.name for u in target.units]
            run["target_kind"] = "compose" if target.compose else "run"
            run["source"] = source
            run["target_side"] = target
        return
    if entry.kind in ("serve-up", "serve-down"):
        where = ctx.root / row["envelope"]
        run_id = row["run id"]
        header = _read_json(where / f"{run_id}.run.json", f"{entry.id} header")
        mode = entry.kind.removeprefix("serve-")
        step = where / f"serve-{mode}.json"
        doc = json.loads(step.read_text("utf-8")) if step.is_file() else {}
        if doc.get("run_id") != run_id:
            doc = _read_json(where / f"serve-{mode}.superseded-{run_id}.json", entry.id)
        run["data"] = {"header": header, "step": doc}
        run["ended_at"] = header.get("started_at")
        sidecar = where / f"serve-{mode}.json.RIGMOVED"
        run["sidecar"] = sidecar.is_file() and f"run_id={run_id}" in sidecar.read_text("utf-8")
        failures: list[str] = []
        if mode == "up":
            if doc.get("compose_up_exit") != 0:
                failures.append(f"docker compose up exited {doc.get('compose_up_exit')}")
            unhealthy = [str(u.get("container")) for u in doc.get("units") or [] if not u.get("healthy")]
            if unhealthy:
                failures.append(f"not serving after serve up: {', '.join(unhealthy)}")
            compose = doc.get("compose")
            run["compose_group"] = entry.fleet
            run["compose_sha256"] = (
                hashlib.sha256(compose.encode("utf-8")).hexdigest() if isinstance(compose, str) else None
            )
        else:
            if doc.get("compose_down_exit") != 0:
                failures.append(f"docker compose down exited {doc.get('compose_down_exit')}")
            if doc.get("remaining"):
                failures.append(f"still up after serve down: {doc['remaining']}")
            if doc.get("daemon_read") is False:
                failures.append("the daemon could not be read after serve down")
        run["failure"] = "; ".join(failures) or None
        return
    rows = ctx.rows(row["run id"])
    rig_rows = [r for r in rows if "observed_rig_id" in r and r.get("rig") == entry.rig]
    if not rig_rows:
        raise MissingError(f"{entry.id}: the journal holds no rig row for {row['run id']}")
    rig_row = rig_rows[-1]
    run["rig_row"] = rig_row
    run["data"] = {"rig": rig_row, "units": [r for r in rows if "observed_rig_id" not in r]}
    run["snapshots"] = [rig_row["snapshot"]] if isinstance(rig_row.get("snapshot"), dict) else []
    run["ended_at"] = rig_row.get("at")
    for name in entry.units:
        unit_id = ctx.unit(name).get("unit_id")
        mine = [r for r in rows if r.get("unit_id") == unit_id and "field" in r]
        figures = {
            r["field"]: r.get("observed")
            for r in mine
            if r["field"] in ("warm_decode_tok_s", "prefill_tok_s", "decode_samples", "prefill_samples")
        }
        if figures:
            run["figures"][name] = figures
        restarts = [r.get("observed") for r in mine if r["field"] == "restarts"]
        run["restarts"][name] = _digits(restarts[-1]) if restarts else None
        backends = [r.get("observed") for r in mine if r["field"] == "attention_backend"]
        if ctx.unit(name).get("engine") == lf.ENGINE_VLLM:
            run["backend"][name] = backends[-1] if backends else None
        loads = [r for r in mine if r["field"] == "load_peak_mib"]
        if entry.kind == "load" and loads:
            run["loads"][name] = _load_from_row(loads[-1])


def _card(runs: Sequence[Mapping[str, Any]]) -> int | None:
    cards = {_digits(s.get("gpu_vram_mib")) for r in runs for s in r["snapshots"]}
    cards.discard(None)
    return max(cards) if cards else None  # type: ignore[type-var]


def _reserves(runs: Sequence[Mapping[str, Any]]) -> list[int]:
    return [
        value
        for r in runs
        for s in r["snapshots"]
        if (value := _digits(s.get("gpu_reserve_mib"))) is not None
    ]


def stops(ctx: Context, entry: Any, run: Mapping[str, Any], prior: Sequence[Mapping[str, Any]]) -> list[str]:
    """THE stop-and-ask list for one entry (owner, 2026-09-15). ``prior`` is every
    earlier run on the entry's rig, in the frozen order."""
    out: list[str] = []
    if run.get("door"):
        out.append(f"the door refused: {run['door']}")
        return out
    if run.get("failure"):
        out.append(f"the step failed: {run['failure']}")
    if run.get("harness_error"):
        out.append(f"the harness on the rig could not measure: {run['harness_error']}")
    if run.get("load_error"):
        out.append(f"the load on the rig could not run: {run['load_error']}")
    if run.get("sidecar"):
        out.append("gate 7 filed a .RIGMOVED sidecar: the rig moved under this run")
    markers = run.get("markers")
    if markers:
        start, end = markers
        moved = [f"{k} {start.get(k)} -> {end.get(k)}" for k in lf.MARKER_FIELDS if start.get(k) != end.get(k)]
        if moved:
            out.append(f"the START and END markers differ: {', '.join(moved)}")
    # On a rig use.json lists, swap growth is filed (run["pswpout"]) and is no
    # reason to stop (owner ruling, 2026-09-15: "Record swap on srv1, don't stop").
    swap = run.get("pswpout")
    if swap and swap["delta"] > 0 and entry.rig not in ctx.use.swap_recorded_not_stopped_on:
        out.append(f"pswpout rose during the run ({swap['start']} -> {swap['end']})")
    for name, count in run["restarts"].items():
        if count is None:
            out.append(f"{name}'s restarts were not read")
        elif count > 0:
            out.append(f"{name} restarted {count} time(s)")
    rig_row = run.get("rig_row")
    if rig_row:
        for key in ("failed", "contended", "busy"):
            if rig_row.get(key):
                out.append(f"the rig row shows {key}: {rig_row[key]}")
        if entry.kind == "load" and rig_row.get("unloaded"):
            out.append(f"the load was not run: {rig_row['unloaded']}")
    for name, load in run["loads"].items():
        out += [f"{name}'s load is refused: {why}" for why in load_refusal(load)]
        for key in ("restarts_before", "restarts_after"):
            if isinstance(load.get(key), int) and load[key] > 0:
                out.append(f"{name}'s container restarted ({key} {load[key]})")
    named: dict[str, str] = {}
    for r in [*prior, run]:
        for snapshot in r["snapshots"]:
            try:
                named.setdefault(rig_id(snapshot), r["entry"])
            except ValueError as exc:
                out.append(f"{r['entry']}'s snapshot names no rig: {exc}")
    if len(named) > 1:
        out.append(f"the rig id changed between runs: {named}")
    if entry.kind == "move":
        rc = ((run.get("data") or {}).get("stamps") or {}).get("rc") or {}
        wanted = ["rc_stop", "rc_drop", "rc_compose" if run.get("target_kind") == "compose" else "rc_run"]
        for key in wanted:
            if key not in rc:
                out.append(f"the stopwatch filed no {key}")
        for key, value in rc.items():
            if value != 0:
                out.append(f"{key} is {value}")
        t2 = ((run.get("data") or {}).get("stamps") or {}).get("t2") or {}
        missing = [u for u in run.get("target") or [] if u not in t2]
        if missing:
            out.append(f"no t2 for {', '.join(missing)}")
    group = run.get("compose_group")
    if group and run.get("compose_sha256"):
        shas = {
            r["compose_sha256"]
            for r in prior
            if r.get("compose_group") == group and r.get("compose_sha256")
        }
        if shas - {run["compose_sha256"]}:
            out.append(f"the compose file of {group} on {entry.rig} differs between runs")
    if run["loads"]:
        combination = [r for r in [*prior, run] if r["fleet"] == entry.fleet and r["kind"] != "move"]
        card, reserves = _card([*prior, run]), _reserves(combination)
        if card is not None and reserves:
            reserve = max(reserves)
            cycle = [r for r in combination if r["run"] == entry.run]
            peaks = {
                name: load["peak_mib"]
                for r in cycle
                for name, load in r["loads"].items()
                if isinstance(load.get("peak_mib"), int)
            }
            for name, load in run["loads"].items():
                peak = load.get("peak_mib")
                if isinstance(peak, int) and peak + reserve > card:
                    out.append(f"{name}'s peak {peak} + reserve {reserve} > card {card}")
            if len(peaks) > 1 and sum(peaks.values()) + reserve > card:
                out.append(f"the peaks of {entry.fleet} on {entry.rig} {peaks} + reserve {reserve} > card {card}")
        for cap in ctx.runs.caps:
            load = run["loads"].get(cap["unit"])
            if cap["rig"] == entry.rig and cap["fleet"] == entry.fleet and load:
                peak = load.get("peak_mib")
                if isinstance(peak, int) and peak > int(cap["cap_mib"]):
                    out.append(f"{cap['unit']}'s peak {peak} > its cap {cap['cap_mib']} ({cap['from']})")
    for name, backend in run["backend"].items():
        pin = ctx.unit(name).get("attention_backend")
        if backend is None:
            out.append(f"{name} reported no attention_backend")
        elif backend != pin:
            out.append(f"{name} reported attention backend {backend}, not the pinned {pin}")
    # No stop on idle_after_close false (owner ruling, 2026-09-15: "Sample the card
    # until idle"): the close does not cancel the work, and the flag is data.
    return out


def verdict(ctx: Context, host: str, entry_id: str, run_id: str | None = None) -> tuple[list[str], str]:
    """The stop-and-ask reasons for one entry, and what is said when there are none.

    A logged entry that fails its check and has its one retry (``plan.py retry``,
    owner ruling 2026-09-15) gives no reason to stop: it is said to have failed,
    retried by that retry, which is the entry after it. A retry that fails stops
    like any entry; so does an entry that passes and has a retry anyway.
    """
    try:
        entry = ctx.runs.entry(entry_id)
    except plan.PlanRefusedError as exc:
        return [str(exc)], ""
    if entry.rig != host:
        return [f"{entry_id} is an entry of {entry.rig}, not {host}"], ""
    row = ctx.runs.logged(entry_id)
    if run_id and row is not None and row["run id"] != run_id:
        return [f"{entry_id}'s log row names run id {row['run id']}, not {run_id}"], ""
    prior: list[dict[str, Any]] = []
    for earlier in ctx.runs.entries:
        if earlier.id == entry_id:
            break
        if earlier.rig == host and ctx.runs.logged(earlier.id) is not None:
            try:
                prior.append(gather(ctx, earlier))
            except MissingError:
                continue
    reasons: list[str]
    try:
        run = gather(ctx, entry)
    except MissingError as exc:
        reasons = [str(exc)]
    else:
        reasons = stops(ctx, entry, run, prior)
    retry = ctx.runs.retry_for(entry_id)
    if retry is not None and row is not None:
        if not reasons:
            return [passed_with_a_retry(entry_id, retry.id)], ""
        return [], f"{entry_id} failed, retried by {retry.id}: {'; '.join(reasons)}"
    if reasons:
        return reasons, ""
    rerun = ctx.runs.rerun_for(entry_id)
    if rerun is not None:
        return [], f"ok {entry_id}; its one extra cold start for room, {rerun.id}, runs next"
    return [], f"ok {entry_id}"


def passed_with_a_retry(entry_id: str, retry_id: str) -> str:
    return (
        f"{entry_id} passes its check, and {plan.RETRIES} names {retry_id} as its "
        "retry: only a failed entry is retried (owner ruling, 2026-09-15)"
    )


def check(ctx: Context, host: str, entry_id: str, run_id: str | None = None) -> list[str]:
    """The stop-and-ask reasons for one entry; empty when it may go on."""
    return verdict(ctx, host, entry_id, run_id)[0]


def _utc(text: str) -> datetime:
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _max_alert_at(journal: Path, combinations: Sequence[str]) -> str | None:
    found: list[str] = []
    for combination in combinations:
        for path in sorted((journal / combination).glob("*.jsonl")) if (journal / combination).is_dir() else []:
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get("alert") and isinstance(row.get("at"), str):
                    found.append(row["at"])
    return max(found, key=_utc) if found else None


@dataclass
class Collected:
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    combinations: list[dict[str, Any]] = field(default_factory=list)
    samples: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    rooms: dict[str, int] = field(default_factory=dict)
    moves: list[dict[str, Any]] = field(default_factory=list)
    rigs: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: Failed entries kept as data points, each counted by its retry instead.
    failed: set[str] = field(default_factory=set)


def _median_of_samples(entry: str, name: str, figures: Mapping[str, Any], median_key: str, samples_key: str) -> tuple[float, list[float]]:
    median, samples = figures.get(median_key), figures.get(samples_key)
    if not isinstance(median, int | float) or not isinstance(samples, list) or not samples:
        raise AssemblyRefusedError(f"{entry}: {name} has no {median_key} with its {samples_key}")
    values = [float(s) for s in samples]
    if abs(float(median) - statistics.median(values)) > MEDIAN_EPSILON:
        raise AssemblyRefusedError(
            f"{entry}: {name}'s {median_key} {median} is not the median of its own samples "
            f"({statistics.median(values)})"
        )
    return float(median), values


def collect(ctx: Context) -> Collected:
    """Every entry read back and checked, then folded into what the lock needs."""
    out = Collected()
    entries = ctx.runs.entries
    for rig in sorted({e.rig for e in entries}):
        prior: list[dict[str, Any]] = []
        for entry in (e for e in entries if e.rig == rig):
            retry = ctx.runs.retry_for(entry.id)
            row = ctx.runs.logged(entry.id)
            try:
                run = gather(ctx, entry)
            except MissingError as exc:
                if retry is None or row is None:
                    raise AssemblyRefusedError(f"a frozen entry is missing: {exc}") from exc
                run = {"entry": entry.id, "kind": entry.kind, "rig": entry.rig, "fleet": entry.fleet,
                       "to": entry.to, "run": entry.run, "units": list(entry.units), "log": row}
                reasons = [str(exc)]
            else:
                reasons = stops(ctx, entry, run, prior)
            if retry is not None:
                # A data point, and not one of the K valid runs: its retry
                # counts in its place (owner ruling, 2026-09-15).
                if not reasons:
                    raise AssemblyRefusedError(passed_with_a_retry(entry.id, retry.id))
                run |= {"retried_by": retry.id, "check": reasons}
                out.failed.add(entry.id)
                out.runs[entry.id] = run
                continue
            if reasons:
                raise AssemblyRefusedError(f"{entry.id} fails its check: {'; '.join(reasons)}")
            rerun = ctx.runs.rerun_for(entry.id)
            if rerun is not None:
                run["rerun_by"] = rerun.id
            prior.append(run)
            out.runs[entry.id] = run
        card = _card(prior)
        cards = {_digits(s.get("gpu_vram_mib")) for r in prior for s in r["snapshots"]}
        if len(cards) != 1 or card is None:
            raise AssemblyRefusedError(f"{rig}'s runs read card sizes {sorted(map(str, cards))}, not one")
        snapshots = [s for r in prior for s in r["snapshots"]]
        if not snapshots:
            raise AssemblyRefusedError(f"no run on {rig} read its snapshot")
        snapshot = snapshots[-1]
        pinned = ((ctx.fleet.get("rigs") or {}).get(rig) or {}).get("rig_id")
        if rig in ctx.use.keep_rig_pins and rig_id(snapshot) != pinned:
            raise AssemblyRefusedError(
                f"{rig}'s pin must not change, and its snapshot names {rig_id(snapshot)}, not {pinned}"
            )
        out.rigs[rig] = {"card_mib": card, "snapshot": snapshot}
    declared_tolerance = reserve_tolerance_mib()
    for rig in sorted(out.rigs):
        _combinations(ctx, rig, out, declared_tolerance)
        _moves(ctx, rig, out)
    _fits(ctx, out)
    return out


def _combinations(ctx: Context, rig: str, out: Collected, tolerance: int) -> None:
    from mcgyvr.fleet.lock import _combination_id_for

    # A failed entry with its retry, and a re-run, are not cycles of their own:
    # the retry stands in for its entry, and a re-run gives only room.
    entries = [
        e for e in ctx.runs.entries
        if e.rig == rig and e.kind != "move" and e.id not in out.failed and not e.rerun_of
    ]
    for fleet_name in dict.fromkeys(e.fleet for e in entries):
        mine = [e for e in entries if e.fleet == fleet_name]
        names = list(next(e for e in mine if e.kind in ("unit", "serve-up")).units)
        vllm = any(e.kind == "serve-up" for e in mine)
        labels = list(dict.fromkeys(e.run for e in mine))
        valid: list[str] = []
        for label in labels:
            kinds = [e.kind for e in mine if e.run == label]
            complete = kinds == ["unit"] if not vllm else (
                "serve-up" in kinds and "read" in kinds and "serve-down" in kinds and kinds.count("load") == len(names)
            )
            if complete:
                valid.append(label)
        if len(valid) < plan.K:
            raise AssemblyRefusedError(
                f"{fleet_name} on {rig} has {len(valid)} valid runs, and the lock needs {plan.K}"
            )
        decode: dict[str, list[float]] = {n: [] for n in names}
        prefill: dict[str, list[float]] = {n: [] for n in names}
        room_runs: dict[str, list[tuple[str, Mapping[str, Any]]]] = {n: [] for n in names}
        backends: dict[str, set[Any]] = {n: set() for n in names}
        runs_of: list[dict[str, Any]] = []
        envelopes: set[str] = set()
        validated_at = None
        for label in valid:
            cycle = [e for e in mine if e.run == label]
            cycle_runs = [out.runs[e.id] for e in cycle]
            runs_of += cycle_runs
            figures_run = next(out.runs[e.id] for e in cycle if e.kind in ("unit", "read"))
            for name in names:
                figures = figures_run["figures"].get(name) or {}
                median, samples = _median_of_samples(figures_run["entry"], name, figures, "warm_decode_tok_s", "decode_samples")
                decode[name].append(median)
                pmedian, psamples = _median_of_samples(figures_run["entry"], name, figures, "prefill_tok_s", "prefill_samples")
                prefill[name].append(pmedian)
                out.samples.setdefault(name, []).append(
                    {"entry": figures_run["entry"], "prefill_tok_s": pmedian, "prefill_samples": psamples,
                     "warm_decode_tok_s": median, "decode_samples": samples}
                )
                load_run = next(
                    out.runs[e.id] for e in cycle if e.kind in ("unit", "load") and name in out.runs[e.id]["loads"]
                )
                # Room takes the entry's extra cold start when it has one (owner
                # ruling, 2026-09-15: "One extra cold start for room"); the
                # entry's own peak stays in runs.json as data, a lower bound.
                rerun = ctx.runs.rerun_for(load_run["entry"])
                room_run = out.runs[rerun.id] if rerun is not None else load_run
                room_runs[name].append((room_run["entry"], room_run["loads"].get(name) or {}))
                for r in cycle_runs:
                    if name in r["backend"]:
                        backends[name].add(r["backend"][name])
            last = next(e for e in reversed(cycle) if e.kind in ("unit", "serve-down"))
            validated_at = out.runs[last.id]["ended_at"]
            envelopes |= {ctx.runs.logged(e.id)["envelope"] for e in cycle if e.kind in ("unit", "serve-up", "serve-down")}
        # Room and the card peak are the max of peaks sampled until idle (owner
        # ruling, 2026-09-15: "Sample the card until idle"). A peak not sampled
        # until idle is a lower bound and never counts toward room.
        peaks: dict[str, list[int]] = {}
        for name in names:
            until = [load for _, load in room_runs[name] if load.get("sampled_until_idle") is True]
            short = [entry for entry, load in room_runs[name] if load.get("sampled_until_idle") is not True]
            if len(until) < plan.K:
                raise AssemblyRefusedError(
                    f"{name} on {rig}: room takes {plan.K} valid runs sampled until idle, and "
                    f"{len(until)} were; not sampled until idle, each peak a lower bound: "
                    f"{', '.join(short)}"
                )
            peaks[name] = [int(load["peak_mib"]) for load in until]
        reserves = _reserves(runs_of)
        overhead = max(reserves)
        declared = int(ctx.hosts[rig]["rig"]["gpu_reserve_mib"])
        if abs(overhead - declared) > tolerance:
            raise AssemblyRefusedError(
                f"{fleet_name} on {rig}: the reserve read {overhead} MiB, more than {tolerance} MiB "
                f"from tools/runs/hosts.json's {declared}"
            )
        restarts = {n: max(max(r["restarts"].get(n) or 0 for r in runs_of), 0) for n in names}
        if any(restarts.values()):
            raise AssemblyRefusedError(f"{fleet_name} on {rig} restarted: {restarts}")
        slots = [[n, "awake"] for n in names]
        snapshot = out.rigs[rig]["snapshot"]
        rig_ids = {r: b["rig_id"] for r, b in (ctx.fleet.get("rigs") or {}).items()}
        unit_ids = {n: ctx.unit(n)["unit_id"] for n in names}
        combinations = [
            _combination_id_for(rig_ids, unit_ids, rig, slots),
            _combination_id_for({**rig_ids, rig: rig_id(snapshot)}, unit_ids, rig, slots),
        ]
        try:
            alert_at = _max_alert_at(ctx.journal(), combinations)
        except MissingError as exc:
            raise AssemblyRefusedError(f"validated_at cannot be held to the journal: {exc}") from exc
        if not isinstance(validated_at, str) or (alert_at is not None and _utc(validated_at) <= _utc(alert_at)):
            raise AssemblyRefusedError(
                f"{fleet_name} on {rig}: validated_at {validated_at} is not after the journal's "
                f"last alert at {alert_at}"
            )
        record: dict[str, Any] = {
            "rig": rig,
            "slots": slots,
            "passed": True,
            "overhead_mib": overhead,
            "restarts": restarts,
            "warm_decode_tok_s": {n: statistics.median(decode[n]) for n in names},
            "prefill_tok_s": {n: statistics.median(prefill[n]) for n in names},
            "baseline_tok_s": {},
            "validated_at": validated_at,
            "envelope": sorted(envelopes)[0] if len(envelopes) == 1 else sorted(envelopes),
        }
        if vllm:
            record["attention_backend"] = {}
            for n in names:
                if len(backends[n]) != 1:
                    raise AssemblyRefusedError(f"{n}'s attention backend is not unanimous: {sorted(map(str, backends[n]))}")
                record["attention_backend"][n] = next(iter(backends[n]))
        else:
            record["card_peak_mib"] = {n: max(peaks[n]) for n in names}
        for n in names:
            out.rooms[n] = max(peaks[n])
        out.combinations.append(record)


def _moves(ctx: Context, rig: str, out: Collected) -> None:
    entries = [e for e in ctx.runs.entries if e.rig == rig and e.kind == "move" and e.id not in out.failed]
    for key in dict.fromkeys((e.fleet, e.to) for e in entries):
        mine = [e for e in entries if (e.fleet, e.to) == key]
        if len(mine) < plan.K:
            raise AssemblyRefusedError(f"the move {key[0]} -> {key[1]} on {rig} has {len(mine)} valid runs, and the lock needs {plan.K}")
        downtime: list[float] = []
        wake: dict[str, list[float]] = {}
        source = target = None
        for entry in mine:
            run = out.runs[entry.id]
            source, target = run["source"], run["target_side"]
            stamps = run["data"]["stamps"]
            t0, t1, t2 = stamps.get("t0"), stamps.get("t1"), stamps.get("t2") or {}
            if t0 is None or t1 is None:
                raise AssemblyRefusedError(f"{entry.id}: the stopwatch filed no t0 or t1")
            if t1 < t0:
                raise AssemblyRefusedError(f"{entry.id}: t1 {t1} is before t0 {t0}")
            for name in run["target"]:
                if t2[name] < t1:
                    raise AssemblyRefusedError(f"{entry.id}: {name}'s t2 {t2[name]} is before t1 {t1}")
            if target.compose and stamps.get("t_compose") is None:
                raise AssemblyRefusedError(f"{entry.id}: a compose target filed no t_compose")
            seconds, wakes = lf.move_times(stamps, run["target"])
            downtime.append(seconds)
            for name, value in wakes.items():
                wake.setdefault(name, []).append(value)
        assert source is not None and target is not None
        out.moves.append(
            {
                "rig": rig,
                "from": source.slots,
                "to": target.slots,
                "passed": True,
                "downtime_s": max(downtime),
                "wake_s": {name: max(values) for name, values in wake.items()},
            }
        )


def _fits(ctx: Context, out: Collected) -> None:
    """lock.py:138 for every layout with the measured rooms, and lock.py:240-245."""
    by_slots = {(c["rig"], json.dumps(c["slots"])): c for c in out.combinations}
    for fleet_name, block in (ctx.fleet.get("fleets") or {}).items():
        for rig, slots in (block.get("layout") or {}).items():
            comb = by_slots.get((rig, json.dumps([list(s) for s in slots])))
            if comb is None:
                raise AssemblyRefusedError(f"{fleet_name}: the combination on {rig} has no run")
            room = sum(out.rooms[name] for name, _ in slots)
            card = out.rigs[rig]["card_mib"]
            if room + comb["overhead_mib"] > card:
                raise AssemblyRefusedError(
                    f"{fleet_name}: {rig} units' room {room} MiB plus overhead {comb['overhead_mib']} MiB "
                    f"exceeds the card {card} MiB"
                )
    for comb in out.combinations:
        for name, warm in comb["warm_decode_tok_s"].items():
            unit = ctx.unit(name)
            if float(unit["output_tokens"]) / float(warm) > float(unit["request_timeout_s"]):
                raise AssemblyRefusedError(
                    f"{name}: a reply of {unit['output_tokens']} tokens at {warm} tok/s cannot "
                    f"finish inside request_timeout_s {unit['request_timeout_s']}"
                )


def edits(ctx: Context, out: Collected) -> list[str]:
    """The fleet.yaml edits the evidence asks for. Printed; fleet.yaml is not written."""
    lines = ["fleet.yaml edits (assemble_evidence.py writes no fleet.yaml):"]
    for rig, block in sorted(out.rigs.items()):
        pinned = ((ctx.fleet.get("rigs") or {}).get(rig) or {}).get("rig_id")
        named = rig_id(block["snapshot"])
        lines.append(f"  rigs.{rig}.rig_id: {pinned} -> {named}" if pinned != named else f"  rigs.{rig}.rig_id: {named} (unchanged)")
    for name, room in sorted(out.rooms.items()):
        was = ctx.unit(name).get("room_mib")
        lines.append(f"  units.{name}.room_mib: {was} -> {room}" if was != room else f"  units.{name}.room_mib: {room} (unchanged)")
    return lines


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def assemble(ctx: Context) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    out = collect(ctx)
    evidence = {"rigs": out.rigs, "combinations": out.combinations, "moves": out.moves}
    runs = {
        "use": ctx.use.name,
        "k": plan.K,
        "runs": {
            entry_id: _jsonable({k: v for k, v in run.items() if k not in ("source", "target_side")})
            for entry_id, run in out.runs.items()
        },
    }
    return evidence, runs, edits(ctx, out)


def tolerance(ctx: Context, klass: str, unit: str) -> dict[str, Any]:
    from mcgyvr.fleet.tolerance import tolerance_class

    if unit not in (ctx.fleet.get("units") or {}):
        raise AssemblyRefusedError(f"{unit} is not a unit of fleet.yaml")
    if tolerance_class(ctx.unit(unit)) != klass:
        raise AssemblyRefusedError(f"{unit} is in class {tolerance_class(ctx.unit(unit))}, not {klass}")
    out = collect(ctx)
    runs = out.samples.get(unit) or []
    samples = [s for r in runs for s in r["prefill_samples"]]
    if len(runs) != plan.K or len(samples) != plan.K * PREFILL_SAMPLES:
        raise AssemblyRefusedError(
            f"{unit} has {len(samples)} prefill samples from {len(runs)} valid runs, and the rule "
            f"takes exactly {plan.K * PREFILL_SAMPLES} from {plan.K}"
        )
    locked = statistics.median([r["prefill_tok_s"] for r in runs])
    evidence_path = ctx.root / "fleet-setup" / "evidence.json"
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AssemblyRefusedError(f"{evidence_path} cannot be read: {exc}") from exc
    values = [
        c["prefill_tok_s"][unit]
        for c in evidence.get("combinations") or []
        if unit in (c.get("prefill_tok_s") or {})
    ]
    if len(values) != 1 or abs(float(values[0]) - locked) > MEDIAN_EPSILON:
        raise AssemblyRefusedError(
            f"L {locked} for {unit} is not evidence.json's prefill_tok_s ({values})"
        )
    shortfalls = [max(0.0, (locked - s) / locked * 100.0) for s in samples]
    worst = max(shortfalls)
    return {
        "use": ctx.use.name,
        "class": klass,
        "unit": unit,
        "locked_prefill_tok_s": locked,
        "run_medians": [r["prefill_tok_s"] for r in runs],
        "entries": [r["entry"] for r in runs],
        "samples": samples,
        "shortfall_pct": shortfalls,
        "worst_shortfall_pct": worst,
        "tolerance_pct": max(1, math.ceil(round(worst, 9))),
        "rule": PREFILL_RULE,
        "note": PREFILL_NOTE,
        "evidence": "fleet-setup/evidence.json",
    }


def _dump(path: Path, doc: Any) -> None:
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="assemble_evidence.py", description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=str(REPO))
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("check")
    one.add_argument("--use", required=True)
    one.add_argument("--host", required=True)
    one.add_argument("--entry", required=True)
    one.add_argument("--run-id", default="")
    one.add_argument("--journal", default="")
    one = sub.add_parser("assemble")
    one.add_argument("--use", required=True)
    one.add_argument("--journal", default="")
    one = sub.add_parser("tolerance")
    one.add_argument("--use", required=True)
    one.add_argument("--class", dest="klass", required=True)
    one.add_argument("--unit", required=True)
    one.add_argument("--journal", default="")
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        ctx = Context.load(root, args.use, args.journal or None)
        if args.command == "check":
            reasons, said = verdict(ctx, args.host, args.entry, args.run_id or None)
            for reason in reasons:
                print(reason)
            if reasons:
                return 1
            print(said)
        elif args.command == "assemble":
            evidence, runs, lines = assemble(ctx)
            _dump(root / "fleet-setup" / "evidence.json", evidence)
            _dump(plan.use_dir(root, args.use) / "runs.json", runs)
            print("\n".join(lines))
        else:
            doc = tolerance(ctx, args.klass, args.unit)
            path = plan.use_dir(root, args.use) / f"prefill-tolerance-{args.klass}.json"
            if path.is_file() and json.loads(path.read_text("utf-8")).get("unit") != args.unit:
                raise AssemblyRefusedError(f"{path} already holds another unit's tolerance")
            _dump(path, doc)
            print(f"{args.klass} prefill tolerance {doc['tolerance_pct']}% from {args.unit}: {path}")
    except AssemblyRefusedError as exc:
        print(f"assemble_evidence.py: REFUSED — {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
