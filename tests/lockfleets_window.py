"""A throw-away tree where a lock-fleets use is frozen and its window written out.

Nothing reaches a rig. The fleet is made up: rig ``alpha`` with two llama.cpp
units taking turns, and rig ``beta`` with one llama.cpp unit taking turns with a
vLLM pair. :class:`Window` writes every file a window would leave, in the shapes
the campaign's step bodies (``lockfleets.write_unit``/``write_move``), the door's
serve steps (``serve-up.py``/``serve-down.py`` and gate 5's header) and its
``read`` (:mod:`mcgyvr.fleet.read`) write them. A test changes one entry's
payload before it is written and asks the assembler what it makes of it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from mcgyvr.fleet.files import load_fleet
from mcgyvr.fleet.ids import rig_id
from tests._helpers import by_path

REPO = Path(__file__).resolve().parent.parent
LOCK_FLEETS = REPO / "records" / "measurements" / "lock-fleets"
USE = "fixture-use"
WINDOW_DATE = "2026-09-16"
STALE_PIN = "rig-" + "0" * 64
COMPOSE_TEXT = "services:\n  b_small: {}\n  b_mid: {}\n"
PEAK = {"a_solo": 4000, "a_pair": 4200, "b_big": 10500, "b_small": 3400, "b_mid": 7800}
LLAMA_DECODE = [30.0, 31.0, 32.0, 33.0, 34.0]
LLAMA_PREFILL = {
    "c1": [300.0, 310.0, 320.0],
    "c2": [305.0, 312.0, 330.0],
    "c3": [290.0, 309.0, 311.0],
}
VLLM_DECODE = [118.0, 119.0, 120.0, 121.0, 122.0]
VLLM_PREFILL = [10900.0, 11000.0, 11100.0]
TOLERANCES = {
    "warm_decode_class_pct": {"vllm": 1.0, "llamacpp": 1.0, "cpu_experts": 48.0}
}
HOST_KEYS = (
    "cpu_max_mhz",
    "cpu_model",
    "ram_mt_s",
    "pl1_uw",
    "pl2_uw",
    "gpu_name",
    "gpu_vram_mib",
    "gpu_cc",
    "driver",
    "gpu_reserve_mib",
    "docker",
)
LLAMA_IMAGE_ID = "sha256:" + "a" * 64
VLLM_IMAGE = "vllm/vllm-openai@sha256:" + "f" * 64

Change = Callable[[dict[str, Any]], None]


def plan_module() -> ModuleType:
    return by_path("lockfleets_plan", LOCK_FLEETS / "plan.py")


def assemble_module() -> ModuleType:
    return by_path("lockfleets_assemble", LOCK_FLEETS / "assemble_evidence.py")


def steps_module() -> ModuleType:
    module: ModuleType = plan_module().lockfleets()
    return module


def snapshot(rig: str, **override: str) -> dict[str, str]:
    """One ``rig-snapshot.sh`` reading of a made-up rig."""
    cards = {"alpha": ("6144", "399", "7.5"), "beta": ("12288", "377", "8.6")}
    vram, reserve, cc = cards[rig]
    values = {
        "uptime_since": "2026-09-16T08:00:00Z",
        "cpu_max_mhz": "4600",
        "cpu_model": f"Made_Up_CPU_{rig}",
        "ram_mt_s": "3600",
        "pl1_uw": "95000000",
        "pl2_uw": "120000000",
        "gpu_name": f"Made_Up_Card_{rig}",
        "gpu_vram_mib": vram,
        "gpu_cc": cc,
        "driver": "580.178.04",
        "gpu_reserve_mib": reserve,
        "gpu_used_mib": "0",
        "gpu_free_mib": str(int(vram) - int(reserve)),
        "docker": "29.7.2",
        "kernel": "7.0.0-31-generic",
        "os_machine_id": hashlib.sha256(rig.encode()).hexdigest()[:16],
        "hostname": rig,
        "gpu_procs": "none",
        "containers": "none",
    }
    return {**values, **override}


def unit_id(name: str) -> str:
    return "unt-" + hashlib.sha256(name.encode()).hexdigest()


def llama(
    name: str, rig: str, port: int, np: int, ctx: int, room: int
) -> dict[str, Any]:
    argv = ["--model", f"/models/{name}.gguf", "--parallel", str(np)]
    argv += ["--port", str(port), "-c", str(ctx), "-ub", "512"]
    return {
        "rig": rig,
        "address": f"http://{rig}:{port}",
        "engine": "llama.cpp",
        "image": "llamacpp:made-up",
        "model": name,
        "width": np,
        "window": ctx,
        "output_tokens": 512,
        "request_timeout_s": 180,
        "room_mib": room,
        "container": f"mcgyvr-{name}",
        "unit_id": unit_id(name),
        "launch": {
            "argv": argv,
            "env": {"LLAMA_ARG_HOST": "0.0.0.0"},
            "volumes": ["/models:/models:ro"],
        },
    }


def vllm(name: str, rig: str, port: int, room: int) -> dict[str, Any]:
    argv = [f"Made/{name}", "--max-model-len", "4096", "--max-num-seqs", "8"]
    argv += ["--port", str(port)]
    return {
        "rig": rig,
        "address": f"http://{rig}:{port}",
        "engine": "vllm",
        "image": VLLM_IMAGE,
        "model": f"Made/{name}",
        "width": 8,
        "window": 4096,
        "output_tokens": 512,
        "request_timeout_s": 180,
        "room_mib": room,
        "kv_cache_memory_bytes": 1073741824,
        "attention_backend": "FLASH_ATTN",
        "container": f"mcgyvr-beta-{name}",
        "hf_cache": "/hf",
        "unit_id": unit_id(name),
        "launch": {"argv": argv, "env": {"HF_HUB_OFFLINE": "1"}},
    }


def fleet_doc() -> dict[str, Any]:
    return {
        "profile": "dev",
        "units": {
            "a_solo": llama("a_solo", "alpha", 8080, 1, 8192, 5000),
            "a_pair": llama("a_pair", "alpha", 8080, 2, 8192, 5200),
            "b_big": llama("b_big", "beta", 8003, 4, 16384, 11000),
            "b_small": vllm("b_small", "beta", 8001, 3500),
            "b_mid": vllm("b_mid", "beta", 8002, 8000),
        },
        "rigs": {
            "alpha": {"rig_id": STALE_PIN},
            "beta": {"rig_id": rig_id(snapshot("beta"))},
        },
        "fleets": {
            "one": {
                "layout": {
                    "alpha": [["a_solo", "awake"]],
                    "beta": [["b_big", "awake"]],
                },
                "next": ["two"],
            },
            "two": {
                "layout": {
                    "alpha": [["a_pair", "awake"]],
                    "beta": [["b_small", "awake"], ["b_mid", "awake"]],
                },
                "next": ["one"],
            },
        },
    }


def digests_doc(fleet: Mapping[str, Any], rig: str) -> dict[str, Any]:
    """``digests-<rig>.json``; the two rigs spell the image key two ways, as the
    committed files do."""
    key = "image_id" if rig == "alpha" else "image"
    units: dict[str, Any] = {}
    for name, unit in fleet["units"].items():
        if unit["rig"] != rig:
            continue
        image = str(unit["image"])
        units[name] = {
            "fields": {
                "argv": list(unit["launch"]["argv"]),
                "engine": unit["engine"],
                "env": dict(unit["launch"]["env"]),
                key: image.rpartition("@")[2] if "@" in image else LLAMA_IMAGE_ID,
            },
            "unit_id": unit["unit_id"],
        }
    return {"units": units}


def use_doc(**override: Any) -> dict[str, Any]:
    return {
        "use": USE,
        "why": ["a made-up fleet, planned and assembled on paper"],
        "keep_rig_pins": ["beta"],
        "unit_caps_on": ["beta"],
        "compose_must_match_live": {},
        **override,
    }


def make_tree(
    root: Path,
    *,
    fleet: dict[str, Any] | None = None,
    use: dict[str, Any] | None = None,
) -> Path:
    """The fleet files, hosts.json and use.json a plan is made from."""
    fleet = fleet if fleet is not None else fleet_doc()
    setup = root / "fleet-setup"
    setup.mkdir(parents=True, exist_ok=True)
    (setup / "fleet.yaml").write_text(yaml.safe_dump(fleet, sort_keys=False), "utf-8")
    ladder = {"ladder": list(fleet["units"])}
    (setup / "policy.yaml").write_text(yaml.safe_dump(ladder), "utf-8")
    for rig in ("alpha", "beta"):
        text = json.dumps(digests_doc(fleet, rig), indent=2)
        (setup / f"digests-{rig}.json").write_text(text, "utf-8")
    hosts = {
        rig: {"rig": {k: snapshot(rig)[k] for k in HOST_KEYS}, "read_on": WINDOW_DATE}
        for rig in ("alpha", "beta")
    }
    runs = root / "tools" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "hosts.json").write_text(json.dumps(hosts, indent=2), "utf-8")
    where = root / "records" / "measurements" / "lock-fleets" / USE
    where.mkdir(parents=True, exist_ok=True)
    doc = use if use is not None else use_doc()
    (where / "use.json").write_text(json.dumps(doc, indent=2), "utf-8")
    return root


def _marker(word: str, snap: Mapping[str, str], run_id: str) -> str:
    fields = " ".join(f"{k}={snap[k]}" for k in ("uptime_since", "pl1_uw", "pl2_uw"))
    return f"### {word} {fields} ram_mt_s={snap['ram_mt_s']} run_id={run_id}"


class Window:
    """Every file a frozen use's window leaves, written entry by entry."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.journal = root / "journal" / "fleet"
        self.plan = plan_module()
        self.runs = self.plan.read_runs(root, USE)
        self.fleet = load_fleet(
            (root / "fleet-setup" / "fleet.yaml").read_text("utf-8")
        )
        self.clock = datetime(2026, 9, 16, 10, 0, tzinfo=UTC)
        self.reads = 0

    def tick(self) -> str:
        self.clock += timedelta(minutes=1)
        return self.clock.strftime("%Y-%m-%dT%H:%M:%SZ")

    def reload(self) -> None:
        """The frozen order read back again, with any retry added since."""
        self.runs = self.plan.read_runs(self.root, USE)

    def retry(
        self, entry_id: str, change: Change | None = None, log: bool = True
    ) -> dict[str, str]:
        """``plan.py retry`` for a logged failed entry, then the retry's run
        written as a window would leave it."""
        made: dict[str, str] = self.plan.retry(
            self.root, USE, entry_id, "a made-up failure", journal=str(self.journal)
        )
        self.reload()
        self.write(self.runs.entry(made["retry_entry"]), change, log=log)
        return made

    def write_all(
        self,
        change: Mapping[str, Change] | None = None,
        unlogged: frozenset[str] = frozenset(),
    ) -> None:
        for entry in self.runs.entries:
            self.write(
                entry, (change or {}).get(entry.id), log=entry.id not in unlogged
            )

    def write(self, entry: Any, change: Change | None = None, log: bool = True) -> None:
        started = self.tick()
        if entry.kind in ("read", "load"):
            self.reads += 1
            run_id = f"run-20260916T{self.clock:%H%M%S}-{self.reads:08x}"
        else:
            run_id = entry.run_id(WINDOW_DATE)
        builders = {
            "unit": self._unit,
            "move": self._move,
            "serve-up": self._serve,
            "serve-down": self._serve,
            "read": self._read,
            "load": self._read,
        }
        payload = builders[entry.kind](entry, run_id)
        payload |= {"output": "", "write": True, "sidecar": False}
        if change is not None:
            change(payload)
        output = self._place(entry, run_id, payload)
        if log:
            cells = [entry.id, entry.rig, started, self.tick(), "0", run_id]
            cells += [entry.envelope(WINDOW_DATE), output]
            self.plan.insert_row(self.runs.path, self.plan.LOG_HEADER, cells)

    def _common(self, entry: Any, run_id: str) -> dict[str, Any]:
        snap = snapshot(entry.rig)
        return {
            "run_id": run_id,
            "host": entry.rig,
            "round": "r-fixture",
            "product_sha256": "0" * 64,
            "snapshots": {"start": dict(snap), "end": dict(snap)},
            "markers": {
                "start": _marker("START", snap, run_id),
                "end": _marker("END", snap, run_id),
                "on_rig": None,
            },
            "vmstat": {
                "start": {"pswpout": 10, "pgmajfault": 5},
                "end": {"pswpout": 10, "pgmajfault": 9},
            },
            "started_at": self.tick(),
            "ended_at": self.tick(),
            "failure": None,
        }

    def _unit(self, entry: Any, run_id: str) -> dict[str, Any]:
        name = entry.units[0]
        container = hashlib.sha256(entry.id.encode()).hexdigest()
        width = steps_module().launch(self.fleet, name).width
        peak = PEAK[name]
        samples = [
            f"gpu_app=4242,{mib},{container},llama-server\n"
            for mib in (peak - 300, peak)
        ]
        doc = {
            "schema": "lock-fleets-unit/1",
            **self._common(entry, run_id),
            "unit": name,
            "image": {"tag": "llamacpp:made-up", "digest": LLAMA_IMAGE_ID},
            "container_id": container,
            "wake_s": 40.0,
            "harness": {
                "figures": {
                    "warm_decode_tok_s": 32.0,
                    "prefill_tok_s": LLAMA_PREFILL[entry.run][1],
                    "decode_samples": list(LLAMA_DECODE),
                    "prefill_samples": list(LLAMA_PREFILL[entry.run]),
                },
                "after_page": "[]",
            },
            "load": {
                "load": {
                    "limit_s": 30,
                    "samples": samples,
                    "errors": [],
                    "idle_error": None,
                    "idle_after_close": True,
                    "idle_after_s": 0.5,
                    "completed": width,
                    "closed_unfinished": 0,
                    "restarts_before": "0",
                    "restarts_after": "0",
                    "pace_path": None,
                    "pace_start_page": None,
                    "pace_end_page": None,
                    "pace_seconds": 12.0,
                    "after_page": "[]",
                    "status_readings": 1,
                }
            },
            "restarts": 0,
        }
        return {"doc": doc}

    def _move(self, entry: Any, run_id: str) -> dict[str, Any]:
        source, target = steps_module().move_sides(
            self.fleet, entry.rig, entry.fleet, entry.to
        )
        started = "rc_compose" if target.compose else "rc_run"
        rc = {"rc_stop": 0, "rc_drop": 0, started: 0}
        stamps: dict[str, Any] = {
            "t0": 1000.0,
            "t1": 1002.0,
            "t_compose": 1003.0 if target.compose else None,
            "t2": {unit.name: 1060.0 for unit in target.units},
            "rc": rc,
            "timeout": [],
            "unparsed": [],
        }
        composed = source.compose or target.compose
        doc = {
            "schema": "lock-fleets-move/1",
            **self._common(entry, run_id),
            "rig": entry.rig,
            "stamps": stamps,
            "rc": rc,
            "compose_sha256": (
                hashlib.sha256(COMPOSE_TEXT.encode()).hexdigest() if composed else None
            ),
            "downtime_s": 60.0,
            "wake_s": {unit.name: 58.0 for unit in target.units},
        }
        return {"doc": doc}

    def _serve(self, entry: Any, run_id: str) -> dict[str, Any]:
        header = {"run_id": run_id, "started_at": self.tick()}
        if entry.kind == "serve-up":
            units = self.fleet["units"]
            step: dict[str, Any] = {
                "compose_up_exit": 0,
                "units": [
                    {"container": units[name]["container"], "healthy": True}
                    for name in entry.units
                ],
                "compose": COMPOSE_TEXT,
            }
        else:
            step = {"compose_down_exit": 0, "remaining": [], "daemon_read": True}
        return {"header": header, "step": step}

    def _read(self, entry: Any, run_id: str) -> dict[str, Any]:
        snap = snapshot(entry.rig)
        rig_row = {
            "fleet": entry.fleet,
            "rig": entry.rig,
            "rig_id": self.fleet["rigs"][entry.rig]["rig_id"],
            "combination_id": f"cmb-made-up-{entry.rig}-{entry.fleet}",
            "at": self.clock.strftime("%Y-%m-%dT%H:%M:%S"),
            "observed_rig_id": rig_id(snap),
            "snapshot": snap,
            "units": {},
            "foreign": [],
            "probed": {},
            "busy": {},
            "contended": [],
            "failed": {},
            "not_read": {},
            "loaded": [],
            "unloaded": {},
        }
        units: dict[str, dict[str, dict[str, Any]]] = {}
        for name in entry.units:
            fields: dict[str, dict[str, Any]] = {
                "warm_decode_tok_s": {"observed": 120.0},
                "prefill_tok_s": {"observed": 11000.0},
                "decode_samples": {"observed": list(VLLM_DECODE)},
                "prefill_samples": {"observed": list(VLLM_PREFILL)},
                "restarts": {"observed": 0},
                "attention_backend": {
                    "observed": "FLASH_ATTN",
                    "attention_backend": "FLASH_ATTN",
                },
            }
            if entry.kind == "load":
                fields["load_peak_mib"] = {
                    "observed": PEAK[name],
                    "unit": name,
                    "peak_mib": PEAK[name],
                    "limit_s": 30,
                    "errors": [],
                    "idle_error": None,
                    "idle_after_close": True,
                    "idle_after_s": 1.0,
                    "completed": 8,
                    "closed_unfinished": 0,
                    "restarts_before": 0,
                    "restarts_after": 0,
                    "samples": 61,
                    "pace_prompt_tok_s": 9000.0,
                    "pace_source": "vllm:prompt_tokens_total on /metrics",
                }
            units[name] = fields
        return {"rig": rig_row, "units": units}

    def _place(self, entry: Any, run_id: str, payload: dict[str, Any]) -> str:
        output = ""
        if payload["output"]:
            out = LOCK_FLEETS.name, USE, "logs", entry.rig, f"{entry.id}.out"
            path = self.root / "records" / "measurements" / Path(*out)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload["output"], "utf-8")
            output = path.relative_to(self.root).as_posix()
        if entry.kind in ("unit", "move"):
            where = self.root / entry.envelope(WINDOW_DATE)
            where.mkdir(parents=True, exist_ok=True)
            path = where / entry.artifact
            if payload["write"]:
                path.write_text(json.dumps(payload["doc"], indent=1), "utf-8")
            if payload["sidecar"]:
                sidecar = path.with_name(path.name + ".RIGMOVED")
                sidecar.write_text(f"### RIGMOVED run_id={run_id} x=1 x_start=0\n")
        elif entry.kind in ("serve-up", "serve-down"):
            where = self.root / entry.envelope(WINDOW_DATE)
            where.mkdir(parents=True, exist_ok=True)
            if payload["write"]:
                (where / f"{run_id}.run.json").write_text(json.dumps(payload["header"]))
                name = f"{entry.kind}.json"
                step = where / name
                if step.is_file():
                    old = json.loads(step.read_text("utf-8"))["run_id"]
                    step.rename(where / f"{entry.kind}.superseded-{old}.json")
                step.write_text(json.dumps({"run_id": run_id, **payload["step"]}))
            if payload["sidecar"]:
                sidecar = where / f"{entry.kind}.json.RIGMOVED"
                sidecar.write_text(f"### RIGMOVED run_id={run_id} x=1 x_start=0\n")
        elif payload["write"]:
            rig_row = {**payload["rig"], "run_id": run_id}
            where = self.journal / rig_row["combination_id"]
            where.mkdir(parents=True, exist_ok=True)
            with (where / "rig.jsonl").open("a", encoding="utf-8") as rows:
                rows.write(json.dumps(rig_row) + "\n")
            for name, fields in payload["units"].items():
                stamp = {
                    key: rig_row[key]
                    for key in ("fleet", "rig", "rig_id", "combination_id", "at")
                }
                with (where / f"{unit_id(name)}.jsonl").open(
                    "a", encoding="utf-8"
                ) as rows:
                    for field_name, values in fields.items():
                        row = {**stamp, "unit_id": unit_id(name), "run_id": run_id}
                        rows.write(
                            json.dumps({**row, "field": field_name, **values}) + "\n"
                        )
        return output


def frozen_window(root: Path, **tree: Any) -> Window:
    """A tree, its use frozen, and a window object ready to write."""
    make_tree(root, **tree)
    plan_module().freeze(root, USE)
    return Window(root)


def context(window: Window) -> Any:
    return assemble_module().Context.load(window.root, USE, str(window.journal))
